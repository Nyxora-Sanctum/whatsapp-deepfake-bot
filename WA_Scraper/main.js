const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

// --- LLM Integration ---
require("dotenv").config(); // Load environment variables from .env file
const ModelClient = require("@azure-rest/ai-inference").default;
const { AzureKeyCredential } = require("@azure/core-auth");

// --- Client Initializations ---

// Azure AI Client
const modelName = "Llama-3.3-70B-Instruct";
const aiClient = new ModelClient(
    process.env.AZURE_AI_ENDPOINT,
    new AzureKeyCredential(process.env.AZURE_AI_API_KEY)
);

// WhatsApp Client
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: "/usr/bin/google-chrome", // Adjust this path if necessary
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
});

// This object keeps track of each user's multi-step progress
const userStates = {};

// --- Helper Functions ---

/**
 * Uses an LLM to determine the user's intent from their message.
 * @param {string} userMessage The message sent by the user.
 * @returns {Promise<"IMAGE"|"VIDEO"|"UNKNOWN">} The classified intent.
 */
async function getIntent(userMessage) {
    const systemPrompt =
        "You are a classification assistant for a WhatsApp bot. Analyze the user's message to determine their intent. You must respond with only one of these three words: IMAGE, VIDEO, or UNKNOWN.";

    try {
        const response = await aiClient.path("/chat/completions").post({
            body: {
                messages: [
                    { role: "system", content: systemPrompt },
                    {
                        role: "user",
                        content: `What is the intent of this message? Message: "${userMessage}"`,
                    },
                ],
                max_tokens: 10,
                temperature: 0.1,
                model: modelName,
            },
        });

        if (response.status !== "200") {
            console.error("Azure AI Error:", response.body.error);
            return "UNKNOWN";
        }

        const intent = response.body.choices[0].message.content
            .trim()
            .toUpperCase();

        if (["IMAGE", "VIDEO"].includes(intent)) {
            return intent;
        }

        return "UNKNOWN";
    } catch (err) {
        console.error("The intent detection encountered an error:", err);
        return "UNKNOWN";
    }
}

/**
 * Runs the Python face-swapping script and provides real-time updates.
 * @param {string} chatId The user's chat ID.
 * @param {string} sourceImagePath Path to the source face image.
 * @param {string} targetAssetPath Path to the target image or video.
 * @param {string} assetType The type of asset, either "image" or "video".
 * @param {import('whatsapp-web.js').Message} loadingMessage The message to edit for status updates.
 * @returns {Promise<void>}
 */
async function runPythonScript(
    chatId,
    sourceImagePath,
    targetAssetPath,
    assetType,
    loadingMessage
) {
    return new Promise(async (resolve, reject) => {
        // Edit message to show processing has started
        await loadingMessage.edit(
            `Oke, proses AI-nya dimulai! 🪄\n\nIni mungkin butuh waktu beberapa saat, jadi sabar ya. Terutama untuk video, bisa lebih lama. 🧘`
        );

        const scriptDir = path.join(__dirname, "DL");
        const pythonScriptPath = path.join(scriptDir, "process_image.py");
        const tempDir = path.join(__dirname, "temp");
        const outputFilename = `output-${Date.now()}.${
            assetType === "video" ? "mp4" : "png"
        }`;
        const outputAssetPath = path.join(tempDir, outputFilename);

        const args = [
            pythonScriptPath,
            "--source",
            sourceImagePath,
            "--target",
            targetAssetPath,
            "--output",
            outputAssetPath,
            "--execution-provider",
            "CPUExecutionProvider",
        ];

        console.log(`Calling Python script with args: ${args.join(" ")}`);

        const pythonProcess = spawn("python", args, { cwd: scriptDir });

        pythonProcess.stdout.on("data", (data) =>
            console.log("Python output:", data.toString().trim())
        );
        pythonProcess.stderr.on("data", (data) =>
            console.error("Python error:", data.toString().trim())
        );

        pythonProcess.on("close", async (code) => {
            console.log(`Python script finished with code ${code}`);

            // Clean up temporary input files
            try {
                if (fs.existsSync(sourceImagePath))
                    await fs.promises.unlink(sourceImagePath);
                if (fs.existsSync(targetAssetPath))
                    await fs.promises.unlink(targetAssetPath);
            } catch (cleanupError) {
                console.error("Failed to clean up input files:", cleanupError);
            }

            if (code === 0 && fs.existsSync(outputAssetPath)) {
                console.log(
                    "Python script successful! Output at:",
                    outputAssetPath
                );
                try {
                    await loadingMessage.edit(
                        "Berhasil! ✨ Lagi ngirim hasilnya ke kamu..."
                    );
                    await new Promise((res) => setTimeout(res, 1000)); // Small delay for file system

                    const outputMedia =
                        MessageMedia.fromFilePath(outputAssetPath);
                    await client.sendMessage(chatId, outputMedia, {
                        caption: "Ini dia hasilnya, keren kan! 😎",
                    });
                    console.log("Successfully sent media to", chatId);
                    resolve();
                } catch (sendError) {
                    console.error("Error sending message:", sendError);
                    await loadingMessage.edit(
                        "Waduh, gagal ngirim filenya. Coba lagi nanti ya."
                    );
                    reject(sendError);
                } finally {
                    // Clean up the output file and the loading message
                    if (fs.existsSync(outputAssetPath)) {
                        await fs.promises.unlink(outputAssetPath);
                    }
                    await loadingMessage.delete(true); // Delete for everyone
                }
            } else {
                console.error("Python script failed or output file not found.");
                await loadingMessage.edit(
                    "Waduh, ada yang error pas prosesnya. 😥 Kayaknya ada masalah sama gambarnya."
                );
                client.sendMessage(
                    chatId,
                    "Gagal nih. Coba lagi pake gambar lain ya. Pastiin wajahnya keliatan jelas!"
                );
                reject(new Error("Python script failed."));
            }
        });
    });
}

// --- WhatsApp Client Event Handlers ---

client.on("ready", () => {
    console.log("Client is ready! 🚀");
});

client.on("qr", (qr) => {
    qrcode.generate(qr, { small: true });
});

client.on("message", async (message) => {
    const chatId = message.from;
    const lowerCaseBody = message.body.toLowerCase();

    // Check if the user is already in a process
    if (userStates[chatId]) {
        const currentState = userStates[chatId];
        const assetTypeName =
            currentState.type === "image" ? "gambar" : "video";

        if (message.hasMedia) {
            const media = await message.downloadMedia();
            const mediaType = media.mimetype.split("/")[0];

            // State 1: Waiting for the face image
            if (currentState.state === "waiting_for_face") {
                const filename = `face-${Date.now()}.${
                    media.mimetype.split("/")[1]
                }`;
                const tempDir = path.join(__dirname, "temp");
                if (!fs.existsSync(tempDir)) fs.mkdirSync(tempDir);
                const filepath = path.join(tempDir, filename);

                fs.writeFileSync(filepath, media.data, { encoding: "base64" });
                currentState.faceImage = filepath;
                currentState.state = `waiting_for_${currentState.type}`;

                client.sendMessage(
                    chatId,
                    `Sip, foto wajahnya udah kuterima! 👍\n\nSekarang, kirim ${assetTypeName} yang mau ditempelin wajah ini.`
                );
                return;
            }

            // State 2: Waiting for the target image/video
            else if (
                currentState.state === `waiting_for_${currentState.type}`
            ) {
                const isCorrectType =
                    (currentState.type === "image" && mediaType === "image") ||
                    (currentState.type === "video" && mediaType === "video");

                if (isCorrectType) {
                    const filename = `${currentState.type}-${Date.now()}.${
                        media.mimetype.split("/")[1]
                    }`;
                    const tempDir = path.join(__dirname, "temp");
                    const filepath = path.join(tempDir, filename);
                    fs.writeFileSync(filepath, media.data, {
                        encoding: "base64",
                    });
                    currentState.mainAsset = filepath;

                    // Send the initial message that we will edit later
                    const loadingMessage = await client.sendMessage(
                        chatId,
                        "Oke, semua file lengkap! Lagi disiapin dulu ya... 🚀"
                    );

                    await runPythonScript(
                        chatId,
                        currentState.faceImage,
                        currentState.mainAsset,
                        currentState.type,
                        loadingMessage // Pass the message object to be edited
                    );

                    delete userStates[chatId]; // Reset state after completion
                } else {
                    client.sendMessage(
                        chatId,
                        `Waduh, tipenya salah nih. Aku butuhnya file ${assetTypeName}, bukan ${mediaType}. Kirim yang bener ya.`
                    );
                }
            }
        } else {
            client.sendMessage(
                chatId,
                "Eh, jangan tulisan doang, kirimin aku file gambar atau video dong. 😊"
            );
        }

        // If the user is NOT in a process, use the LLM to understand them
    } else {
        const intent = await getIntent(lowerCaseBody);
        console.log(`User: "${lowerCaseBody}" -> Intent: ${intent}`);

        switch (intent) {
            case "IMAGE":
                userStates[chatId] = {
                    state: "waiting_for_face",
                    faceImage: null,
                    mainAsset: null,
                    type: "image",
                };
                client.sendMessage(
                    chatId,
                    "Asiik, kita bikin gambar ya! 🖼️\n\nYuk, pertama-tama kirim dulu foto close-up yang ada wajahnya."
                );
                break;

            case "VIDEO":
                userStates[chatId] = {
                    state: "waiting_for_face",
                    faceImage: null,
                    mainAsset: null,
                    type: "video",
                };
                client.sendMessage(
                    chatId,
                    "Oke, kita bikin video! 🎥\n\nCoba kirim dulu satu foto yang ada wajahnya dengan jelas ya."
                );
                break;

            case "UNKNOWN":
            default:
                const welcomeMessage = `
Halo! 👋 Aku bot AI yang bisa nuker wajah di foto dan video. Keren kan?

Mau coba? Gampang kok, tinggal bilang aja mau buat apa, contohnya:
➡️ "bro, buatin gambar dong"
➡️ "aku mau bikin video lucu"

Nanti aku pandu langkah-langkahnya. Yuk mulai!
                `;
                client.sendMessage(chatId, welcomeMessage.trim());
                break;
        }
    }
});

// --- Start The Bot ---
client.initialize();

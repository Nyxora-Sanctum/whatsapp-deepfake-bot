const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

// --- LLM Integration ---
require("dotenv").config(); // Load environment variables from .env file
const ModelClient = require("@azure-rest/ai-inference").default;
const { AzureKeyCredential } = require("@azure/core-auth");

// --- NEW: User Database for Persistence ---
const USER_DB_PATH = path.join(__dirname, "user_database.json");
let userDB = {};

// Load the user database from the file on startup
try {
    if (fs.existsSync(USER_DB_PATH)) {
        const data = fs.readFileSync(USER_DB_PATH, "utf8");
        userDB = JSON.parse(data);
        console.log("User database loaded.");
    } else {
        console.log(
            "No existing user database found, a new one will be created."
        );
    }
} catch (err) {
    console.error("Failed to load user database:", err);
}

/**
 * Saves the current state of the user database to the JSON file.
 */
function saveUserDB() {
    try {
        fs.writeFileSync(USER_DB_PATH, JSON.stringify(userDB, null, 2));
    } catch (err) {
        console.error("Failed to save user database:", err);
    }
}

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

// This object keeps track of each user's multi-step progress in memory
const userStates = {};

// --- Helper Functions ---

/**
 * Creates a visual text-based progress bar.
 * @param {number} percentage The progress percentage (0-100).
 * @returns {string} The formatted progress bar string.
 */
function createProgressBar(percentage) {
    const filledBlocks = Math.round(percentage / 10);
    const emptyBlocks = 10 - filledBlocks;
    const bar = "█".repeat(filledBlocks) + "░".repeat(emptyBlocks);
    return `[${bar}] ${percentage}%`;
}

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
        let lastReportedProgress = -1;

        pythonProcess.stdout.on("data", async (data) => {
            const output = data.toString().trim();
            console.log("Python output:", output);

            if (output.startsWith("PROGRESS:")) {
                const currentProgress = parseInt(output.split(":")[1], 10);
                if (
                    currentProgress > lastReportedProgress + 4 &&
                    currentProgress < 100
                ) {
                    lastReportedProgress = currentProgress;
                    const progressBar = createProgressBar(currentProgress);
                    // MODIFIED: Gen Z style message
                    const messageText = `Okee, AI-nya lagi kerja keras nih.\n\n${progressBar}\n\nBentar yaa, sabar dikit. Kalo video emang lebih lama prosesnya.`;
                    try {
                        await loadingMessage.edit(messageText);
                    } catch (editError) {
                        console.warn(
                            "Could not edit loading message:",
                            editError.message
                        );
                    }
                }
            }
        });

        let pythonErrorOutput = "";
        pythonProcess.stderr.on("data", (data) => {
            const errorText = data.toString().trim();
            console.error("Python error:", errorText);
            pythonErrorOutput += errorText + "\n";
        });

        pythonProcess.on("close", async (code) => {
            console.log(`Python script finished with code ${code}`);
            try {
                if (fs.existsSync(sourceImagePath))
                    await fs.promises.unlink(sourceImagePath);
                if (fs.existsSync(targetAssetPath))
                    await fs.promises.unlink(targetAssetPath);
            } catch (cleanupError) {
                console.error("Failed to clean up input files:", cleanupError);
            }

            const successful = code === 0 && fs.existsSync(outputAssetPath);
            const noFaceDetected =
                pythonErrorOutput.includes("No face detected");

            if (successful) {
                console.log(
                    "Python script successful! Output at:",
                    outputAssetPath
                );
                try {
                    // MODIFIED: Gen Z style message
                    await loadingMessage.edit(
                        "Selesaii! Bentar yaa, hasilnya lagi dikirim."
                    );
                    await new Promise((res) => setTimeout(res, 1000));

                    const outputMedia =
                        MessageMedia.fromFilePath(outputAssetPath);
                    await client.sendMessage(chatId, outputMedia, {
                        // MODIFIED: Gen Z style message
                        caption: "Nih hasilnya, gokil ga?",
                    });
                    console.log("Successfully sent media to", chatId);
                    resolve();
                } catch (sendError) {
                    console.error("Error sending message:", sendError);
                    // MODIFIED: Gen Z style message
                    await loadingMessage.edit(
                        "Yah, gagal kirim filenya. Coba lagi ntar ya."
                    );
                    reject(sendError);
                } finally {
                    if (fs.existsSync(outputAssetPath)) {
                        await fs.promises.unlink(outputAssetPath);
                    }
                    await loadingMessage.delete(true);
                }
            } else {
                console.error("Python script failed or output file not found.");
                // MODIFIED: Gen Z style error messages
                let userErrorMessage =
                    "Duh, ada error nih pas proses. Coba lagi ntar yaa.";
                if (noFaceDetected) {
                    userErrorMessage =
                        "Yah, ga kedeteksi wajahnya di foto pertama. Coba pake foto lain yang mukanya jelas, ga miring, dan ga ketutupan apa-apa.";
                }
                await loadingMessage.edit(userErrorMessage);
                reject(
                    new Error(
                        noFaceDetected
                            ? "No face detected"
                            : "Python script failed"
                    )
                );
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

    // --- NEW: Check for new user and send T&C ---
    if (!userDB[chatId]) {
        console.log(`New user detected: ${chatId}. Sending T&C.`);
        const tncPath = path.join(__dirname, "TNC.pdf");

        if (fs.existsSync(tncPath)) {
            const tncMedia = MessageMedia.fromFilePath(tncPath);
            // MODIFIED: Gen Z style message
            await client.sendMessage(
                chatId,
                "Halo! Sebelum mulai, baca TNC dulu yaa. Penting nih biar sama-sama enak."
            );
            await client.sendMessage(chatId, tncMedia);
        } else {
            console.warn("TNC.pdf not found in the script directory.");
            // MODIFIED: Gen Z style message
            await client.sendMessage(
                chatId,
                "Halo! Kenalin aku bot AI buat tuker muka."
            );
        }

        // Add user to DB and save
        userDB[chatId] = { firstContact: new Date().toISOString() };
        saveUserDB();

        // Send the main welcome message after T&C
        // MODIFIED: Gen Z style welcome message
        const welcomeMessage = `
Aku bisa nuker wajah di foto sama video.

Mau coba? Gampang, tinggal bilang aja mau buat apa, contohnya:
➡️ "bro, buatin gambar"
➡️ "aku mau bikin video lucu"

Nanti aku pandu langkah-langkahnya. Yuk mulai!
        `;
        await client.sendMessage(chatId, welcomeMessage.trim());
        return; // Stop processing this message further
    }

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

                // MODIFIED: Gen Z style message
                client.sendMessage(
                    chatId,
                    `Oke, fotonya udah masuk. Sekarang kirim ${assetTypeName} yang mau diganti mukanya.`
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

                    // MODIFIED: Gen Z style message
                    const loadingMessage = await client.sendMessage(
                        chatId,
                        "Sip, filenya lengkap. Prosesnya kumulai yaa."
                    );

                    try {
                        await runPythonScript(
                            chatId,
                            currentState.faceImage,
                            currentState.mainAsset,
                            currentState.type,
                            loadingMessage
                        );
                        console.log(
                            `Process for ${chatId} completed successfully.`
                        );
                    } catch (error) {
                        console.error(
                            `Script execution failed for ${chatId}:`,
                            error.message
                        );
                    } finally {
                        delete userStates[chatId]; // Always reset state
                    }
                } else {
                    // MODIFIED: Gen Z style message
                    client.sendMessage(
                        chatId,
                        `Eh, salah tipe file. Aku butuhnya ${assetTypeName}, bukan ${mediaType}. Kirim ulang yang bener yaa.`
                    );
                }
            }
        } else {
            // MODIFIED: Gen Z style message
            client.sendMessage(
                chatId,
                "Jangan chat doang, kirim file dongg. Mau gambar apa video?"
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
                // MODIFIED: Gen Z style message
                client.sendMessage(
                    chatId,
                    "Oke, kita bikin gambar ya. Pertama, kirim dulu satu foto muka yang jelas."
                );
                break;

            case "VIDEO":
                userStates[chatId] = {
                    state: "waiting_for_face",
                    faceImage: null,
                    mainAsset: null,
                    type: "video",
                };
                // MODIFIED: Gen Z style message
                client.sendMessage(
                    chatId,
                    "Gas, kita bikin video. Kirim dulu satu foto muka yang jelas yaa."
                );
                break;

            case "UNKNOWN":
            default:
                // MODIFIED: Gen Z style welcome message
                const welcomeMessage = `
Halo! Aku bot AI yang bisa nuker wajah di foto dan video.

Mau coba? Gampang, tinggal bilang aja mau buat apa, contohnya:
➡️ "bro, buatin gambar"
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

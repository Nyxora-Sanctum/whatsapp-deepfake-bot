const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

// --- LLM Integration ---
require("dotenv").config(); // Load environment variables from .env file
const ModelClient = require("@azure-rest/ai-inference").default;
const { AzureKeyCredential } = require("@azure/core-auth");

// --- User Database for Persistence ---
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
// NEW: This object keeps track of recent chat history for each user
const chatHistories = {};
const CHAT_HISTORY_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes

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
 * @returns {Promise<"IMAGE"|"VIDEO"|"CHITCHAT"|"UNKNOWN">} The classified intent.
 */
async function getIntent(userMessage) {
    const systemPrompt =
        "You are a classification assistant for a WhatsApp bot. Analyze the user's message to determine their intent. You must respond with only one of these three words: IMAGE, VIDEO, or CHITCHAT. If the user asks to create a picture, photo, or image, respond with IMAGE. If they ask to create a video or clip, respond with VIDEO. For any other conversation, greeting, or question, respond with CHITCHAT.";

    try {
        const response = await aiClient.path("/chat/completions").post({
            body: {
                messages: [
                    { role: "system", content: systemPrompt },
                    {
                        role: "user",
                        content: `Classify the intent of this message: "${userMessage}"`,
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

        if (["IMAGE", "VIDEO", "CHITCHAT"].includes(intent)) {
            return intent;
        }

        return "UNKNOWN";
    } catch (err) {
        console.error("The intent detection encountered an error:", err);
        return "UNKNOWN";
    }
}

/**
 * NEW: Uses an LLM to generate a conversational response.
 * @param {string} userMessage The latest message from the user.
 * @param {Array<Object>} history The user's recent chat history.
 * @returns {Promise<string>} The bot's generated response.
 */
async function getChatResponse(userMessage, history) {
    // --- MODIFICATION: Updated system prompt for 'soft boy' persona ---
    const systemPrompt =
        "You are a friendly and helpful WhatsApp bot with a 'soft boy' personality. You speak like a kind Gen Z Indonesian. Use 'aku' for yourself and 'kamu' for the user. Absolutely NEVER use 'lo' or 'gue'. Your vocabulary includes soft, modern slang like 'gemes', 'lucu banget', 'ih', 'hehe', 'wkwk', 'santuy', 'semangat ya', 'gapapa kok'. Keep your responses short, sweet, and conversational, like you're texting a close friend. Your main job is to chat, but you can also create images and videos if asked. Right now, your only task is to respond to the user's latest message based on the conversation history.";

    const messages = [
        { role: "system", content: systemPrompt },
        ...history.map((h) => ({ role: h.role, content: h.content })),
        { role: "user", content: userMessage },
    ];

    try {
        const response = await aiClient.path("/chat/completions").post({
            body: {
                messages,
                max_tokens: 80,
                temperature: 0.7,
                model: modelName,
            },
        });

        if (response.status !== "200") {
            console.error("Azure AI Error:", response.body.error);
            return "Aduh, AI aku lagi error nih. Maaf yaa :(";
        }
        return response.body.choices[0].message.content;
    } catch (err) {
        console.error("The chat response encountered an error:", err);
        return "Hehe, aku lagi pusing. Nanti kita ngobrol lagi yaa.";
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
                    const messageText = `Bentar yaa, Tunggu AI nya proses...\n\n${progressBar}\n\nKalo video emang butuh waktu lebih lama sih. Jadi tunggu dulu hehe.`;
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
                    await loadingMessage.edit(
                        "Udah selese! Bentar, aku kirim hasilnya."
                    );
                    await new Promise((res) => setTimeout(res, 1000));

                    const outputMedia =
                        MessageMedia.fromFilePath(outputAssetPath);
                    await client.sendMessage(chatId, outputMedia, {
                        caption: "Nih hasilnya, goks kan? wkwkwk",
                    });
                    console.log("Successfully sent media to", chatId);
                    resolve();
                } catch (sendError) {
                    console.error("Error sending message:", sendError);
                    await loadingMessage.edit(
                        "Hell nah, filenya gagal kekirim. coba lagi yaa kak."
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
                let userErrorMessage =
                    "Njir, ada error pas proses. Coba lagi ya.";
                if (noFaceDetected) {
                    userErrorMessage =
                        "Mukanya nggak keliatan di foto pertama. Coba pake foto lain deh. Yang lurus ke depan, jangan miring-miring, dan jangan ketutupan apa-apa.";
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
    const now = Date.now();

    // --- History Management: Clear history if older than 15 mins ---
    if (chatHistories[chatId] && chatHistories[chatId].length > 0) {
        const firstMessageTimestamp = chatHistories[chatId][0].timestamp;
        if (now - firstMessageTimestamp > CHAT_HISTORY_TIMEOUT_MS) {
            console.log(`Chat history for ${chatId} expired. Clearing.`);
            delete chatHistories[chatId];
        }
    }
    if (!chatHistories[chatId]) {
        chatHistories[chatId] = [];
    }

    // --- New User Onboarding ---
    if (!userDB[chatId]) {
        console.log(`New user detected: ${chatId}. Sending T&C.`);
        const tncPath = path.join(__dirname, "TNC.pdf");

        if (fs.existsSync(tncPath)) {
            const tncMedia = MessageMedia.fromFilePath(tncPath);
            await client.sendMessage(
                chatId,
                "Haloo, dibaca dulu ya syarat dan ketentuannya. Makasi."
            );
            await client.sendMessage(chatId, tncMedia);
        } else {
            console.warn("TNC.pdf not found in the script directory.");
            await client.sendMessage(
                chatId,
                "Oh iya, datamu disini tetap private ya, jadi nggaakan dijual/dipakai/disimpan."
            );
        }

        userDB[chatId] = { firstContact: new Date().toISOString() };
        saveUserDB();

        const welcomeMessage = `
Aku bisa ngubah muka orang di foto/video jadi muka orang lain.

Kalo mau bikin, bilang aja, contoh:
➡️ "Ubahin wajah di fotoku dongg"
➡️ "Ubahin wajah di videoku yaa"

Kalo mau ngobrol dulu nggapapa kok!
        `;
        await client.sendMessage(chatId, welcomeMessage.trim());
        return;
    }

    // --- Handle Active Generation Process ---
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
                    `Oke, foto muka dapet. Sekarang kirim ${assetTypeName} targetnya.`
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

                    const loadingMessage = await client.sendMessage(
                        chatId,
                        "Sip, bahan lengkap. Gua proses dulu, sabar..."
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
                    client.sendMessage(
                        chatId,
                        `Hell nah, itu kan ${mediaType}. Gua butuhnya ${assetTypeName}, bro. Kirim ulang yang bener.`
                    );
                }
            }
        } else {
            client.sendMessage(
                chatId,
                "Bukan ngetik, bro. Kirim filenya donggg."
            );
        }
        return; // Stop further processing
    }

    // --- If not in a process, determine intent (Chit-chat, Image, Video) ---
    const intent = await getIntent(lowerCaseBody);
    console.log(`User: "${lowerCaseBody}" -> Intent: ${intent}`);

    // Add user message to history AFTER intent classification but BEFORE response generation
    chatHistories[chatId].push({
        role: "user",
        content: message.body,
        timestamp: now,
    });

    // --- MODIFICATION: Added emoji reactions and adjusted prompts ---
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
                "Oke siap, kita buatin gambarnya. Kirimin aku satu foto muka kamu yang jelas yaa, biar hasilnya bagus."
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
                "Asik, bikin video! Boleh minta satu foto muka kamu yang jelas dulu, hehe."
            );
            break;

        case "CHITCHAT":
        case "UNKNOWN": // Treat UNKNOWN as CHITCHAT for a more robust conversational experience
        default:
            // --- MODIFICATION: Add a chance to react with an emoji for natural interaction ---
            try {
                // React to the user's message sometimes (e.g., 30% chance)
                if (Math.random() < 0.3) {
                    const softBoyEmojis = ["👍", "😊", "✨", "🥺", "❤️", "✅"];
                    const randomEmoji =
                        softBoyEmojis[
                            Math.floor(Math.random() * softBoyEmojis.length)
                        ];
                    await message.react(randomEmoji);
                }
            } catch (e) {
                console.warn("Couldn't react to message:", e.message);
            }

            const reply = await getChatResponse(
                message.body,
                chatHistories[chatId]
            );
            await client.sendMessage(chatId, reply);
            // Add bot's reply to history
            chatHistories[chatId].push({
                role: "assistant",
                content: reply,
                timestamp: now,
            });
            break;
    }
});

// --- Start The Bot ---
client.initialize();

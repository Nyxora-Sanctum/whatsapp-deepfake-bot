const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

// --- LLM Integration ---
require("dotenv").config();
const ModelClient = require("@azure-rest/ai-inference").default;
const { AzureKeyCredential } = require("@azure/core-auth");

// --- User Database for Persistence ---
const USER_DB_PATH = path.join(__dirname, "user_database.json");
let userDB = {};

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

function saveUserDB() {
    try {
        fs.writeFileSync(USER_DB_PATH, JSON.stringify(userDB, null, 2));
    } catch (err) {
        console.error("Failed to save user database:", err);
    }
}

// --- Client Initializations ---
const modelName = "Llama-3.3-70B-Instruct";
const aiClient = new ModelClient(
    process.env.AZURE_AI_ENDPOINT,
    new AzureKeyCredential(process.env.AZURE_AI_API_KEY)
);

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: "/usr/bin/google-chrome",
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
});

const userStates = {}; // In-memory state for multi-step processes
const chatHistories = {}; // In-memory chat history
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
 * **[NEW & IMPROVED]** Uses an LLM to determine the user's intent, aware of the current conversation context.
 * @param {import('whatsapp-web.js').Message} message The incoming message object.
 * @param {object|null} currentUserState The user's current state from userStates.
 * @returns {Promise<string>} The classified intent (e.g., "START_IMAGE", "CANCEL", "CHITCHAT").
 */
async function classifyUserIntent(message, currentUserState) {
    const userMessage = message.body;

    let systemPrompt;
    // The prompt changes based on whether the user is in the middle of a process.
    if (currentUserState) {
        // --- CONTEXT-AWARE PROMPT ---
        systemPrompt = `You are a classification assistant for a WhatsApp bot that is currently in the middle of a task with a user. The user is in the '${currentUserState.state}' step of a '${currentUserState.type}' creation process. Analyze the user's latest message.

        Possible intents are:
        - CANCEL: User wants to stop, cancel, or quit the current process. Keywords: "cancel", "batal", "stop", "gajadi".
        - SWITCH_TO_IMAGE: User explicitly asks to switch to making an image instead.
        - SWITCH_TO_VIDEO: User explicitly asks to switch to making a video instead.
        - PROVIDE_MEDIA: User has sent a file (image or video). You should ONLY return this if the message contains media.
        - CHITCHAT: Any other question, comment, or conversation not related to the above.

        Respond with ONLY one of the intent names from the list above.`;
    } else {
        // --- GENERAL PROMPT ---
        systemPrompt = `You are a classification assistant for a WhatsApp bot. Analyze the user's message to determine their primary intent.

        Possible intents are:
        - START_IMAGE: User wants to create or generate a picture, photo, or image.
        - START_VIDEO: User wants to create or generate a video or clip.
        - CHITCHAT: Any other conversation, greeting, question, or statement.

        Respond with ONLY one of the intent names: START_IMAGE, START_VIDEO, or CHITCHAT.`;
    }

    // If the user sent media, the intent is almost certainly to provide it for the process.
    // This avoids an unnecessary LLM call and provides a faster response.
    if (currentUserState && message.hasMedia) {
        return "PROVIDE_MEDIA";
    }

    try {
        const response = await aiClient.path("/chat/completions").post({
            body: {
                messages: [
                    { role: "system", content: systemPrompt },
                    {
                        role: "user",
                        content: `Classify this message: "${userMessage}"`,
                    },
                ],
                max_tokens: 15,
                temperature: 0.1,
                model: modelName,
            },
        });

        if (response.status !== "200") {
            console.error("Azure AI Error:", response.body.error);
            return "CHITCHAT"; // Default to CHITCHAT on error
        }

        const intent = response.body.choices[0].message.content
            .trim()
            .toUpperCase();
        console.log(
            `Message: "${userMessage}" -> Classified Intent: ${intent}`
        );
        return intent;
    } catch (err) {
        console.error("The intent detection encountered an error:", err);
        return "CHITCHAT"; // Default to CHITCHAT on error
    }
}

/**
 * Uses an LLM to generate a conversational response.
 * @param {string} userMessage The latest message from the user.
 * @param {Array<Object>} history The user's recent chat history.
 * @returns {Promise<string>} The bot's generated response.
 */
async function getChatResponse(userMessage, history) {
    const systemPrompt =
        "You are a friendly and helpful WhatsApp bot with a 'soft boy' personality. You speak like a kind Gen Z Indonesian. Use 'aku' for yourself and 'kamu' for the user. Absolutely NEVER use 'lo' or 'gue'. Your vocabulary includes soft, modern slang like 'gemes', 'lucu banget', 'ih', 'hehe', 'wkwk', 'santuy', 'semangat ya', 'gapapa kok'. Keep your responses short, sweet, and conversational, like you're texting a close friend. Your main job is to chat, but you can also create images and videos if asked. Right now, your only task is to respond to the user's latest message based on the conversation history.";

    // The history is already being passed correctly here.
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
 * (This function remains unchanged as its internal logic is sound)
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
                        "Aduh, filenya gagal kekirim. coba lagi yaa kak."
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
                    "Waduh, ada error pas proses. Coba lagi ya.";
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

/**
 * **[NEW]** Handles the logic for processing media sent by the user during a task.
 * @param {import('whatsapp-web.js').Message} message The incoming message object with media.
 */
async function handleMediaProvision(message) {
    const chatId = message.from;
    const currentState = userStates[chatId];
    if (!currentState) return; // Safety check

    const assetTypeName = currentState.type === "image" ? "gambar" : "video";
    const media = await message.downloadMedia();
    const mediaType = media.mimetype.split("/")[0];

    // State 1: Waiting for the face image
    if (currentState.state === "waiting_for_face") {
        const filename = `face-${Date.now()}.${media.mimetype.split("/")[1]}`;
        const tempDir = path.join(__dirname, "temp");
        if (!fs.existsSync(tempDir)) fs.mkdirSync(tempDir);
        const filepath = path.join(tempDir, filename);

        fs.writeFileSync(filepath, media.data, { encoding: "base64" });
        currentState.faceImage = filepath;
        currentState.state = `waiting_for_${currentState.type}`;

        client.sendMessage(
            chatId,
            `Oke, foto muka dapet. Sekarang kirim ${assetTypeName} targetnya yaa.`
        );
        return;
    }

    // State 2: Waiting for the target image/video
    else if (currentState.state === `waiting_for_${currentState.type}`) {
        const isCorrectType =
            (currentState.type === "image" && mediaType === "image") ||
            (currentState.type === "video" && mediaType === "video");

        if (isCorrectType) {
            const filename = `${currentState.type}-${Date.now()}.${
                media.mimetype.split("/")[1]
            }`;
            const tempDir = path.join(__dirname, "temp");
            const filepath = path.join(tempDir, filename);
            fs.writeFileSync(filepath, media.data, { encoding: "base64" });
            currentState.mainAsset = filepath;

            const loadingMessage = await client.sendMessage(
                chatId,
                "Sip, bahan lengkap. Aku proses dulu ya, sabar..."
            );

            try {
                await runPythonScript(
                    chatId,
                    currentState.faceImage,
                    currentState.mainAsset,
                    currentState.type,
                    loadingMessage
                );
                console.log(`Process for ${chatId} completed successfully.`);
            } catch (error) {
                console.error(
                    `Script execution failed for ${chatId}:`,
                    error.message
                );
            } finally {
                delete userStates[chatId]; // Always reset state after completion or failure
            }
        } else {
            client.sendMessage(
                chatId,
                `Ih, itu kan ${mediaType}. Aku butuhnya ${assetTypeName}, kamu salah kirim hehe. Kirim ulang yang bener ya.`
            );
        }
    }
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
    const now = Date.now();
    const currentUserState = userStates[chatId];

    // --- History Management ---
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
                "Oh iya, datamu disini tetap privat ya, jadi nggaakan dijual/dipakai/disimpan."
            );
        }
        userDB[chatId] = { firstContact: new Date().toISOString() };
        saveUserDB();
        const welcomeMessage = `
Aku bisa ngubah muka orang di foto/video jadi muka orang lain.

Kalo mau bikin, bilang aja, contoh:
➡️ "Ubahin wajah di fotoku dongg"
➡️ "Ubahin wajah di videoku yaa"

Kalo mau ngobrol dulu nggapapa kok!`;
        await client.sendMessage(chatId, welcomeMessage.trim());
        return;
    }

    // --- CENTRALIZED INTENT CLASSIFICATION ---
    // Every message is classified here first.
    const intent = await classifyUserIntent(message, currentUserState);

    // Add user message to history AFTER intent classification
    chatHistories[chatId].push({
        role: "user",
        content: message.body,
        timestamp: now,
    });

    // --- Main Logic Router based on Intent ---
    switch (intent) {
        case "START_IMAGE":
            userStates[chatId] = {
                state: "waiting_for_face",
                faceImage: null,
                mainAsset: null,
                type: "image",
            };
            await client.sendMessage(
                chatId,
                "Oke siap, kita buatin gambarnya. Kirimin aku satu foto muka kamu yang jelas yaa, biar hasilnya bagus."
            );
            break;

        case "START_VIDEO":
            userStates[chatId] = {
                state: "waiting_for_face",
                faceImage: null,
                mainAsset: null,
                type: "video",
            };
            await client.sendMessage(
                chatId,
                "Asik, bikin video! Boleh minta satu foto muka kamu yang jelas dulu, hehe."
            );
            break;

        case "PROVIDE_MEDIA":
            // This case is only reachable if the user is in an active state and sends media.
            if (currentUserState) {
                await handleMediaProvision(message);
            } else {
                // This case should not be reached if no state, but as a fallback, treat as chitchat
                await client.sendMessage(
                    chatId,
                    "Hmm, kamu ngirim file tapi aku lagi ngga nungguin apa-apa. Mau buat sesuatu kah?"
                );
            }
            break;

        case "CANCEL":
            if (currentUserState) {
                delete userStates[chatId]; // Clear the state
                await client.sendMessage(
                    chatId,
                    "Oke, prosesnya aku batalin ya. Kalo mau mulai lagi, bilang aja hehe. 😊"
                );
            } else {
                await client.sendMessage(
                    chatId,
                    "Ngga ada proses yang lagi jalan kok, jadi santuy aja hehe."
                );
            }
            break;

        case "SWITCH_TO_IMAGE":
            if (currentUserState) {
                await client.sendMessage(
                    chatId,
                    `Oke, kita ganti ya. Batalin yang ${currentUserState.type}, sekarang kita mulai buat image baru.`
                );
            }
            // Start the image process from scratch
            userStates[chatId] = { state: "waiting_for_face", type: "image" };
            await client.sendMessage(
                chatId,
                "Oke, kita mulai dari awal buat gambar ya. Kirimin aku foto muka kamu yang jelas."
            );
            break;

        case "SWITCH_TO_VIDEO":
            if (currentUserState) {
                await client.sendMessage(
                    chatId,
                    `Oke, kita ganti ya. Batalin yang ${currentUserState.type}, sekarang kita mulai buat video baru.`
                );
            }
            // Start the video process from scratch
            userStates[chatId] = { state: "waiting_for_face", type: "video" };
            await client.sendMessage(
                chatId,
                "Oke, kita mulai dari awal buat video ya. Kirimin aku foto muka kamu yang jelas."
            );
            break;

        case "CHITCHAT":
        default: // Also handles UNKNOWN
            if (currentUserState) {
                // If the user is chitchatting during a process, remind them what's needed.
                await client.sendMessage(
                    chatId,
                    "Lagi nungguin file nih, bukan ketikan. Kirim fotonya dong, atau bilang 'batal' kalo ngga jadi. Semangat yaa!"
                );
            } else {
                // Standard chitchat flow
                try {
                    if (Math.random() < 0.3) {
                        const softBoyEmojis = [
                            "👍",
                            "😊",
                            "✨",
                            "🥺",
                            "❤️",
                            "✅",
                        ];
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

                chatHistories[chatId].push({
                    role: "assistant",
                    content: reply,
                    timestamp: now,
                });
            }
            break;
    }
});

// --- Start The Bot ---
client.initialize();

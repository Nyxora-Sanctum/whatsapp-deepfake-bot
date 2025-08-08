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
// This object keeps track of recent chat history for each user
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
 * @returns {Promise<"IMAGE"|"VIDEO"|"CHITCHAT"|"HELP"|"UNKNOWN">} The classified intent.
 */
async function getIntent(userMessage) {
    const systemPrompt =
        "You are a classification assistant for a WhatsApp bot. Analyze the user's message to determine their intent. You must respond with only one of these four words: IMAGE, VIDEO, CHITCHAT, or HELP. If the user asks to create a picture, photo, or image, respond with IMAGE. If they ask to create a video or clip, respond with VIDEO. If the user asks for help, menu, or what you can do, respond with HELP. For any other conversation, greeting, or question, respond with CHITCHAT.";

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

        if (["IMAGE", "VIDEO", "CHITCHAT", "HELP"].includes(intent)) {
            return intent;
        }

        return "UNKNOWN";
    } catch (err) {
        console.error("The intent detection encountered an error:", err);
        return "UNKNOWN";
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
 * Runs the enhanced Python script with user-selected options including quality.
 * @param {string} chatId The user's chat ID.
 * @param {object} options The state object containing all paths and user choices.
 * @returns {Promise<void>}
 */
async function runPythonScript(chatId, options) {
    return new Promise(async (resolve, reject) => {
        const {
            sourceImage,
            mainAsset,
            type,
            useEnhancer,
            processManyFaces,
            quality,
        } = options;

        const loadingMessage = await client.sendMessage(
            chatId,
            "Sip, bahan lengkap & pilihan dicatet. Aku proses dulu ya, sabar..."
        );

        const scriptDir = path.join(__dirname, "DL");
        const pythonScriptPath = path.join(scriptDir, "process_image.py");
        const tempDir = path.join(__dirname, "temp");
        const outputFilename = `output-${Date.now()}.${
            type === "video" ? "mp4" : "png"
        }`;
        const outputAssetPath = path.join(tempDir, outputFilename);

        // --- Build arguments based on user choices ---
        const args = [
            pythonScriptPath,
            "--source",
            sourceImage,
            "--target",
            mainAsset,
            "--output",
            outputAssetPath,
            "--execution-provider",
            "CPUExecutionProvider",
            "--keep-fps",
        ];

        const frameProcessors = ["face_swapper"];
        if (useEnhancer) {
            frameProcessors.push("face_enhancer");
        }
        args.push("--frame-processors", ...frameProcessors);

        if (processManyFaces) {
            args.push("--many-faces");
        }

        if (type === "video") {
            const videoQuality = quality === "high" ? "18" : "23";
            args.push("--video-quality", videoQuality);
        }

        console.log(`Calling Python script with args: ${args.join(" ")}`);
        const pythonProcess = spawn("python", args, { cwd: scriptDir });
        let lastReportedProgress = -1;

        pythonProcess.stdout.on("data", async (data) => {
            const output = data.toString().trim();
            const progressLines = output
                .split("\n")
                .filter((line) => line.startsWith("PROGRESS:"));
            if (progressLines.length === 0) {
                console.log("Python output:", output);
                return;
            }
            const lastProgressLine = progressLines[progressLines.length - 1];
            const currentProgress = parseInt(
                lastProgressLine.split(":")[1],
                10
            );
            if (
                currentProgress > lastReportedProgress + 4 &&
                currentProgress < 100
            ) {
                lastReportedProgress = currentProgress;
                const progressBar = createProgressBar(currentProgress);
                const messageText = `Bentar yaa, AI-nya lagi kerja keras...\n\n${progressBar}\n\nKalo video emang butuh waktu lebih lama sih. Jadi tunggu dulu hehe.`;
                try {
                    await loadingMessage.edit(messageText);
                } catch (editError) {
                    /* Ignore */
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
                if (fs.existsSync(sourceImage))
                    await fs.promises.unlink(sourceImage);
                if (fs.existsSync(mainAsset))
                    await fs.promises.unlink(mainAsset);
            } catch (cleanupError) {
                console.error("Failed to clean up input files:", cleanupError);
            }

            const successful = code === 0 && fs.existsSync(outputAssetPath);
            const noFaceDetected = pythonErrorOutput.includes(
                "No face detected in the source image"
            );

            if (successful) {
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
                    resolve();
                } catch (sendError) {
                    console.error("Error sending message:", sendError);
                    await loadingMessage.edit(
                        "Aduh, filenya gagal kekirim. coba lagi yaa kak."
                    );
                    reject(sendError);
                } finally {
                    if (fs.existsSync(outputAssetPath))
                        await fs.promises.unlink(outputAssetPath);
                    await loadingMessage.delete(true).catch(() => {});
                }
            } else {
                let userErrorMessage =
                    "Waduh, ada error pas proses. Coba lagi ya.";
                if (noFaceDetected) {
                    userErrorMessage =
                        "Mukanya nggak keliatan di foto pertama. Coba pake foto lain deh. Yang lurus ke depan dan jelas ya.";
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

    // History Management
    if (chatHistories[chatId] && chatHistories[chatId].length > 0) {
        if (
            now - chatHistories[chatId][0].timestamp >
            CHAT_HISTORY_TIMEOUT_MS
        ) {
            delete chatHistories[chatId];
        }
    }
    if (!chatHistories[chatId]) chatHistories[chatId] = [];

    // New User Onboarding
    if (!userDB[chatId]) {
        console.log(`New user detected: ${chatId}.`);
        await client.sendMessage(
            chatId,
            "Haloo! Aku bot AI yang bisa tuker muka di foto atau video. Sebelum mulai, datamu di sini aman kok, nggak bakal disalahgunain."
        );
        userDB[chatId] = { firstContact: new Date().toISOString() };
        saveUserDB();
        const welcomeMessage = `Kalo mau bikin, bilang aja, contoh:\n➡️ *"Ubahin wajah di fotoku dongg"*\n\nKetik *!help* buat liat menu bantuan ya.\nKalo mau ngobrol dulu juga boleh!`;
        await client.sendMessage(chatId, welcomeMessage.trim());
        return;
    }

    // Multi-step process with user choices
    if (userStates[chatId]) {
        const currentState = userStates[chatId];

        // Cancellation Logic
        if (!message.hasMedia) {
            const cancelKeywords = ["cancel", "batal", "stop", "gajadi"];
            if (
                cancelKeywords.some((keyword) =>
                    lowerCaseBody.includes(keyword)
                )
            ) {
                await client.sendMessage(
                    chatId,
                    "Oke, prosesnya aku batalin ya. 😊"
                );
                delete userStates[chatId];
                return;
            }
        }

        // State Machine for collecting data and choices
        switch (currentState.state) {
            case "waiting_for_face":
                // FIX: Check message.type to accept both images and stickers.
                if (message.type === "image" || message.type === "sticker") {
                    const media = await message.downloadMedia();
                    // Stickers are often .webp, which is fine for the Python script
                    const filename = `face-${Date.now()}.${
                        media.mimetype.split("/")[1] || "webp"
                    }`;
                    const tempDir = path.join(__dirname, "temp");
                    if (!fs.existsSync(tempDir)) fs.mkdirSync(tempDir);
                    const filepath = path.join(tempDir, filename);
                    fs.writeFileSync(filepath, media.data, {
                        encoding: "base64",
                    });

                    currentState.faceImage = filepath;
                    currentState.state = "waiting_for_target";

                    const assetTypeName =
                        currentState.type === "image" ? "gambar" : "video";
                    await client.sendMessage(
                        chatId,
                        `Sip, foto muka dapet. Sekarang kirim ${assetTypeName} targetnya yaa.`
                    );
                } else {
                    await client.sendMessage(
                        chatId,
                        "Itu bukan foto, hehe. Kirimin foto muka atau stiker yang jelas ya."
                    );
                }
                break;

            case "waiting_for_target":
                // FIX: Check message.type for the target media as well.
                const isCorrectType =
                    currentState.type === message.type ||
                    (currentState.type === "image" &&
                        message.type === "sticker");

                if (message.hasMedia && isCorrectType) {
                    const media = await message.downloadMedia();
                    const filename = `${currentState.type}-${Date.now()}.${
                        media.mimetype.split("/")[1] || "webp"
                    }`;
                    const tempDir = path.join(__dirname, "temp");
                    const filepath = path.join(tempDir, filename);
                    fs.writeFileSync(filepath, media.data, {
                        encoding: "base64",
                    });

                    currentState.mainAsset = filepath;
                    currentState.state = "waiting_for_enhancer_choice";

                    await client.sendMessage(
                        chatId,
                        "Oke, bahan lengkap! Sebelum diproses, aku mau tanya beberapa hal.\n\nMukanya mau dibuat lebih jernih (enhance)? Jawab *'iya'* atau *'ngga'*, hehe."
                    );
                } else {
                    const assetTypeName =
                        currentState.type === "image" ? "gambar" : "video";
                    await client.sendMessage(
                        chatId,
                        `Waduh, salah file. Aku butuhnya ${assetTypeName}. Kirim ulang ya.`
                    );
                }
                break;

            case "waiting_for_enhancer_choice":
                currentState.useEnhancer =
                    lowerCaseBody.includes("iya") ||
                    lowerCaseBody.includes("yes");
                currentState.state = "waiting_for_faces_choice";
                await client.sendMessage(
                    chatId,
                    "Sip, dicatet. Kalo di target ada banyak muka, aku proses *semua* atau *satu* aja? Jawab *'semua'* atau *'satu'*."
                );
                break;

            case "waiting_for_faces_choice":
                currentState.processManyFaces =
                    lowerCaseBody.includes("semua") ||
                    lowerCaseBody.includes("all");
                if (currentState.type === "video") {
                    currentState.state = "waiting_for_quality_choice";
                    await client.sendMessage(
                        chatId,
                        "Oke. Terakhir nih, mau kualitas hasilnya *Biasa* aja atau yang *Bagus*? Kalo bagus, prosesnya bakal lebih lama ya, hehe."
                    );
                } else {
                    try {
                        await runPythonScript(chatId, currentState);
                    } catch (error) {
                        console.error(
                            `Script execution failed for ${chatId}:`,
                            error.message
                        );
                    } finally {
                        delete userStates[chatId];
                    }
                }
                break;

            case "waiting_for_quality_choice":
                currentState.quality =
                    lowerCaseBody.includes("bagus") ||
                    lowerCaseBody.includes("high")
                        ? "high"
                        : "normal";
                try {
                    await runPythonScript(chatId, currentState);
                } catch (error) {
                    console.error(
                        `Script execution failed for ${chatId}:`,
                        error.message
                    );
                } finally {
                    delete userStates[chatId];
                }
                break;

            default:
                await client.sendMessage(
                    chatId,
                    "Lagi nungguin file nih, bukan ketikan. Atau bilang 'batal' kalo ngga jadi."
                );
        }
        return;
    }

    // If not in a process, determine intent
    const intent = await getIntent(lowerCaseBody);
    console.log(`User: "${lowerCaseBody}" -> Intent: ${intent}`);
    chatHistories[chatId].push({
        role: "user",
        content: message.body,
        timestamp: now,
    });

    switch (intent) {
        case "IMAGE":
        case "VIDEO":
            userStates[chatId] = {
                state: "waiting_for_face",
                type: intent.toLowerCase(),
            };
            await client.sendMessage(
                chatId,
                `Oke siap, kita buatin ${intent.toLowerCase()}nya. Kirimin aku satu foto muka kamu yang jelas yaa, biar hasilnya bagus.`
            );
            break;

        case "HELP":
            const helpMessage = `
Halo! Aku bisa bantu kamu buat ganti muka di foto atau video. Ini caranya:

1️⃣ *Mulai Proses*
Bilang aja "buat video" atau "bikin gambar" buat mulai.

2️⃣ *Kirim File*
Aku bakal minta kamu kirim 2 file:
- *Foto Muka*: Foto orang yang mukanya mau dipake (bisa foto biasa atau stiker).
- *File Target*: Foto atau video yang mukanya mau diganti.

3️⃣ *Jawab Pertanyaan*
Setelah file lengkap, aku bakal tanya beberapa hal buat nentuin hasil akhirnya, seperti kualitas video.

*Perintah Lain:*
- *batal/cancel*: Buat batalin proses yang lagi jalan.
- *!help*: Buat nampilin pesan ini lagi.

Santuy aja kalo mau tanya-tanya atau ngobrol dulu! 😊
            `;
            await client.sendMessage(chatId, helpMessage.trim());
            break;

        case "CHITCHAT":
        case "UNKNOWN":
        default:
            try {
                if (Math.random() < 0.3) {
                    const softBoyEmojis = ["👍", "😊", "✨", "🥺", "❤️", "✅"];
                    await message.react(
                        softBoyEmojis[
                            Math.floor(Math.random() * softBoyEmojis.length)
                        ]
                    );
                }
            } catch (e) {
                /* ignore react error */
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
            break;
    }
});

// --- Start The Bot ---
client.initialize();

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
                max_tokens: 10, // Small value is efficient for a single-word reply
                temperature: 0.1, // Low temperature for deterministic classification
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
 * Runs the Python face-swapping script.
 * @param {string} chatId The user's chat ID.
 * @param {string} sourceImagePath Path to the source face image.
 * @param {string} targetAssetPath Path to the target image or video.
 * @param {string} assetType The type of asset, either "image" or "video".
 * @returns {Promise<void>}
 */
async function runPythonScript(
    chatId,
    sourceImagePath,
    targetAssetPath,
    assetType
) {
    return new Promise((resolve, reject) => {
        const scriptDir = path.join(__dirname, "DL"); // Directory of the Python script
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

        // Spawn the process with the correct working directory ('cwd')
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
                    await new Promise((res) => setTimeout(res, 1000)); // Small delay for file system
                    const outputMedia =
                        MessageMedia.fromFilePath(outputAssetPath);
                    await client.sendMessage(chatId, outputMedia, {
                        caption: "Here is your generated media!",
                    });
                    console.log("Successfully sent media to", chatId);
                    resolve();
                } catch (sendError) {
                    console.error("Error sending message:", sendError);
                    reject(sendError);
                } finally {
                    // Clean up the output file after sending
                    if (fs.existsSync(outputAssetPath)) {
                        await fs.promises.unlink(outputAssetPath);
                    }
                }
            } else {
                console.error("Python script failed or output file not found.");
                client.sendMessage(
                    chatId,
                    "Something went wrong during processing. Please try again. 😔"
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

    // Check if the user is already in a process (e.g., has sent the first image)
    if (userStates[chatId]) {
        const currentState = userStates[chatId];

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
                currentState.state = `waiting_for_${currentState.type}`; // Move to next state

                client.sendMessage(
                    chatId,
                    `Face received! 👍 Now, please send the ${currentState.type} you want to put the face on.`
                );
                return;

                // State 2: Waiting for the target image/video
            } else if (
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

                    client.sendMessage(
                        chatId,
                        "Processing your request. This might take a moment... ⏳"
                    );
                    await runPythonScript(
                        chatId,
                        currentState.faceImage,
                        currentState.mainAsset,
                        currentState.type
                    );

                    delete userStates[chatId]; // Reset state after completion
                } else {
                    client.sendMessage(
                        chatId,
                        `That's not the right file type. I was expecting a ${currentState.type}. Please send the correct file.`
                    );
                }
            }
        } else {
            client.sendMessage(
                chatId,
                "I was expecting a file. Please send an image or video."
            );
        }

        // If the user is NOT in a process, use the LLM to understand their initial message
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
                    "Great! Let's make an image. Please send me a picture with a face in it."
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
                    "Great! Let's make a video. Please send me a picture with a face in it."
                );
                break;

            case "UNKNOWN":
            default:
                const welcomeMessage = `
Hello! 👋 I can swap faces in images and videos using AI.

You can ask me things like:
➡️ "Create a face swap image for me"
➡️ "I want to make a video"

Just tell me what you'd like to do to begin!
                `;
                client.sendMessage(chatId, welcomeMessage);
                break;
        }
    }
});

// --- Start The Bot ---
client.initialize();

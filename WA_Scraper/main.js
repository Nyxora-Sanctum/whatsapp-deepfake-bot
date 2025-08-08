const { Client, LocalAuth, MessageMedia, List } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

// Use a local Chrome installation to ensure video processing works correctly.
// Using LocalAuth prevents you from needing to scan the QR code every time.
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: "/usr/bin/google-chrome",
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
});

// This object keeps track of each user's progress
const userStates = {};

client.on("ready", () => {
    console.log("Client is ready!");
});

client.on("qr", (qr) => {
    qrcode.generate(qr, { small: true });
});

client.initialize();

client.on("message", async (message) => {
    const chatId = message.from;
    const lowerCaseBody = message.body.toLowerCase();

    // --- NEW: Trigger the menu only with the "start" command ---
    if (lowerCaseBody === "start") {
        const sections = [
            {
                title: "Available Options",
                rows: [
                    {
                        title: "🖼️ Generate Image",
                        id: "generate_image",
                        description: "Swap a face onto a target image.",
                    },
                    {
                        title: "🎬 Generate Video",
                        id: "generate_video",
                        description: "Swap a face onto a target video.",
                    },
                ],
            },
        ];

        const list = new List(
            "Hello! 👋 I can swap faces in images and videos.\n\nPlease choose an option from the list below.",
            "Choose an option",
            sections,
            "What would you like to do?",
            "Powered by Gemini"
        );

        await client.sendMessage(chatId, list);
        return; // Exit after sending the menu
    }

    // Check if the user is starting a new image generation (from the list selection)
    if (lowerCaseBody === "generate_image") {
        userStates[chatId] = {
            state: "waiting_for_face",
            faceImage: null,
            mainAsset: null,
            type: "image",
        };
        client.sendMessage(
            chatId,
            "Great! Please send me an image with a face in it."
        );
        return;
    }

    // Check if the user is starting a new video generation (from the list selection)
    if (lowerCaseBody === "generate_video") {
        userStates[chatId] = {
            state: "waiting_for_face",
            faceImage: null,
            mainAsset: null,
            type: "video",
        };
        client.sendMessage(
            chatId,
            "Great! Please send me an image with a face in it."
        );
        return;
    }

    // If the user is already in a process, handle their next message
    if (userStates[chatId]) {
        const currentState = userStates[chatId];

        if (message.hasMedia) {
            const media = await message.downloadMedia();
            const mediaType = media.mimetype.split("/")[0];

            // Handle the face image upload
            if (currentState.state === "waiting_for_face") {
                const filename = `face-${Date.now()}.${
                    media.mimetype.split("/")[1]
                }`;
                const tempDir = path.join(__dirname, "temp");
                if (!fs.existsSync(tempDir)) {
                    fs.mkdirSync(tempDir);
                }
                const filepath = path.join(tempDir, filename);

                fs.writeFileSync(filepath, media.data, { encoding: "base64" });
                currentState.faceImage = filepath;
                currentState.state = `waiting_for_${currentState.type}`;

                client.sendMessage(
                    chatId,
                    `Face received! Now, please send the ${currentState.type} you want to put the face on.`
                );
                return;
            }

            // Handle the target image or video upload
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

                    client.sendMessage(
                        chatId,
                        "Processing your request. This might take a moment... ⏳"
                    );

                    console.log(
                        `Calling Python script for ${currentState.type} with:`,
                        currentState.faceImage,
                        currentState.mainAsset
                    );

                    // Run the Python script and wait for it to finish
                    await runPythonScript(
                        chatId,
                        currentState.faceImage,
                        currentState.mainAsset,
                        currentState.type
                    );

                    // Clean up the user's state after finishing
                    delete userStates[chatId];
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
    } else {
        // --- NEW: Handle unknown commands ---
        // If the user isn't in a process and didn't type "start", send a help message.
        client.sendMessage(
            chatId,
            "I'm not sure what you mean. Please type *start* to see the available options."
        );
    }
});

// This function runs the Python script to do the face swapping
async function runPythonScript(
    chatId,
    sourceImagePath,
    targetAssetPath,
    assetType
) {
    return new Promise((resolve, reject) => {
        // Define the directory where the Python script and its 'modules' folder are located
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

        // --- THE FIX: Add the 'cwd' option to set the working directory ---
        const pythonProcess = spawn("python", args, { cwd: scriptDir });

        pythonProcess.stdout.on("data", (data) => {
            console.log("Python output:", data.toString().trim());
        });

        pythonProcess.stderr.on("data", (data) => {
            console.error("Python error:", data.toString().trim());
        });

        pythonProcess.on("close", async (code) => {
            console.log(`Python script finished with code ${code}`);

            // Clean up input files
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
                    await new Promise((resolve) => setTimeout(resolve, 1000));
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
                    // Clean up output file
                    if (fs.existsSync(outputAssetPath)) {
                        await fs.promises.unlink(outputAssetPath);
                    }
                }
            } else {
                console.error("Python script failed or output file not found.");
                client.sendMessage(
                    chatId,
                    "Something went wrong. Please try again."
                );
                reject(new Error("Python script failed."));
            }
        });
    });
}

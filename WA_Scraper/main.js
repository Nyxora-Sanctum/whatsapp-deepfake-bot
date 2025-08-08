const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: "/usr/bin/google-chrome",
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
});

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
    const lowerCaseBody = message.body.toLowerCase().trim();

    // Command to start image generation
    if (lowerCaseBody === "generate_image") {
        userStates[chatId] = {
            state: "waiting_for_face",
            faceImage: null,
            mainAsset: null,
            type: "image",
            // *** NEW: Add a property to store upscale choice ***
            upscaleChoice: null,
        };
        client.sendMessage(
            chatId,
            "Great! Please send me an image with a single, clear face in it."
        );
        return;
    }

    // Command to start video generation
    if (lowerCaseBody === "generate_video") {
        userStates[chatId] = {
            state: "waiting_for_face",
            faceImage: null,
            mainAsset: null,
            type: "video",
            upscaleChoice: null,
        };
        client.sendMessage(
            chatId,
            "Great! Please send me an image with a single, clear face in it."
        );
        return;
    }

    // Handle the user's conversation flow
    if (userStates[chatId]) {
        const currentState = userStates[chatId];

        // State 1: Waiting for the face image
        if (currentState.state === "waiting_for_face" && message.hasMedia) {
            const media = await message.downloadMedia();
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
                `Face received! Now, please send the target ${currentState.type} you want to modify.`
            );
            return;
        }

        // State 2: Waiting for the target image/video
        if (
            currentState.state === `waiting_for_${currentState.type}` &&
            message.hasMedia
        ) {
            const media = await message.downloadMedia();
            const mediaType = media.mimetype.split("/")[0];
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

                // *** NEW: Move to the next state to ask about upscaling ***
                currentState.state = "waiting_for_upscale_choice";
                const upscaleQuestion = `Got it. Do you want to enhance and upscale the result? This will take longer.

Please reply with one of the following:
*- yes 2x* (upscale by a factor of 2)
*- yes 4x* (upscale by a factor of 4)
*- no* (just do the face swap)`;
                client.sendMessage(chatId, upscaleQuestion);
            } else {
                client.sendMessage(
                    chatId,
                    `That's not the right file type. I was expecting a ${currentState.type}. Please send the correct file.`
                );
            }
            return;
        }

        // *** NEW: State 3: Waiting for the user's upscale choice ***
        if (currentState.state === "waiting_for_upscale_choice") {
            if (lowerCaseBody === "yes 2x") {
                currentState.upscaleChoice = { enabled: true, factor: 2 };
            } else if (lowerCaseBody === "yes 4x") {
                currentState.upscaleChoice = { enabled: true, factor: 4 };
            } else if (lowerCaseBody === "no") {
                currentState.upscaleChoice = { enabled: false };
            } else {
                client.sendMessage(
                    chatId,
                    "Sorry, that's not a valid option. Please reply with 'yes 2x', 'yes 4x', or 'no'."
                );
                return;
            }

            client.sendMessage(
                chatId,
                "Processing your request. This might take a moment... ⏳"
            );

            // Now we have all the info, run the script
            await runPythonScript(
                chatId,
                currentState.faceImage,
                currentState.mainAsset,
                currentState.type,
                currentState.upscaleChoice
            );

            // Clean up the user's state after finishing
            delete userStates[chatId];
            return;
        }
    }

    // Default message if no command is matched
    const welcomeMessage = `Hello! 👋 I can swap faces and enhance media.

Here are the commands you can use:

1️⃣ Type *generate_image* to start.
2️⃣ Type *generate_video* to start.`;
    client.sendMessage(chatId, welcomeMessage);
});

// *** CHANGE: This function is updated to handle the new Python script and arguments ***
async function runPythonScript(
    chatId,
    sourceImagePath,
    targetAssetPath,
    assetType,
    upscaleOptions
) {
    return new Promise((resolve, reject) => {
        const scriptDir = path.join(__dirname, "DL");
        // Point to your new Python script
        const pythonScriptPath = path.join(scriptDir, "process_cpu.py");

        const tempDir = path.join(__dirname, "temp");
        const outputFilename = `output-${Date.now()}.${
            assetType === "video" ? "mp4" : "png"
        }`;
        const outputAssetPath = path.join(tempDir, outputFilename);

        // Build the arguments array dynamically based on user's choice
        const args = [
            pythonScriptPath,
            "--source",
            sourceImagePath,
            "--target",
            targetAssetPath,
            "--output",
            outputAssetPath,
        ];

        if (upscaleOptions && upscaleOptions.enabled) {
            args.push("--upscale-factor", String(upscaleOptions.factor));
        } else {
            args.push("--skip-upscale");
        }

        console.log(`Calling Python script with args: ${args.join(" ")}`);

        // Use 'python3' for better compatibility on Linux/macOS
        const pythonProcess = spawn("python3", args, { cwd: scriptDir });

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
                    fs.unlinkSync(sourceImagePath);
                if (fs.existsSync(targetAssetPath))
                    fs.unlinkSync(targetAssetPath);
            } catch (cleanupError) {
                console.error("Failed to clean up input files:", cleanupError);
            }

            if (code === 0 && fs.existsSync(outputAssetPath)) {
                console.log(
                    "Python script successful! Output at:",
                    outputAssetPath
                );
                try {
                    await new Promise((res) => setTimeout(res, 1000));
                    const outputMedia =
                        MessageMedia.fromFilePath(outputAssetPath);
                    await client.sendMessage(chatId, outputMedia, {
                        caption: "Here is your generated media! ✨",
                    });
                    resolve();
                } catch (sendError) {
                    console.error("Error sending message:", sendError);
                    reject(sendError);
                } finally {
                    if (fs.existsSync(outputAssetPath))
                        fs.unlinkSync(outputAssetPath);
                }
            } else {
                client.sendMessage(
                    chatId,
                    "Something went wrong during processing. Please try again."
                );
                reject(new Error(`Python script failed with code ${code}.`));
            }
        });
    });
}

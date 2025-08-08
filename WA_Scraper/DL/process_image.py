import os
import argparse
import cv2
import subprocess
import shutil
import sys
import numpy as np

# --- Core Face-Swapper Imports ---
try:
    import modules.globals
    from modules.face_analyser import get_one_face
    from modules.processors.frame.core import get_frame_processors_modules
    from modules.utilities import is_video
except ImportError as e:
    print(f"Error: A required face-swapper module could not be imported: {e}", file=sys.stderr)
    sys.exit(1)

# --- NEW: Upscaler imports are conditional later in the code ---


def parse_args():
    """Parses command line arguments for the script."""
    program = argparse.ArgumentParser(description="Face swapper and upscaler for images and videos (CPU-only).")
    program.add_argument('-s', '--source', help='Path to the source image with the face', dest='source_path', required=True)
    program.add_argument('-t', '--target', help='Path to the target image or video', dest='target_path', required=True)
    program.add_argument('-o', '--output', help='Path for the output file', dest='output_path', required=True)
    program.add_argument('--execution-provider', help='Execution provider for ONNX runtime', dest='execution_provider', default=['CPUExecutionProvider'], nargs='+')
    
    # --- NEW: Upscaling Arguments ---
    program.add_argument('--skip-upscale', help='Skip the upscaling step entirely', action='store_true')
    program.add_argument('--upscale-factor', help='The factor by which to upscale (2 or 4)', dest='upscale_factor', type=int, default=2, choices=[2, 4])
    
    return program.parse_args()


def process_image(source_path: str, target_path: str, output_path: str, upscaler_model=None):
    """Loads images, performs a face swap, optionally upscales, and saves the output."""
    try:
        from PIL import Image # Conditionally import Pillow

        source_image = cv2.imread(source_path)
        target_image = cv2.imread(target_path)

        if source_image is None or target_image is None:
            print("Error: Could not read one of the image files.", file=sys.stderr)
            return

        source_face = get_one_face(source_image)
        if source_face is None:
            print("Error: No face detected in the source image.", file=sys.stderr)
            return
        
        print("Processing face swap for image...")
        modules.globals.frame_processors = ['face_swapper']
        frame_processors = get_frame_processors_modules(modules.globals.frame_processors)
        processed_frame = frame_processors[0].process_frame(source_face, target_image)
        
        if processed_frame is None:
            print("Error: Face swapping failed.", file=sys.stderr)
            return

        final_frame = processed_frame

        # --- NEW: Upscaling Logic for Image ---
        if upscaler_model:
            print(f"Upscaling image by factor of {upscaler_model.scale}x...")
            # Convert OpenCV BGR image to PIL RGB image
            pil_image = Image.fromarray(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
            # Upscale the image
            upscaled_image = upscaler_model.predict(pil_image)
            # Convert the upscaled PIL image back to an OpenCV BGR image for saving
            final_frame = cv2.cvtColor(np.array(upscaled_image), cv2.COLOR_RGB2BGR)

        cv2.imwrite(output_path, final_frame)
        print(f"Image successfully processed and saved to {output_path}")

    except Exception as e:
        print(f"An error occurred during image processing: {e}", file=sys.stderr)


def process_video(source_path: str, target_path: str, output_path: str, upscaler_model=None, upscale_factor: int = 2):
    """Processes video with face swap and optional frame-by-frame upscaling."""
    from PIL import Image # Conditionally import Pillow
    
    # Use a temporary file for the intermediate video to handle audio separately
    temp_video_path = os.path.splitext(output_path)[0] + '_temp_video.mp4'
    
    try:
        source_image = cv2.imread(source_path)
        if source_image is None:
            print("Error: Could not read the source image file.", file=sys.stderr)
            return

        source_face = get_one_face(source_image)
        if source_face is None:
            print("Error: No face detected in the source image.", file=sys.stderr)
            return
        
        modules.globals.frame_processors = ['face_swapper']
        frame_processors = get_frame_processors_modules(modules.globals.frame_processors)

        cap = cv2.VideoCapture(target_path)
        if not cap.isOpened():
            print(f"Error: Could not open the target video file: {target_path}", file=sys.stderr)
            return

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # --- NEW: Adjust dimensions for upscaling ---
        output_width, output_height = width, height
        if upscaler_model:
            output_width = width * upscale_factor
            output_height = height * upscale_factor
            print(f"Video will be upscaled from {width}x{height} to {output_width}x{output_height}.")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video_path, fourcc, fps, (output_width, output_height))

        print("Processing video frames...")
        frame_number = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_number += 1
            print(f"Processing frame {frame_number}/{frame_count}...", end='\r')
            
            # 1. Face Swap
            processed_frame = frame_processors[0].process_frame(source_face, frame)
            if processed_frame is None:
                processed_frame = frame # Use original frame if swap fails

            final_frame = processed_frame

            # 2. --- NEW: Upscaling Logic for Video Frame ---
            if upscaler_model:
                pil_image = Image.fromarray(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
                upscaled_image = upscaler_model.predict(pil_image)
                final_frame = cv2.cvtColor(np.array(upscaled_image), cv2.COLOR_RGB2BGR)

            out.write(final_frame)

        cap.release()
        out.release()
        print(f"\nVideo processing complete. Merging audio...")

        # --- Use FFmpeg to combine the processed video with the original audio ---
        if shutil.which('ffmpeg'):
            ffmpeg_command = [
                'ffmpeg',
                '-i', temp_video_path,      # Input processed video
                '-i', target_path,          # Input original video (for audio)
                '-c:v', 'libx264',          # Re-encode video for compatibility
                '-crf', '18',               # Good quality setting
                '-preset', 'medium',        # Good balance of speed/compression
                '-c:a', 'copy',             # Copy audio stream without re-encoding
                '-map', '0:v:0',            # Map video from first input
                '-map', '1:a:0?',           # Map audio from second input (optional)
                '-y',                       # Overwrite output file
                output_path
            ]
            subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"Final video with audio saved to {output_path}")
        else:
            print("Warning: ffmpeg not found. Saving video without original audio.", file=sys.stderr)
            shutil.move(temp_video_path, output_path)

    except Exception as e:
        print(f"\nAn error occurred during video processing: {e}", file=sys.stderr)
    finally:
        # --- Clean up the temporary file ---
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        cv2.destroyAllWindows()


def main():
    """Main function to parse arguments and run the processing pipeline."""
    args = parse_args()
    modules.globals.execution_providers = args.execution_provider
    
    upscaler_model = None
    # --- NEW: Initialize the upscaler model once ---
    if not args.skip_upscale:
        print("Initializing upscaler model... (This may take a moment)")
        try:
            import torch
            from realesrgan import RealESRGAN
            
            # Use CPU for the upscaling model
            device = torch.device('cpu')
            upscaler_model = RealESRGAN(device, scale=args.upscale_factor)
            print("Upscaler model loaded successfully.")
        except ImportError:
            print("Error: 'realesrgan' or 'torch' not found. Please install them with 'pip install realesrgan torch'", file=sys.stderr)
            sys.exit(1)

    if is_video(args.target_path):
        process_video(args.source_path, args.target_path, args.output_path, upscaler_model, args.upscale_factor)
    else:
        process_image(args.source_path, args.target_path, args.output_path, upscaler_model)


if __name__ == '__main__':
    main()
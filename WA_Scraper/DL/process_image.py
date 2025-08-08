import os
import sys
import argparse
import cv2
import subprocess
import shutil
import multiprocessing

# --- Core Application Imports ---
try:
    import modules.globals
    from modules.face_analyser import get_one_face
    from modules.processors.frame.core import get_frame_processors_modules
    from modules.utilities import is_video
except ImportError as e:
    print(f"Error: A required module could not be imported: {e}", file=sys.stderr)
    print("Please ensure you are running this script from the correct directory and all dependencies are installed.", file=sys.stderr)
    sys.exit(1)

def parse_args():
    """Parses command line arguments for the enhanced script."""
    program = argparse.ArgumentParser(description="High-quality face swapper and enhancer for images and videos.")
    
    # --- Basic Arguments ---
    program.add_argument('-s', '--source', help='Path to the source image with the face', dest='source_path', required=True)
    program.add_argument('-t', '--target', help='Path to the target image or video', dest='target_path', required=True)
    program.add_argument('-o', '--output', help='Path for the output file', dest='output_path', required=True)
    
    # --- Quality & Feature Arguments ---
    program.add_argument('--frame-processors', help='Processors to use (face_swapper, face_enhancer)', dest='frame_processors', default=['face_swapper'], nargs='+')
    program.add_argument('--video-encoder', help='Adjust output video encoder', dest='video_encoder', default='libx264', choices=['libx264', 'libx265', 'libvpx-vp9'])
    program.add_argument('--video-quality', help='Adjust output video quality (0-51, lower is better)', dest='video_quality', type=int, default=18)
    
    # --- Performance & Resource Arguments ---
    program.add_argument('--execution-provider', help='Execution provider for ONNX runtime', dest='execution_provider', default=['cpu'], nargs='+')
    program.add_argument('--execution-threads', help='Number of execution threads', dest='execution_threads', type=int, default=multiprocessing.cpu_count())
    program.add_argument('--max-memory', help='Maximum amount of RAM in GB to use', dest='max_memory', type=int, default=6)
    
    return program.parse_args()


def process_frames(source_face, temp_frame, frame_processors):
    """Helper function to apply a sequence of frame processors."""
    for processor in frame_processors:
        temp_frame = processor.process_frame(
            source_face=source_face,
            temp_frame=temp_frame
        )
    return temp_frame


def process_image(args, frame_processors):
    """Loads images, performs processing, and saves the output."""
    try:
        source_image = cv2.imread(args.source_path)
        target_image = cv2.imread(args.target_path)

        if source_image is None or target_image is None:
            print("Error: Could not read one of the image files.", file=sys.stderr)
            return

        source_face = get_one_face(source_image)
        if source_face is None:
            print("Error: No face detected in the source image.", file=sys.stderr)
            return
        
        print("Processing image with:", ', '.join(args.frame_processors))
        result = process_frames(source_face, target_image, frame_processors)
        
        if result is None:
            print("Error: Image processing failed.", file=sys.stderr)
            return

        cv2.imwrite(args.output_path, result)
        print(f"Image successfully processed and saved to {args.output_path}")

    except Exception as e:
        print(f"An error occurred during image processing: {e}", file=sys.stderr)


def process_video(args, frame_processors):
    """Processes video with face swap, enhancement, and high-quality encoding."""
    if not shutil.which('ffmpeg'):
        print("Error: FFmpeg is not installed or not in the system's PATH.", file=sys.stderr)
        return
    
    # Define temporary paths
    temp_dir = os.path.join(os.path.dirname(args.output_path), 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    temp_video_path = os.path.join(temp_dir, os.path.basename(args.output_path))
    
    try:
        source_image = cv2.imread(args.source_path)
        if source_image is None:
            print("Error: Could not read the source image file.", file=sys.stderr)
            return

        source_face = get_one_face(source_image)
        if source_face is None:
            print("Error: No face detected in the source image.", file=sys.stderr)
            return
        
        cap = cv2.VideoCapture(args.target_path)
        if not cap.isOpened():
            print(f"Error: Could not open the target video file: {args.target_path}", file=sys.stderr)
            return

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video_path, fourcc, fps, (width, height))

        print(f"Processing {frame_count} video frames with: {', '.join(args.frame_processors)}...")
        frame_number = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_number += 1
            print(f"Processing frame {frame_number}/{frame_count}...", end='\r')
            
            processed_frame = process_frames(source_face, frame, frame_processors)
            out.write(processed_frame if processed_frame is not None else frame)

        cap.release()
        out.release()
        print(f"\nFrame processing complete. Starting final video encoding...")

        # Build the high-quality FFmpeg command
        ffmpeg_command = [
            'ffmpeg',
            '-i', temp_video_path,
            '-i', args.target_path,
            '-c:v', args.video_encoder,
            '-crf', str(args.video_quality),
            '-preset', 'medium',
            '-c:a', 'copy',
            '-map', '0:v:0',
            '-map', '1:a:0?',
            '-threads', str(args.execution_threads),
            '-y',
            args.output_path
        ]
        
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"Video successfully processed and saved to {args.output_path}")

    except Exception as e:
        print(f"\nAn error occurred during video processing: {e}", file=sys.stderr)
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        cv2.destroyAllWindows()


def main():
    """Main function to parse arguments and run the processing pipeline."""
    args = parse_args()

    # Set global settings for the face processing modules
    modules.globals.execution_providers = args.execution_provider
    modules.globals.execution_threads = args.execution_threads
    modules.globals.max_memory = args.max_memory
    
    # Load the requested frame processors
    frame_processors = get_frame_processors_modules(args.frame_processors)
    
    if is_video(args.target_path):
        process_video(args, frame_processors)
    else:
        process_image(args, frame_processors)


if __name__ == '__main__':
    main()
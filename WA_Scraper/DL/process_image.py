import os
import argparse
import cv2
import subprocess
import shutil

# --- Core Application Imports ---
# These are assumed to be part of your project structure (e.g., roop).
# Make sure these modules are available in your environment.
try:
    import modules.globals
    from modules.face_analyser import get_one_face
    from modules.processors.frame.core import get_frame_processors_modules
    from modules.utilities import is_video
except ImportError as e:
    print(f"Error: A required module could not be imported: {e}")
    print("Please ensure you are running this script from the correct directory and all dependencies are installed.")
    exit(1)

def parse_args():
    """Parses command line arguments for the script."""
    program = argparse.ArgumentParser(description="Face swapper for images and videos.")
    program.add_argument('-s', '--source', help='Path to the source image with the face', dest='source_path', required=True)
    program.add_argument('-t', '--target', help='Path to the target image or video', dest='target_path', required=True)
    program.add_argument('-o', '--output', help='Path for the output file', dest='output_path', required=True)
    program.add_argument('--execution-provider', help='Execution provider(s) for ONNX runtime (e.g., CUDAExecutionProvider, CPUExecutionProvider)', dest='execution_provider', default=['CUDAExecutionProvider'], nargs='+')
    return program.parse_args()
    
def process_image(source_path: str, target_path: str, output_path: str):
    """Loads images, performs a face swap, and saves the output."""
    try:
        source_image = cv2.imread(source_path)
        target_image = cv2.imread(target_path)

        if source_image is None or target_image is None:
            print("Error: Could not read one of the image files.")
            return

        source_face = get_one_face(source_image)
        if source_face is None:
            print("Error: No face detected in the source image.")
            return
        
        modules.globals.frame_processors = ['face_swapper']
        frame_processors = get_frame_processors_modules(modules.globals.frame_processors)
                
        processed_frame = frame_processors[0].process_frame(source_face, target_image)
        
        if processed_frame is None:
            print("Error: Face swapping failed.")
            return

        cv2.imwrite(output_path, processed_frame)
        print(f"Image successfully processed and saved to {output_path}")

    except Exception as e:
        print(f"An error occurred during image processing: {e}")

def process_video(source_path: str, target_path: str, output_path: str):
    """
    Creates a video with the 'mp4v' codec and then converts it to H.264 using FFmpeg for maximum compatibility.
    """
    # --- NEW: Check for FFmpeg before starting ---
    if not shutil.which('ffmpeg'):
        print("Error: FFmpeg is not installed or not found in the system's PATH.")
        print("Please install FFmpeg to use the video processing feature.")
        return
        
    # Define a temporary path for the initial video file
    temp_output_path = os.path.splitext(output_path)[0] + '_temp.mp4'

    try:
        source_image = cv2.imread(source_path)
        if source_image is None:
            print("Error: Could not read the source image file.")
            return

        source_face = get_one_face(source_image)
        if source_face is None:
            print("Error: No face detected in the source image.")
            return
        
        modules.globals.frame_processors = ['face_swapper']
        frame_processors = get_frame_processors_modules(modules.globals.frame_processors)

        cap = cv2.VideoCapture(target_path)
        if not cap.isOpened():
            print(f"Error: Could not open the target video file: {target_path}")
            return

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # --- STEP 1: Write to a temporary file using the reliable 'mp4v' codec ---
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

        print("Processing video (Step 1/2: Initial creation)...")
        frame_number = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_number += 1
            print(f"Processing frame {frame_number}...", end='\r')
            processed_frame = frame_processors[0].process_frame(source_face, frame)

            out.write(processed_frame if processed_frame is not None else frame)

        cap.release()
        out.release()
        print(f"\nStep 1 complete. Temporary file saved to {temp_output_path}")

# --- STEP 2: Convert the temporary file to H.264 using FFmpeg ---
        print("Processing video (Step 2/2: Converting to H.264)...")
        ffmpeg_command = [
            'ffmpeg',
            '-i', temp_output_path,      # Input file
            '-vcodec', 'libx264',       # Video codec: H.264
            '-crf', '15',               # CHANGED: Lower for higher quality (e.g., 18)
            '-preset', 'medium',        # CHANGED: Slower for better compression
            '-y',                       # Overwrite output file if it exists
            output_path                 # Final output file path
        ]
        
        # Use DEVNULL to hide FFmpeg's verbose output from the console
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"Step 2 complete. Final video saved to {output_path}")

    except Exception as e:
        print(f"\nAn error occurred during video processing: {e}")
    finally:
        # --- Clean up the temporary file ---
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
            print(f"Cleaned up temporary file: {temp_output_path}")
        cv2.destroyAllWindows()


def main():
    """Main function to parse arguments and decide whether to process an image or a video."""
    args = parse_args()

    modules.globals.execution_providers = args.execution_provider
    
    if is_video(args.target_path):
        print("Detected video target. Starting video processing.")
        process_video(args.source_path, args.target_path, args.output_path)
    else:
        print("Detected image target. Starting image processing.")
        process_image(args.source_path, args.target_path, args.output_path)

if __name__ == '__main__':
    main()

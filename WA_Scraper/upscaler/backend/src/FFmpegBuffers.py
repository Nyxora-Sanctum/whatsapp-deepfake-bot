import queue
from abc import ABC, abstractmethod
import os
import subprocess
import queue
import sys
import time

from .constants import FFMPEG_PATH, FFMPEG_LOG_FILE
from .utils.Util import (
    log,
    printAndLog,
    subprocess_popen_without_terminal
)
from .utils.Encoders import  EncoderSettings

class Buffer(ABC):
    @abstractmethod
    def command(self) -> list[str]:
        pass


class FFmpegRead(Buffer):
    def __init__(self, inputFile, width, height, start_time, end_time, borderX, borderY, hdr_mode, color_space=None):
        self.inputFile = inputFile
        self.width = width
        self.height = height
        self.start_time = start_time
        self.end_time = end_time
        self.borderX = borderX
        self.borderY = borderY
        self.hdr_mode = hdr_mode
        self.color_space = color_space

        if self.hdr_mode:
            self.inputFrameChunkSize = width * height * 6
        else:
            self.inputFrameChunkSize = width * height * 3

        self.readProcess = subprocess_popen_without_terminal(
            self.command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.readQueue = queue.Queue(maxsize=25)

    def command(self):
        log("Generating FFmpeg READ command...")
        
        
        command = [
            f"{FFMPEG_PATH}",
            "-i",
            f"{self.inputFile}",
        ]
        
        if self.color_space is not None:
            command += [
                "-colorspace",
                self.color_space,
            ]
            

        command += [
            "-vf",
            f"crop={self.width}:{self.height}:{self.borderX}:{self.borderY},scale=w=iw*sar:h=ih", # fix when DAR does not match SAR https://github.com/TNTwise/REAL-Video-Enhancer/issues/63
            "-f",
            "image2pipe",
            "-pix_fmt",
            "rgb48le" if self.hdr_mode else "rgb24",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{self.width}x{self.height}",
            "-ss",
            str(self.start_time),
            "-to",
            str(self.end_time),
            "-"
            
        ]

        log("FFMPEG READ COMMAND: " + str(command))
        return command

    def read_frame(self):
        chunk = self.readProcess.stdout.read(self.inputFrameChunkSize)
        if len(chunk) < self.inputFrameChunkSize:
            return None
        return chunk

    def read_frames_into_queue(self):
        while True:
            chunk = self.read_frame()
            if chunk is None:
                break
            self.readQueue.put(chunk)
        self.readQueue.put(None)

    def get(self):
        return self.readQueue.get()

    def close(self):
        self.readProcess.stdout.close()
        self.readProcess.terminate()


class FFmpegWrite(Buffer):
    def __init__(
        self,
        inputFile: str,
        outputFile: str,
        width: int,
        height: int,
        start_time: float,
        end_time: float,
        fps: float,
        crf: str,
        audio_bitrate: str,
        pixelFormat: str,
        overwrite: bool,
        custom_encoder: str,
        benchmark: bool,
        slowmo_mode: bool,
        upscaleTimes: int,
        interpolateFactor:int,
        ceilInterpolateFactor: int,
        video_encoder: EncoderSettings,
        audio_encoder: EncoderSettings,
        subtitle_encoder: EncoderSettings,
        hdr_mode: bool,
        mpv_output: bool,
        merge_subtitles: bool,
        color_space: str = None,
    ):
        self.inputFile = inputFile
        self.outputFile = outputFile
        if self.outputFile:
            self.outputFileExtension = os.path.split(self.outputFile)[-1].split(".")[-1]
        self.width = width
        self.height = height
        self.start_time = start_time
        self.end_time = end_time
        self.outputWidth = width * upscaleTimes
        self.outputHeight = height * upscaleTimes
        self.fps = fps
        self.crf = crf
        self.audio_bitrate = audio_bitrate
        self.pixelFormat = pixelFormat
        self.overwrite = overwrite
        self.custom_encoder = custom_encoder
        self.benchmark = benchmark
        self.slowmo_mode = slowmo_mode
        self.upscaleTimes = upscaleTimes
        self.interpolateFactor = interpolateFactor
        self.ceilInterpolateFactor = ceilInterpolateFactor
        self.video_encoder = video_encoder
        self.audio_encoder = audio_encoder
        self.subtitle_encoder = subtitle_encoder
        self.mpv_output = mpv_output
        self.hdr_mode = hdr_mode
        self.writeQueue = queue.Queue(maxsize=25)
        self.previewFrame = None
        self.framesRendered: int = 1
        self.writeProcess = None
        self.color_space = color_space
        self.merge_subtitles = merge_subtitles
        log(f"FFmpegWrite parameters: inputFile={inputFile}, outputFile={outputFile}, width={width}, height={height}, start_time={start_time}, end_time={end_time}, fps={fps}, crf={crf}, audio_bitrate={audio_bitrate}, pixelFormat={pixelFormat}, overwrite={overwrite}, custom_encoder={custom_encoder}, benchmark={benchmark}, slowmo_mode={slowmo_mode}, upscaleTimes={upscaleTimes}, interpolateFactor={interpolateFactor}, ceilInterpolateFactor={ceilInterpolateFactor}, video_encoder={video_encoder}, audio_encoder={audio_encoder}, subtitle_encoder={subtitle_encoder}, hdr_mode={hdr_mode}, mpv_output={mpv_output}, merge_subtitles={merge_subtitles}")
        self.outputFPS = (
            (self.fps * self.interpolateFactor)
            if not self.slowmo_mode
            else self.fps
        )
        self.ffmpeg_log = open(FFMPEG_LOG_FILE, "w", encoding='utf-8')
        try:

            self.writeProcess = subprocess_popen_without_terminal(
                self.command(),
                stdin=subprocess.PIPE,
                stderr=self.ffmpeg_log,
                stdout=subprocess.PIPE if self.mpv_output else self.ffmpeg_log,
                text=True,
                universal_newlines=True,
            )
        except Exception as e:
            self.onErroredExit()


    def command(self):
        log("Generating FFmpeg WRITE command...")

        if self.mpv_output:
            command = [
                f"{FFMPEG_PATH}",
                "-loglevel",
                "error",
                "-framerate",
                f"{self.fps*self.ceilInterpolateFactor}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb48le" if self.hdr_mode else "rgb24",
                "-vcodec",
                "rawvideo",
                "-s",
                f"{self.outputWidth}x{self.outputHeight}",
                "-i",
                "-",
                "-to",
                str(self.end_time-self.start_time),
                "-r",
                f"{self.outputFPS}",
                "-f",
                "matroska",

                "-af",
                f"atrim=start={self.start_time},asetpts=PTS-STARTPTS",

            ]
            
            
            if self.hdr_mode:

                # override pixel format
                pxfmtdict = {
                    "yuv420p": "yuv420p10le",
                    "yuv422": "yuv422p10le",
                    "yuv444": "yuv444p10le",
                }

                if self.pixelFormat in pxfmtdict:
                    self.pixelFormat = pxfmtdict[self.pixelFormat]
                
                
                
                
                command += [
                    "-pix_fmt",
                    self.pixelFormat,
                ]

                color_primaries = ["bt709", "bt2020", "bt2020nc"]
                
            command += [
                "-",
            ]
            log("FFMPEG WRITE COMMAND: " + str(command))
            return command


        if not self.benchmark:
            # maybe i can split this so i can just use ffmpeg normally like with vspipe
            command = [
                f"{FFMPEG_PATH}",
                "-loglevel",
                "error",
            ]

            if self.custom_encoder is None:
                pre_in_set = self.video_encoder.getPreInputSettings()
                if pre_in_set is not None:
                    command += pre_in_set.split()

            command += [
                "-framerate",
                f"{self.fps*self.interpolateFactor}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb48le" if self.hdr_mode else "rgb24",
                "-vcodec",
                "rawvideo",
                "-s",
                f"{self.outputWidth}x{self.outputHeight}",
                "-i",
                "-",
                "-r",
                f"{self.outputFPS}",
            ]

            if not self.slowmo_mode:
                command += [
                    "-i",
                    f"{self.inputFile}",
                    "-map",
                    "0:v",  # Map video stream from input 0
                    "-map",
                    "1:a?",

                ]
                if self.merge_subtitles:
                    command += [
                    "-map",
                    "1:s?",]  # Map all subtitle streams from input 1, this sometimes causes issues with some older videos and messes up the audio somehow
                command += self.audio_encoder.getPostInputSettings().split()
                command += self.subtitle_encoder.getPostInputSettings().split()


            if self.color_space is not None:
                command += [
                    "-colorspace",
                    self.color_space,
                ]

            # color_primaries = ["bt709", "bt2020", "bt2020nc"]
            
                
            if self.custom_encoder is not None:
                for i in self.custom_encoder.split():
                    command.append(i)
                log(f"Custom Encoder Settings: {self.custom_encoder}")
            else:
                if not self.audio_encoder.getPresetTag() == "copy_audio":
                    command += [
                        "-b:a",
                        self.audio_bitrate,
                    ]
                command += self.video_encoder.getPostInputSettings().split()
                command += [self.video_encoder.getQualityControlMode(), str(self.crf)]
                
                if self.hdr_mode:
                    
                    encoder_tags = ["libx265", "x265_nvenc"]
                    if self.video_encoder.getPresetTag() not in encoder_tags:
                        print("\n\nHDR mode is enabled, but the encoder does not support HDR. Please use libx265 for HDR.\n",file=sys.stderr)
                        os._exit(1)

                    # override pixel format
                    pxfmtdict = {
                        "yuv420p": "yuv420p10le",
                        "yuv422": "yuv422p10le",
                        "yuv444": "yuv444p10le",
                    }

                    if self.pixelFormat in pxfmtdict:
                        self.pixelFormat = pxfmtdict[self.pixelFormat]

                    if self.video_encoder.getPresetTag() == "libx265" or self.video_encoder.getPresetTag() == "x265_nvenc":
                        command += [
                            "-x265-params",
                                "hdr-opt=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                        ]
                    elif self.video_encoder.getPresetTag() == "prores":
                        command += [
                            "-profile:v",
                            "4",
                            "-vendor",
                            "ap10",
                            "-color_range",
                            "full",
                        ]

                log(f"Video Encoder: {self.video_encoder.getEncoder()}")
                log(f"Video Pixel Format: {self.pixelFormat}")
                log(f"Audio Enocder: {self.audio_encoder.getEncoder()}")
                log(f"Subtitle Enocder: {self.subtitle_encoder.getEncoder()}")
                command += [
                    "-pix_fmt",
                    self.pixelFormat,

                ]
            command +=[
                "-to",
                str(self.end_time-self.start_time),
                f"{self.outputFile}",
            ]

            if self.overwrite:
                command.append("-y")

            log("Output Video Information:")
            log(f"Resolution: {self.outputWidth}x{self.outputHeight}")
            log(f"FPS: {self.outputFPS}")
            if self.slowmo_mode:
                log("Slowmo mode enabled, will not merge audio or subtitles.")

        else: # Benchmark mode

            command = [
                f"{FFMPEG_PATH}",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stats",
                "-f",
                "rawvideo",
                "-vcodec",
                "rawvideo",
                "-to",
                str(self.end_time-self.start_time),
                "-video_size",
                f"{self.width * self.upscaleTimes}x{self.upscaleTimes * self.height}",
                "-pix_fmt",
                "rgb48le" if self.hdr_mode else "rgb24",
                "-r",
                str(self.outputFPS),
                "-i",
                "-",
                "-benchmark",
                "-f",
                "null",
                "-",
            ]

        log("FFMPEG WRITE COMMAND: " + str(command))
        return command

    def get_num_frames_rendered(self):
        return self.framesRendered

    def put_frame_in_write_queue(self, frame):
        
        self.writeQueue.put(frame)

    def write_out_frames(self):
        """
        Writes out frames either to ffmpeg or to pipe
        This is determined by the --output command, which if the PIPE parameter is set, it outputs the chunk to pipe.
        A command like this is required,
        ffmpeg -f rawvideo -pix_fmt rgb48 -s 1920x1080 -framerate 24 -i - -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a copy out.mp4
        """
        log("Rendering")
        self.startTime = time.time()

        exit_code: int = 0
        try:
            while True:
                frame = self.writeQueue.get()
                if frame is None:
                    break
                """if len(frame) < self.outputWidth * self.outputHeight * 3:
                    print("Frame is too small, skipping...", file=sys.stderr)
                    continue"""
                self.writeProcess.stdin.buffer.write(frame)

            self.writeProcess.stdin.close()
            self.writeProcess.wait()
            exit_code = self.writeProcess.returncode

            renderTime = time.time() - self.startTime

            printAndLog(f"\nTime to complete render: {round(renderTime, 2)}")
        except Exception as e:
            print(str(e), file=sys.stderr)
            self.onErroredExit()

        if exit_code != 0:
            self.onErroredExit()
            return




    def onErroredExit(self):
        print("FFmpeg failed to render the video.", file=sys.stderr)
        try:
            with open(FFMPEG_LOG_FILE, "r") as f:
                print("FULL FFMPEG LOG:", file=sys.stderr)
                for line in f.readlines():
                    print(line, file=sys.stderr)

            with open(FFMPEG_LOG_FILE, "r") as f:
                for line in f.readlines():
                    if f"[{self.outputFileExtension}" in line:
                        print(line, file=sys.stderr)

            if self.video_encoder.getPresetTag() == "x264_vulkan":
                print("Vulkan encode failed, try restarting the render.", file=sys.stderr)
                print(
                    "Make sure you have the latest drivers installed and your GPU supports vulkan encoding.",
                    file=sys.stderr,
                )
        except Exception as e:
            print("Failed to read FFmpeg log file.", file=sys.stderr)
            print(str(e), file=sys.stderr)

        time.sleep(1)
        os._exit(1)

    def __del__(self):
        self.ffmpeg_log.close()

class MPVOutput:
    def __init__(self, FFMpegWrite: FFmpegWrite,width,height,fps, outputFrameChunkSize):
        self.proc = None
        self.startTime = time.time()
        self.FFMPegWrite = FFMpegWrite
        self.outputFrameChunkSize = outputFrameChunkSize
        self.width = width
        self.height = height
        self.fps = fps


    def command(self):
        command = [
        "mpv",
        f"--audio-file={self.FFMPegWrite.inputFile}",
        "--no-config",
        "--cache=yes",
        "--cache-secs=5",                    # Cache 30 seconds of video
        "--demuxer-max-bytes=500Mib",         # Increase max bytes
        "--demuxer-readahead-secs=5",        # Read ahead 30 seconds
        "--demuxer-seekable-cache=yes",       # Enable seekable cache
        "--stream-buffer-size=500MiB",        # Increase buffer size
        "--hr-seek-framedrop=no",            # Prevent frame dropping during seeks
        "-"
        ]
        return command

    def write_out_frames(self):
        with open('mpv_log.txt', "w") as f:
            while not self.FFMPegWrite.writeProcess:
                time.sleep(1)
            self.proc = subprocess_popen_without_terminal(
                self.command(),
                stdin=self.FFMPegWrite.writeProcess.stdout,
                stderr=f,
                stdout=f,
            )
            self.FFMPegWrite.writeProcess.stdout.close()
            self.proc.wait()
            self.stop()
            os._exit(0) # force exit

    def stop(self):
        """
        Stop mpv by closing stdin.
        """
        if self.proc:
            self.proc.terminate()
            self.proc.wait()

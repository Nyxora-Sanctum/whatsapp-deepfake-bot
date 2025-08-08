import subprocess
import re
from typing import List
from .Util import log, subprocess_popen_without_terminal
from .constants import FFMPEG_PATH

class FFMpegInfoWrapper:
    def __init__(self, input_file: str):
        self.input_file = input_file
        self._get_ffmpeg_info()

    def _get_ffmpeg_info(self):
        command = [
                FFMPEG_PATH,
                "-i",
                self.input_file,
                "-t",
                "00:00:00",
                "-f",
                "null",
                "/dev/null",
                "-hide_banner",
                "-v",
                "debug"
                
        ]

        self.ffmpeg_output:str = subprocess_popen_without_terminal(command,  stderr=subprocess.PIPE, errors="replace").stderr.read().lower().strip()

    def get_duration_seconds(self) -> float:
        total_duration:float = 0.0

        duration = re.search(r"duration: (.*?),", self.ffmpeg_output).groups()[0]
        hours, minutes, seconds = duration.split(":")
        total_duration += int(int(hours) * 3600)
        total_duration += int(int(minutes) * 60)
        total_duration += float(seconds)
        return round(total_duration, 2)

    def get_total_frames(self) -> int:
        return int(self.get_duration_seconds() * self.get_fps())

    def get_width_x_height(self) -> List[int]:
        width, height = re.search(r"video:.* (\d+)x(\d+)", self.ffmpeg_output).groups()[:2]
        return [int(width), int(height)]

    def get_fps(self) -> float:
        fps = re.search(r"(\d+\.?\d*) fps", self.ffmpeg_output).groups()[0]
        return float(fps)

    def get_bitrate(self) -> int:
        bitrate = re.search(r"bitrate: (\d+)", self.ffmpeg_output)
        if bitrate:
            return int(bitrate.groups()[0])
        return 0

    def get_codec(self) -> str:
        codec = re.search(r"video: (\w+)", self.ffmpeg_output)
        if codec:
            return codec.groups()[0]
        return "unknown"

class VideoLoader:
    def __init__(self, inputFile):
        self.inputFile = inputFile

    def loadVideo(self):
        log(f"Loading video file: {self.inputFile}")
        self.ffmpeg_info = FFMpegInfoWrapper(self.inputFile)

    def isValidVideo(self):
        try:
            log(f"Checking if video file is valid: {self.inputFile}")
            disabled_extensions = ["txt", "jpg", "jpeg", "png", "bmp", "webp"]
            file_extension = self.inputFile.split(".")[-1].lower()
            return self.ffmpeg_info.get_total_frames() > 1 and \
                    file_extension not in disabled_extensions
        except Exception as e:
            log(f"Error checking video validity: {e}")
            return False

    def getData(self):
        self.width, self.height = self.ffmpeg_info.get_width_x_height()
        
        self.bitrate = self.ffmpeg_info.get_bitrate()
        self.videoContainer = self.inputFile.split(".")[-1]
        self.codec_str = self.ffmpeg_info.get_codec()
       
        self.fps = self.ffmpeg_info.get_fps()
        self.total_frames = int(self.ffmpeg_info.get_total_frames())
        self.duration = self.total_frames / self.fps

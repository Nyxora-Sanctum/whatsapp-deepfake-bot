
class FFMpegCommand:
    def __init__(self,
                 video_encoder: str,
                 video_quality: str,
                 video_pixel_format: str,
                 audio_encoder: str,
                 audio_bitrate: str,
                 subtitle_encoder: str):
        self._video_encoder = video_encoder
        self._video_quality = video_quality
        self._video_pixel_format = video_pixel_format
        self._audio_encoder = audio_encoder
        self._audio_bitrate = audio_bitrate
        self._subtitle_encoder = subtitle_encoder

        

    def build_command(self):
        command = []
        match self._video_encoder:
            case "libx264":
                command +=["-c:v","libx264"]
                match self._video_quality:
                    case "Very High":
                        command +=["-crf","15"]
                    case "High":
                        command +=["-crf","18"]
                    case "Medium":
                        command +=["-crf","23"]
                    case "Low":
                        command +=["-crf","28"]
                
                
            case "libx265":
                command +=["-c:v","libx265"]
                match self._video_quality:
                    case "Very High":
                        command +=["-crf","15"]
                    case "High":
                        command +=["-crf","18"]
                    case "Medium":
                        command +=["-crf","23"]
                    case "Low":
                        command +=["-crf","28"]
                
            case "vp9":
                command +=["-c:v","libvpx-vp9"]
                match self._video_quality:
                    case "Very High":
                        command +=["-cq:v","15"]
                    case "High":
                        command +=["-cq:v","18"]
                    case "Medium":
                        command +=["-cq:v","23"]
                    case "Low":
                        command +=["-cq:v","28"]
            case "av1":
                command +=["-c:v","libsvtav1"]
                match self._video_quality:
                    case "Very High":
                        command +=["-cq:v","15"]
                    case "High":
                        command +=["-cq:v","18"]
                    case "Medium":
                        command +=["-cq:v","23"]
                    case "Low":
                        command +=["-cq:v","28"]
            case "ffv1":
                command +=["-c:v","ffv1"]
                match self._video_quality:
                    case "Very High":
                        command +=["-level","3"]
                    case "High":
                        command +=["-level","4"]
                    case "Medium":
                        command +=["-level","5"]
                    case "Low":
                        command +=["-level","6"]
            case "prores":
                command +=["-c:v","prores_ks"]
                match self._video_quality:
                    case "Very High":
                        command +=["-profile:v","3"]
                    case "High":
                        command +=["-profile:v","2"]
                    case "Medium":
                        command +=["-profile:v","1"]
                    case "Low":
                        command +=["-profile:v","0"]
            case "x264_vulkan":
                command +=["-c:v","h264_vulkan"]
                command +=["-quality","0"]
            case "x264_nvenc":
                command +=["-c:v","h264_nvenc"]
                match self._video_quality:
                    case "Very High":
                        command +=["-cq:v","15"]
                    case "High":
                        command +=["-cq:v","18"]
                    case "Medium":
                        command +=["-cq:v","23"]
                    case "Low":
                        command +=["-cq:v","28"]
            case "x265_nvenc":
                command +=["-c:v","hevc_nvenc"]
                match self._video_quality:
                    case "Very High":
                        command +=["-cq:v","15"]
                    case "High":
                        command +=["-cq:v","18"]
                    case "Medium":
                        command +=["-cq:v","23"]
                    case "Low":
                        command +=["-cq:v","28"]
            case "av1_nvenc":
                command +=["-c:v","av1_nvenc"]
                match self._video_quality:
                    case "Very High":
                        command +=["-cq:v","15"]
                    case "High":
                        command +=["-cq:v","18"]
                    case "Medium":
                        command +=["-cq:v","23"]
                    case "Low":
                        command +=["-cq:v","28"]
            case "h264_vaapi":
                command +=["-c:v","h264_vaapi"]
                match self._video_quality:
                    case "Very High":
                        command +=["-crf","15"]
                    case "High":
                        command +=["-crf","18"]
                    case "Medium":
                        command +=["-crf","23"]
                    case "Low":
                        command +=["-crf","28"]
            case "h265_vaapi":
                command +=["-c:v","hevc_vaapi"]
                match self._video_quality:
                    case "Very High":
                        command +=["-crf","15"]
                    case "High":
                        command +=["-crf","18"]
                    case "Medium":
                        command +=["-crf","23"]
                    case "Low":
                        command +=["-crf","28"]
            case "av1_vaapi":
                command +=["-c:v","av1_vaapi"]
                match self._video_quality:
                    case "Very High":
                        command +=["-crf","15"]
                    case "High":
                        command +=["-crf","18"]
                    case "Medium":
                        command +=["-crf","23"]
                    case "Low":
                        command +=["-crf","28"]

            case _:
                command +=["-c:v","libx264"]
                match self._video_quality:
                    case "Very High":
                        command +=["-crf","15"]
                    case "High":
                        command +=["-crf","18"]
                    case "Medium":
                        command +=["-crf","23"]
                    case "Low":
                        command +=["-crf","28"]
        
        command += ["-pix_fmt",self._video_pixel_format]

        match self._audio_encoder:
            case "copy_audio":
                command +=["-c:a","copy"]
            case "aac":
                command +=["-c:a","aac"]
            case "libmp3lame":
                command +=["-c:a","libmp3lame"]
            case "opus":
                command +=["-c:a","libopus"]
            case _:
                command +=["-c:a","copy"]
        
        if self._audio_encoder != "copy_audio":
            command += ["-b:a",self._audio_bitrate]
        
        match self._subtitle_encoder:
            case "copy_subtitle":
                command +=["-c:s","copy"]
            case "srt":
                command +=["-c:s","srt"]
            case "ass":
                command +=["-c:s", "ass"]
            case "webvtt":
                command +=["-c:s", "webvtt"]

        return command


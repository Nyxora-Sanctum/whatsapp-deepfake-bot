import os

from PySide6.QtWidgets import QMainWindow, QFileDialog
from ..constants import PLATFORM, HOME_PATH
from ..Util import currentDirectory, checkForWritePermissions, open_folder
from .QTcustom import RegularQTPopup
from ..GenerateFFMpegCommand import FFMpegCommand

class SettingsTab:
    def __init__(
        self,
        parent: QMainWindow,
        halfPrecisionSupport,
        total_pytorch_gpus,
        total_ncnn_gpus,
    ):
        self.parent = parent
        self.ffmpeg_settings_dict = {
            "encoder": self.parent.encoder,
            "audio_encoder": self.parent.audio_encoder,
            "subtitle_encoder": self.parent.subtitle_encoder,
            "audio_bitrate": self.parent.audio_bitrate,
            "video_pixel_format": self.parent.video_pixel_format,
            "video_quality": self.parent.video_quality,

        }
        self.settings = Settings()

        self.connectWriteSettings()
        self.connectSettingText()

        # disable half option if its not supported
        if not halfPrecisionSupport:
            self.parent.precision.removeItem(1)

        # set max gpu id for combo boxs
        self.parent.pytorch_gpu_id.setMaximum(total_pytorch_gpus)
        self.parent.ncnn_gpu_id.setMaximum(total_ncnn_gpus)
        self.parent.openRVEFolderBtn.clicked.connect(lambda:open_folder(currentDirectory()))
        
        self.updateFFMpegCommand()
    
    def updateFFMpegCommand(self):
        """
        Updates the FFMpegCommand object with the current settings.
        """
        for key, value in self.ffmpeg_settings_dict.items():
            self.settings.writeSetting(key, value.currentText())
        
        pixel_fmt = self.settings.settings['video_pixel_format']
        hdr_mode = self.parent.hdrModeCheckBox.isChecked() 
        if hdr_mode:
            pxfmtdict = {
                        "yuv420p": "yuv420p10le",
                        "yuv422": "yuv422p10le",
                        "yuv444": "yuv444p10le",
                    }

            if pixel_fmt in pxfmtdict:
                pixel_fmt = pxfmtdict[pixel_fmt]
        
        command = FFMpegCommand(
        self.settings.settings['encoder'].replace(' (experimental)', '').replace(' (40 series and up)', ''),
        self.settings.settings['video_quality'],
        pixel_fmt,
        self.settings.settings['audio_encoder'],
        self.settings.settings['audio_bitrate'],
        self.settings.settings['subtitle_encoder']).build_command()
        self.parent.EncoderCommand.setText(" ".join(command))
         

    def connectWriteSettings(self):
        

        self.parent.precision.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "precision", self.parent.precision.currentText()
            )
        )
        self.parent.tensorrt_optimization_level.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "tensorrt_optimization_level",
                self.parent.tensorrt_optimization_level.currentText(),
            )
        )
        self.parent.encoder.currentIndexChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.audio_encoder.currentIndexChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.subtitle_encoder.currentIndexChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.video_pixel_format.currentIndexChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.audio_bitrate.currentIndexChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.hdrModeCheckBox.stateChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.video_quality.currentIndexChanged.connect(
            self.updateFFMpegCommand
        )
        self.parent.preview_enabled.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "preview_enabled",
                "True" if self.parent.preview_enabled.isChecked() else "False",
            )
        )
        self.parent.scene_change_detection_enabled.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "scene_change_detection_enabled",
                "True"
                if self.parent.scene_change_detection_enabled.isChecked()
                else "False",
            )
        )
        self.parent.discord_rich_presence.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "discord_rich_presence",
                "True" if self.parent.discord_rich_presence.isChecked() else "False",
            )
        )
        self.parent.scene_change_detection_method.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "scene_change_detection_method",
                self.parent.scene_change_detection_method.currentText(),
            )
        )
        self.parent.scene_change_detection_threshold.valueChanged.connect(
            lambda: self.settings.writeSetting(
                "scene_change_detection_threshold",
                str(self.parent.scene_change_detection_threshold.value()),
            )
        )
        self.parent.video_quality.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "video_quality",
                str(self.parent.video_quality.currentText()),
            )
        )
        self.parent.output_folder_location.textChanged.connect(
            lambda: self.writeOutputFolder()
        )

        self.parent.resetSettingsBtn.clicked.connect(self.resetSettings)

        self.parent.uhd_mode.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "uhd_mode",
                "True" if self.parent.uhd_mode.isChecked() else "False",
            )
        )
        self.parent.ncnn_gpu_id.textChanged.connect(
            lambda: self.settings.writeSetting(
                "ncnn_gpu_id", self.parent.ncnn_gpu_id.text()
            )
        )
        self.parent.pytorch_gpu_id.textChanged.connect(
            lambda: self.settings.writeSetting(
                "pytorch_gpu_id", self.parent.pytorch_gpu_id.text()
            )
        )
        self.parent.auto_border_cropping.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "auto_border_cropping",
                "True" if self.parent.auto_border_cropping.isChecked() else "False",
            )
        )
        self.parent.video_container.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "video_container", self.parent.video_container.currentText()
            )
        )
        self.parent.video_pixel_format.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "video_pixel_format", self.parent.video_pixel_format.currentText()
            )
        )
        self.parent.pytorch_version.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "pytorch_version", self.parent.pytorch_version.currentText()
            )
        )
        self.parent.pytorch_backend.currentIndexChanged.connect(
            lambda: self.settings.writeSetting(
                "pytorch_backend", self.parent.pytorch_backend.currentText()
            )
        )
        self.parent.rocm_override_hack.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "rocm_override_hack",
                "True" if self.parent.rocm_override_hack.isChecked() else "False"
            )
        )
        self.parent.dynamic_tensorrt_engine.stateChanged.connect(
            lambda: self.settings.writeSetting(
                "dynamic_tensorrt_engine",
                "True" if self.parent.dynamic_tensorrt_engine.isChecked() else "False"
            )
        )

    def writeOutputFolder(self):
        outputlocation = self.parent.output_folder_location.text()
        if not (os.path.exists(outputlocation) and os.path.isdir(outputlocation)):
            RegularQTPopup(
                "No videos folder\nSetting default output folder to home directory."
            )
            outputlocation = HOME_PATH
        if not checkForWritePermissions(outputlocation):
            RegularQTPopup(
                "No permissions to export here!\nSetting default output folder to home directory."
            )
            outputlocation = HOME_PATH

        self.settings.writeSetting(
            "output_folder_location",
            str(outputlocation),
        )

    def resetSettings(self):
        self.settings.writeDefaultSettings()
        self.settings.readSettings()
        self.connectSettingText()
        self.parent.switchToSettingsPage()

    def connectSettingText(self):
        if PLATFORM == "darwin":
            index = self.parent.encoder.findText("av1")
            self.parent.encoder.removeItem(index)

        self.parent.precision.setCurrentText(self.settings.settings["precision"])
        self.parent.tensorrt_optimization_level.setCurrentText(
            self.settings.settings["tensorrt_optimization_level"]
        )
        self.parent.encoder.setCurrentText(self.settings.settings["encoder"])
        self.parent.audio_encoder.setCurrentText(
            self.settings.settings["audio_encoder"]
        )
        self.parent.subtitle_encoder.setCurrentText(
            self.settings.settings["subtitle_encoder"]
        )
        self.parent.audio_bitrate.setCurrentText(
            self.settings.settings["audio_bitrate"]
        )
        self.parent.preview_enabled.setChecked(
            self.settings.settings["preview_enabled"] == "True"
        )
        self.parent.discord_rich_presence.setChecked(
            self.settings.settings["discord_rich_presence"] == "True"
        )
        self.parent.scene_change_detection_enabled.setChecked(
            self.settings.settings["scene_change_detection_enabled"] == "True"
        )
        self.parent.scene_change_detection_method.setCurrentText(
            self.settings.settings["scene_change_detection_method"]
        )
        self.parent.scene_change_detection_threshold.setValue(
            float(self.settings.settings["scene_change_detection_threshold"])
        )
        self.parent.video_quality.setCurrentText(
            self.settings.settings["video_quality"]
        )
        self.parent.output_folder_location.setText(
            self.settings.settings["output_folder_location"]
        )
        self.parent.select_output_folder_location_btn.clicked.connect(
            self.selectOutputFolder
        )
        self.parent.uhd_mode.setChecked(self.settings.settings["uhd_mode"] == "True")
        self.parent.ncnn_gpu_id.setValue(int(self.settings.settings["ncnn_gpu_id"]))
        self.parent.pytorch_gpu_id.setValue(
            int(self.settings.settings["pytorch_gpu_id"])
        )
        self.parent.auto_border_cropping.setChecked(
            self.settings.settings["auto_border_cropping"] == "True"
        )
        self.parent.video_container.setCurrentText(
            self.settings.settings["video_container"]
        )
        self.parent.video_pixel_format.setCurrentText(
            self.settings.settings["video_pixel_format"]
        )
        self.parent.pytorch_version.setCurrentText(
            self.settings.settings["pytorch_version"]
        )
        self.parent.pytorch_backend.setCurrentText(
            self.settings.settings["pytorch_backend"]
        )
        self.parent.rocm_override_hack.setChecked(
            self.settings.settings["rocm_override_hack"] == "True"
        )
        self.parent.dynamic_tensorrt_engine.setChecked(
            self.settings.settings["dynamic_tensorrt_engine"] == "True"
        )



    def selectOutputFolder(self):
        outputFile = QFileDialog.getExistingDirectory(
            parent=self.parent,
            caption="Select Folder",
            dir=os.path.expanduser("~"),
        )
        outputlocation = outputFile
        if os.path.exists(outputlocation) and os.path.isdir(outputlocation):
            if checkForWritePermissions(outputlocation):
                self.settings.writeSetting(
                    "output_folder_location",
                    str(outputlocation),
                )
                self.parent.output_folder_location.setText(outputlocation)
            else:
                RegularQTPopup("No permissions to export here!")


class Settings:
    def __init__(self):
        self.settingsFile = os.path.join(currentDirectory(), "settings.txt")

        """
        The default settings are set here, and are overwritten by the settings in the settings file if it exists and the legnth of the settings is the same as the default settings.
        The key is equal to the name of the widget of the setting in the settings tab.
        """
        self.defaultSettings = {
            "precision": "auto",
            "tensorrt_optimization_level": "3",
            "dynamic_tensorrt_engine": "False",
            "encoder": "libx264",
            "audio_encoder": "copy_audio",
            "subtitle_encoder": "copy_subtitle",
            "audio_bitrate": "192k",
            "preview_enabled": "True",
            "scene_change_detection_method": "pyscenedetect",
            "scene_change_detection_enabled": "True",
            "scene_change_detection_threshold": "3.5",
            "discord_rich_presence": "False",
            "video_quality": "High",
            "output_folder_location": os.path.join(f"{HOME_PATH}", "Videos")
            if PLATFORM != "darwin"
            else os.path.join(f"{HOME_PATH}", "Desktop"),
            "uhd_mode": "True",
            "ncnn_gpu_id": "0",
            "pytorch_gpu_id": "0",
            "auto_border_cropping": "False",
            "video_container": "mkv",
            "video_pixel_format": "yuv420p",
            "pytorch_version": "2.7.0",
            "pytorch_backend": "CUDA",
            "rocm_override_hack": "True",
        }
        self.allowedSettings = {
            "precision": ("auto", "float32", "float16"),
            "tensorrt_optimization_level": ("0", "1", "2", "3", "4", "5"),
            "dynamic_tensorrt_engine": ("True", "False"),
            "encoder": (
                "libx264",
                "libx265",
                "vp9",
                "av1",
                "prores",
                "ffv1",
                "x264_vulkan (experimental)",
                "x264_nvenc",
                "x265_nvenc",
                "av1_nvenc (40 series and up)",
                "x264_vaapi",
                "x265_vaapi",
                "av1_vaapi",
            ),
            "audio_encoder": ("aac", "libmp3lame", "opus", "copy_audio"),
            "subtitle_encoder": ("srt", "ass", "webvtt", "copy_subtitle"),
            "audio_bitrate": ("320k", "192k", "128k", "96k"),
            "preview_enabled": ("True", "False"),
            "scene_change_detection_method": (
                "mean",
                "mean_segmented",
                "pyscenedetect",
            ),
            "scene_change_detection_enabled": ("True", "False"),
            "scene_change_detection_threshold": [
                str(num / 10) for num in range(1, 100)
            ],
            "discord_rich_presence": ("True", "False"),
            "video_quality": ("Low", "Medium", "High", "Very High"),
            "output_folder_location": "ANY",
            "uhd_mode": ("True", "False"),
            "ncnn_gpu_id": "ANY",
            "pytorch_gpu_id": "ANY",
            "auto_border_cropping": ("True", "False"),
            "video_container": ("mkv", "mp4", "mov", "webm", "avi"),
            "video_pixel_format": (
                "yuv420p",
                "yuv422p",
                "yuv444p",
                "yuv420p10le",
                "yuv422p10le",
                "yuv444p10le",
            ),
            "pytorch_version": ("2.7.0", "2.6.0"),
            "pytorch_backend": "ANY",
            "rocm_override_hack": ("True", "False")
        }
        self.settings = self.defaultSettings.copy()
        if not os.path.isfile(self.settingsFile):
            self.writeDefaultSettings()
        self.readSettings()
        # check if the settings file is corrupted
        if len(self.defaultSettings) != len(self.settings):
            self.writeDefaultSettings()

    def readSettings(self):
        """
        Reads the settings from the 'settings.txt' file and stores them in the 'settings' dictionary.

        Returns:
            None
        """
        with open(self.settingsFile, "r") as file:
            try:
                for line in file:
                    key, value = line.strip().split(",")
                    self.settings[key] = value
            except (
                ValueError
            ):  # writes and reads again if the settings file is corrupted
                self.writeDefaultSettings()
                self.readSettings()

    def writeSetting(self, setting: str, value: str):
        """
        Writes the specified setting with the given value to the settings dictionary.

        Parameters:
        - setting (str): The name of the setting to be written, this will be equal to the widget name in the settings tab if set correctly.
        - value (str): The value to be assigned to the setting.

        Returns:
        None
        """
        self.settings[setting] = value
        self.writeOutCurrentSettings()

    def writeDefaultSettings(self):
        """
        Writes the default settings to the settings file if it doesn't exist.

        Parameters:
            None

        Returns:
            None
        """
        self.settings = self.defaultSettings.copy()
        self.writeOutCurrentSettings()

    def writeOutCurrentSettings(self):
        """
        Writes the current settings to a file.

        Parameters:
            self (SettingsTab): The instance of the SettingsTab class.

        Returns:
            None
        """
        with open(self.settingsFile, "w") as file:
            for key, value in self.settings.items():
                if key in self.defaultSettings:  # check if the key is valid
                    if (
                        value in self.allowedSettings[key]
                        or self.allowedSettings[key] == "ANY"
                    ):  # check if it is in the allowed settings dict
                        file.write(f"{key},{value}\n")
                else:
                    self.writeDefaultSettings()

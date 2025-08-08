import os
from PySide6.QtWidgets import QMainWindow
from .QTcustom import RegularQTPopup, NetworkCheckPopup, addNotificationToButton, disable_combobox_item_by_text
from ..DownloadDeps import DownloadDependencies
from ..DownloadModels import DownloadModel
from ..ModelHandler import (
    ncnnInterpolateModels,
    pytorchInterpolateModels,
    ncnnUpscaleModels,
    pytorchUpscaleModels,
)
import os


from PySide6.QtWidgets import QMessageBox

from PySide6.QtWidgets import QMessageBox
from .Updater import ApplicationUpdater
from ..constants import IS_FLATPAK, MODELS_PATH, PLATFORM, CWD, USE_LOCAL_BACKEND, HOME_PATH, BACKEND_PATH, PYTHON_EXECUTABLE_PATH, PYTHON_DIRECTORY, PLATFORM, IS_FLATPAK, CWD, CPU_ARCH
from ..BuiltInTorchVersions import TorchVersion
from ..Util import FileHandler

def downloadModelsBasedOnInstalledBackend(installed_backends: list):
    if NetworkCheckPopup():
        for backend in installed_backends:
            match backend:
                case "ncnn":
                    for model in ncnnInterpolateModels:
                        DownloadModel(
                            model, ncnnInterpolateModels[model][1], MODELS_PATH
                        )
                    for model in ncnnUpscaleModels:
                        DownloadModel(model, ncnnUpscaleModels[model][1], MODELS_PATH)
                case "pytorch":  # no need for tensorrt as it uses pytorch models
                    for model in pytorchInterpolateModels:
                        DownloadModel(
                            model, pytorchInterpolateModels[model][1], MODELS_PATH
                        )
                    for model in pytorchUpscaleModels:
                        DownloadModel(
                            model, pytorchUpscaleModels[model][1], MODELS_PATH
                        )


class DownloadTab:
    def __init__(
        self,
        parent: QMainWindow,
        backends: list,
    ):
        self.parent = parent
        self.torch_versions:list[TorchVersion] = [version for version in TorchVersion.__subclasses__()]
        self.downloadDeps = DownloadDependencies()
        self.backends = backends
        self.applicationUpdater = ApplicationUpdater()

        if FileHandler.getFreeSpace() < 7:
            self.parent.downloadTorchBtn.setEnabled(False)
        if FileHandler.getFreeSpace() < 7:
            self.parent.downloadTensorRTBtn.setEnabled(False)

        # disable as it is not complete
        try:
            self.parent.downloadDirectMLBtn.setEnabled(False)
            if PLATFORM != "win32":
                self.parent.downloadDirectMLBtn.setEnabled(False)
        except Exception as e:
            print(e)


        # set this all to not visible, as scrapping the idea for now.
        if PLATFORM != "linux":
            disable_combobox_item_by_text(self.parent.pytorch_backend, "ROCm (Linux Only)")
        
        if PLATFORM == "darwin":
            if CPU_ARCH == "arm64":
                self.parent.pytorch_backend.clear()
                self.parent.pytorch_backend.addItems(
                    ["MPS (Apple Silicon)"]
                )
                self.parent.pytorch_backend.setCurrentText("MPS (Apple Silicon)")
                self.parent.pytorch_backend.setEnabled(False)
                self.parent.downloadTorchBtn.setEnabled(True)
            self.parent.downloadTensorRTBtn.setEnabled(False)
        if IS_FLATPAK or USE_LOCAL_BACKEND:
            self.parent.uninstallAppBtn.setDisabled(True)
        else:
            self.parent.uninstallAppBtn.clicked.connect(self.uninstallApp)

        self.parent.ApplicationUpdateContainer.setVisible(False)
        self.QButtonConnect()
    
    def QButtonConnect(self):
        self.parent.downloadNCNNBtn.clicked.connect(lambda: self.download("ncnn", True))
        self.parent.downloadTorchBtn.clicked.connect(
            lambda: self.download("torch", True)
        )
        self.parent.downloadTensorRTBtn.clicked.connect(
            lambda: self.download("tensorrt", True)
        )
        self.parent.downloadDirectMLBtn.clicked.connect(
            lambda: self.download("directml", True)
        )
        self.parent.downloadAllModelsBtn.clicked.connect(
            lambda: downloadModelsBasedOnInstalledBackend(
                ["ncnn", "pytorch", "tensorrt", "directml"]
            )
        )
        self.parent.downloadSomeModelsBasedOnInstalledBackendbtn.clicked.connect(
            lambda: downloadModelsBasedOnInstalledBackend(self.backends)
        )
        self.parent.uninstallNCNNBtn.clicked.connect(
            lambda: self.download("ncnn", False)
        )
        self.parent.uninstallTorchBtn.clicked.connect(
            lambda: self.download("torch", False)
        )
        self.parent.uninstallTensorRTBtn.clicked.connect(
            lambda: self.download("tensorrt", False)
        )
        self.parent.uninstallDirectMLBtn.clicked.connect(
            lambda: self.download("directml", False)
        )
        self.parent.selectPytorchCustomModel.clicked.connect(
            lambda: self.parent.importCustomModel("pytorch")
        )
        self.parent.selectNCNNCustomModel.clicked.connect(
            lambda: self.parent.importCustomModel("ncnn")
        )
        self.parent.pytorch_version.addItems(
            [version.torch_version for version in self.torch_versions]
        )

    def uninstallApp(self):
        reply = QMessageBox.question(
            self.parent,
            "",
            "Are you sure you want to uninstall?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,  # type: ignore
        )
        if reply == QMessageBox.Yes:  # type: ignore
            os.chdir(HOME_PATH) # fix for windows, as you cant delete a directory in use.
            FileHandler().removeFolder(CWD)
            os._exit(0)
        

        
    def hideUninstallButtons(self):
        self.parent.uninstallTorchBtn.setVisible(False)
        self.parent.uninstallNCNNBtn.setVisible(False)
        self.parent.uninstallTensorRTBtn.setVisible(False)
        self.parent.uninstallDirectMLBtn.setVisible(False)

    def showUninstallButton(self, backends):
        if "pytorch (cuda)" in backends:
            self.parent.downloadTorchBtn.setVisible(False)
            self.parent.uninstallTorchBtn.setVisible(True)
        if "pytorch (rocm)" in backends:
            self.parent.downloadTorchBtn.setVisible(False)
            self.parent.uninstallTorchBtn.setVisible(True)
        if "pytorch (xpu)" in backends:
            self.parent.downloadTorchBtn.setVisible(False)
            self.parent.uninstallTorchBtn.setVisible(True)
        if "pytorch (mps)" in backends:
            self.parent.downloadTorchBtn.setVisible(False)
            self.parent.uninstallTorchBtn.setVisible(True)
        if "ncnn" in backends:
            self.parent.downloadNCNNBtn.setVisible(False)
            self.parent.uninstallNCNNBtn.setVisible(True)
        if "tensorrt" in backends:
            self.parent.downloadTensorRTBtn.setVisible(False)
            self.parent.uninstallTensorRTBtn.setVisible(True)

        # disable as it is not complete
        try:
            self.parent.downloadDirectMLBtn.setEnabled(False)
            if PLATFORM != "win32":
                self.parent.downloadDirectMLBtn.setEnabled(False)
        except Exception as e:
            print(e)


    def download(self, dep, install: bool = True):
        """
        Downloads the specified dependency.
        Parameters:
        - dep (str): The name of the dependency to download.
        Returns:
        - None
        """
        if install and ("torch" in dep.lower() or "tensorrt" in dep.lower()):
            if PLATFORM != "darwin":
                reply = QMessageBox.question(
                    self.parent,
                    "",
                    "Old GTX cards require torch version 2.6.0.\nContinue installation?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,  # type: ignore
                )
                if reply == QMessageBox.Yes:  # type: ignore
                    pass
                else:
                    return
        pytorch_ver:TorchVersion|None = None
        current_pytorch_version = self.parent.pytorch_version.currentText().split()[0]
        current_pytorch_backend = self.parent.pytorch_backend.currentText().split()[0].lower()
        for version in self.torch_versions:
            if version.torch_version == current_pytorch_version:
                pytorch_ver = version
                torchvision_ver = version.torchvision_version

        if not pytorch_ver:
            RegularQTPopup(
                "Please select a valid PyTorch version from the dropdown."
            )
            return
        
        if current_pytorch_backend == "cuda" or dep.lower() == "tensorrt":
            pytorch_backend = pytorch_ver.cuda_version
        elif current_pytorch_backend == "rocm":
            pytorch_backend = pytorch_ver.rocm_version
        elif current_pytorch_backend == "xpu":
            pytorch_backend = pytorch_ver.xpu_version
        elif current_pytorch_backend == "mps":
            pytorch_backend = pytorch_ver.mps_version
        
        if NetworkCheckPopup(
            "https://pypi.org/"
        ):  # check for network before installing
            return_code = self.downloadDeps.downloadPythonDeps(dep, pytorch_ver.torch_version, torchvision_ver, pytorch_backend, install)
            if return_code == 0:
                RegularQTPopup(
                    "Download Complete\nPlease restart the application to apply changes."
                )
            else:
                RegularQTPopup("Download Failed!\nPlease check logs for more info.")

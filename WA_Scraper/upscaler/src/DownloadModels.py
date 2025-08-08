import os

from .constants import MODELS_PATH
from .Util import createDirectory, extractTarGZ, networkCheck
from .ui.QTcustom import DownloadProgressPopup


class DownloadModel:
    """
    Takes in the name of a model and the name of the backend in the GUI, and downloads it from a URL
    model: any valid model used by RVE
    backend: the backend used (pytorch, tensorrt, ncnn)
    """

    def __init__(
        self,
        modelFile: str,
        downloadModelFile: str,
        modelPath: str = MODELS_PATH,
    ):
        self.modelFile = modelFile
        self.modelPath = modelPath
        self.downloadModelFile = downloadModelFile
        self.downloadModelPath = os.path.join(modelPath, downloadModelFile)
        createDirectory(modelPath)
        # check if internet doesnt exist, if it doesnt dont allow to be added to queue

    def downloadModel(self) -> bool:
        """
        Downloads a model from the github repo
        If the installation is unsucessful, or interent is unavailable to download, it will return False
        else
        returns True if the model exists, or is sucessfully downloaded
        """
        if os.path.isfile(
            os.path.join(self.modelPath, self.modelFile)
        ) or os.path.exists(os.path.join(self.modelPath, self.modelFile)):
            return True
        if not networkCheck():
            return False
        url = (
            "https://github.com/TNTwise/real-video-enhancer-models/releases/download/models/"
            + self.downloadModelFile
        )
        title = "Downloading: " + self.downloadModelFile
        DownloadProgressPopup(
            link=url, title=title, downloadLocation=self.downloadModelPath
        )
        print("Done")
        if "tar.gz" in self.downloadModelFile:
            print("Extracting File")
            extractTarGZ(self.downloadModelPath)
        return True


# just some testing code lol

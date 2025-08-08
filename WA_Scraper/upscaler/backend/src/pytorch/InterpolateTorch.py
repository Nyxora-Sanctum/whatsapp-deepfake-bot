import torch
import torch.nn.functional as F
from abc import ABCMeta, abstractmethod
from queue import Queue

from ..utils.SSIM import SSIM

# from backend.src.pytorch.InterpolateArchs.GIMM import GIMM
from .InterpolateArchs.DetectInterpolateArch import ArchDetect
from .InterpolateGIMM import InterpolateGIMMTorch
from .InterpolateGMFSS import InterpolateGMFSSTorch
from .InterpolateRIFE import InterpolateRifeTorch,  InterpolateRIFEDRBA


class InterpolateFactory:
    @staticmethod
    def build_interpolation_method(interpolate_model_path, backend, drba=False):
        ad = ArchDetect(interpolate_model_path)
        base_arch = ad.getArchBase()
        match base_arch:
            case "rife":
                if drba:
                    return InterpolateRIFEDRBA
                return InterpolateRifeTorch
            case "gmfss":
                return InterpolateGMFSSTorch
            case "gimm":
                return InterpolateGIMMTorch

import requests
try:
    from .constants import HAS_NETWORK_ON_STARTUP
except ImportError:
    from constants import HAS_NETWORK_ON_STARTUP
from dataclasses import dataclass
from .ui.SettingsTab import Settings

@dataclass
class TorchVersion:
    torch_version: str
    torchvision_version: str
    cuda_version: str
    rocm_version: str
    xpu_version: str
    mps_version: str


class Torch2_7(TorchVersion):
    torch_version = "2.7.0"
    torchvision_version = "0.22.0"
    cuda_version = "+cu128"
    rocm_version = "+rocm6.3"
    xpu_version = "+xpu"
    mps_version = ""
   

class Torch2_6(TorchVersion):
    torch_version = "2.6.0"
    torchvision_version = "0.21.0"
    cuda_version = "+cu118"
    rocm_version = "+rocm6.2.4"
    xpu_version = "+xpu"
    mps_version = ""



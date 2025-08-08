import torch

from .TorchUtils import TorchUtils
# from backend.src.pytorch.InterpolateArchs.GIMM import GIMM
from .BaseInterpolate import BaseInterpolate
import math
import logging
import sys
from ..utils.Util import (
    warnAndLog,
    log,
)

from ..constants import HAS_SYSTEM_CUDA
from time import sleep

torch.set_float32_matmul_precision("medium")
torch.set_grad_enabled(False)
logging.basicConfig(level=logging.INFO)

class InterpolateGIMMTorch(BaseInterpolate):
    @torch.inference_mode()
    def __init__(
        self,
        modelPath: str,
        ceilInterpolateFactor: int = 2,
        width: int = 1920,
        height: int = 1080,
        device: str = "default",
        dtype: str = "auto",
        backend: str = "pytorch",
        UHDMode: bool = False,
        ensemble: bool = False,
        dynamicScaledOpticalFlow: bool = False,
        gpu_id: int = 0,
        hdr_mode: bool = False,
        *args,
        **kwargs,
    ):
        self.interpolateModel = modelPath
        self.width = width
        self.height = height
        _pad = 64
        self.scale = 0.5  # GIMM uses fat amounts of vram, needs really low flow resolution for regular resolutions
        if UHDMode:
            self.scale = 0.25  # GIMM uses fat amounts of vram, needs really low flow resolution for UHD
        tmp = max(_pad, int(_pad / self.scale))
        self.pw = math.ceil(self.width / tmp) * tmp
        self.ph = math.ceil(self.height / tmp) * tmp
        padding = (0, self.pw - self.width, 0, self.ph - self.height)
        self.torchUtils = TorchUtils(
            width=width,
            height=height,
            hdr_mode=hdr_mode,
            padding=padding,
            device_type=device,
        )
        self.device = self.torchUtils.handle_device(device, gpu_id=gpu_id)
        self.dtype = self.torchUtils.handle_precision(dtype)
        if ensemble:
            print("Ensemble is not implemented for GIMM, disabling", file=sys.stderr)
        if dynamicScaledOpticalFlow:
            print(
                "Dynamic Scaled Optical Flow is not implemented for GIMM, disabling",
                file=sys.stderr,
            )

        self.backend = backend
        self.ceilInterpolateFactor = ceilInterpolateFactor
        self.hdr_mode = hdr_mode # used in base interpolate class (ik inheritance is bad leave me alone)
        self.frame0 = None
        
        self.doEncodingOnFrame = False
        self._load()

    @torch.inference_mode()
    def _load(self):
        self.stream = self.torchUtils.init_stream()
        self.prepareStream = self.torchUtils.init_stream()
        self.copyStream = self.torchUtils.init_stream()
        with self.torchUtils.run_stream(self.prepareStream):  # type: ignore
            from .InterpolateArchs.GIMM.gimmvfi_r import GIMMVFI_R

            self.flownet = GIMMVFI_R(
                model_path=self.interpolateModel, width=self.width, height=self.height
            )
            state_dict = torch.load(self.interpolateModel, map_location=self.device)[
                "gimmvfi_r"
            ]
            self.flownet.load_state_dict(state_dict)
            self.flownet.eval().to(device=self.device, dtype=self.dtype)

            

            dummyInput = torch.zeros(
                [1, 3, self.ph, self.pw], dtype=self.dtype, device=self.device
            )
            dummyInput2 = torch.zeros(
                [1, 3, self.ph, self.pw], dtype=self.dtype, device=self.device
            )
            xs = torch.cat(
                (dummyInput.unsqueeze(2), dummyInput2.unsqueeze(2)), dim=2
            ).to(self.device, non_blocking=True)
            s_shape = xs.shape[-2:]

            # caching the timestep tensor in a dict with the timestep as a float for the key

            self.timestepDict = {}
            self.coordDict = {}

            for n in range(self.ceilInterpolateFactor):
                timestep = n / (self.ceilInterpolateFactor)
                timestep_tens = (
                    n
                    * 1
                    / self.ceilInterpolateFactor
                    * torch.ones(xs.shape[0])
                    .to(xs.device)
                    .to(self.dtype)
                    .reshape(-1, 1, 1, 1)
                )
                self.timestepDict[timestep] = timestep_tens
                coord = (
                    self.flownet.sample_coord_input(
                        1,
                        s_shape,
                        [1 / self.ceilInterpolateFactor * n],
                        device=self.device,
                        upsample_ratio=self.scale,
                    ).to(non_blocking=True, dtype=self.dtype, device=self.device),
                    None,
                )
                self.coordDict[timestep] = coord

            log("GIMM loaded")
            log("Scale: " + str(self.scale))
            log("Using System CUDA: " + str(HAS_SYSTEM_CUDA))
            if not HAS_SYSTEM_CUDA:
                print(
                    "WARNING: System CUDA not found, falling back to PyTorch softsplat. This will be a bit slower.",
                    file=sys.stderr,
                )
            if self.backend == "tensorrt":
                warnAndLog(
                    "TensorRT is not implemented for GIMM yet, falling back to PyTorch"
                )
        self.torchUtils.sync_stream(self.prepareStream)  # type: ignore

    @torch.inference_mode()
    def __call__(
        self,
        img1,
        transition=False,
    ):  # type: ignore
        with self.torchUtils.run_stream(self.stream):  # type: ignore
            if self.frame0 is None:
                self.frame0 = self.torchUtils.frame_to_tensor(img1, self.prepareStream, self.device, self.dtype)
                return
            frame1 = self.torchUtils.frame_to_tensor(img1, self.prepareStream, self.device, self.dtype)
            for n in range(self.ceilInterpolateFactor - 1):
                if not transition:
                    timestep = (n + 1) * 1.0 / (self.ceilInterpolateFactor)
                    coord = self.coordDict[timestep]
                    timestep_tens = self.timestepDict[timestep]
                    xs = torch.cat(
                        (self.frame0.unsqueeze(2), frame1.unsqueeze(2)), dim=2
                    ).to(self.device, non_blocking=True, dtype=self.dtype)

                    while self.flownet is None:
                        sleep(1)
                    with torch.autocast(enabled=True, device_type=self.device.type):
                        output = self.flownet(
                            xs, coord, timestep_tens, ds_factor=self.scale
                        )

                    if torch.isnan(output).any():
                        # if there are nans in output, reload with float32 precision and process.... dumb fix but whatever
                        raise ValueError("Nans in output")

                    output = self.torchUtils.tensor_to_frame(output)
                    yield output

                else:
                    yield img1

            self.torchUtils.copy_tensor(self.frame0, frame1, self.copyStream)

        self.torchUtils.sync_all_streams()

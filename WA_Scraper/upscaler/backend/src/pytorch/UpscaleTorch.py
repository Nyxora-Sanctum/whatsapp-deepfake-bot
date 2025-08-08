import os
import math

import gc
from .TorchUtils import TorchUtils
import torch as torch
import torch.nn.functional as F
import sys
from time import sleep
from ..constants import HAS_PYTORCH_CUDA, MODELS_DIRECTORY

from ..utils.Util import log, printAndLog
import numpy as np
def process_output(output, hdr_mode):
    # Step 1: Squeeze the first dimension
    output = np.squeeze(output, axis=0)

    # Step 2: Permute axes from (C, H, W) to (H, W, C)
    output = np.transpose(output, (1, 2, 0))

    # Step 3: Clamp values to the range [0, 1]
    output = np.clip(output, 0, 1)

    # Step 4: Multiply by scaling factor
    scale_factor = 65535.0 if hdr_mode else 255.0
    output = output * scale_factor

    # Step 5: Convert to appropriate dtype
    dtype = np.uint16 if hdr_mode else np.uint8
    output = output.astype(dtype)

    return output

class UpscalePytorch:
    """A class for upscaling images using PyTorch.

    Args:
        modelPath (str): The path to the model file.
        device (str, optional): The device to use for inference. Defaults to "default".
        tile_pad (int, optional): The padding size for tiles. Defaults to 10.
        precision (str, optional): The precision mode for the model. Defaults to "auto".
        width (int, optional): The width of the input image. Defaults to 1920.
        height (int, optional): The height of the input image. Defaults to 1080.
        backend (str, optional): The backend for inference. Defaults to "pytorch".
        trt_workspace_size (int, optional): The workspace size for TensorRT. Defaults to 0.
        trt_cache_dir (str, optional): The cache directory for TensorRT. Defaults to modelsDirectory().

    Attributes:
        tile_pad (int): The padding size for tiles.
        dtype (torch.dtype): The data type for the model.
        device (torch.device): The device used for inference.
        model (torch.nn.Module): The loaded model.
        width (int): The width of the input image.
        height (int): The height of the input image.
        scale (float): The scale factor of the model.

    Methods:
        handlePrecision(precision): Handles the precision mode for the model.
        loadModel(modelPath, dtype, device): Loads the model from file.
        bytesToFrame(frame): Converts bytes to a torch tensor.
        tensorToNPArray(image): Converts a torch tensor to a NumPy array.
        renderImage(image): Renders an image using the model.
        renderToNPArray(image): Renders an image and returns it as a NumPy array.
        renderImagesInDirectory(dir): Renders all images in a directory.
        getScale(): Returns the scale factor of the model.
        saveImage(image, fullOutputPathLocation): Saves an image to a file.
        renderTiledImage(image, tile_size): Renders a tiled image."""

    @torch.inference_mode()
    def __init__(
        self,
        modelPath: str,
        device="default",
        tile_pad: int = 10,
        precision: str = "auto",
        width: int = 1920,
        height: int = 1080,
        tilesize: int = 0,
        backend: str = "pytorch",
        gpu_id: int = 0,
        hdr_mode: bool = False,
        override_upscale_scale: int | None = None,
        # trt options
        trt_workspace_size: int = 0,
        trt_optimization_level: int = 3,
        trt_max_aux_streams: int | None = None,
        trt_debug: bool = False,
        trt_static_shape: bool = False,

    ):
        self.torchUtils = TorchUtils(width=width, height=height,hdr_mode=hdr_mode,device_type=device)  
        device = self.torchUtils.handle_device(device, gpu_id)
        self.tile_pad = tile_pad
        self.dtype = self.torchUtils.handle_precision(precision)
        self.device = device
        self.videoWidth = width
        self.videoHeight = height
        self.tilesize = tilesize
        self.tile = [self.tilesize, self.tilesize]
        self.modelPath = modelPath
        self.backend = backend
        
      
        self.trt_workspace_size = trt_workspace_size
        self.trt_optimization_level = trt_optimization_level
        self.trt_aux_streams = trt_max_aux_streams
        self.trt_debug = trt_debug
        
        self.hdr_mode = hdr_mode         

        self.trt_static_shape = trt_static_shape

        # streams
        self.stream = self.torchUtils.init_stream()
        self.f2tstream = self.torchUtils.init_stream()  
        self.prepareStream = self.torchUtils.init_stream()
        self.convertStream = self.torchUtils.init_stream()
        self._load()

    @torch.inference_mode()
    def set_self_model(self, backend="pytorch"):
        torch.cuda.empty_cache()
        if backend == "tensorrt":
            from .TensorRTHandler import TorchTensorRTHandler
            trtHandler = TorchTensorRTHandler()
            self.model = trtHandler.load_engine(self.trt_engine_name)
        else:
            self.model = self.loadModel(
                modelPath=self.modelPath, device=self.device, dtype=self.dtype
            )


    # add prores
    # add janai v2
    # add bhi light model

    @torch.inference_mode()
    def _load(self):
        if self.videoWidth <= 1920 and self.videoHeight <= 1920 and (self.videoWidth >= 128 and self.videoHeight >= 128):

            self.trt_min_shape = [128, 128]
            self.trt_opt_shape = [1920, 1080]
            self.trt_max_shape = [1920, 1920]
        

        if self.videoWidth > 1920 or self.videoHeight > 1920 and not self.trt_static_shape:
            printAndLog("The video resolution is very large for TensorRT dynamic shape and will use a lot of VRAM, falling back to static shape")
            self.trt_static_shape = True

        if self.videoWidth < 128 or self.videoHeight < 128 and not self.trt_static_shape:
            printAndLog("The video resolution is too small for TensorRT dynamic shape, falling back to static shape")
            self.trt_static_shape = True

        
        with self.torchUtils.run_stream(self.prepareStream):
            self.set_self_model(backend="pytorch")

            match self.scale:
                case 1:
                    modulo = 4
                case 2:
                    modulo = 2
                case _:
                    modulo = 1
            if all(t > 0 for t in self.tile):
                self.pad_w = (
                    math.ceil(
                        min(self.tile[0] + 2 * self.tile_pad, self.videoWidth) / modulo
                    )
                    * modulo
                )
                self.pad_h = (
                    math.ceil(
                        min(self.tile[1] + 2 * self.tile_pad, self.videoHeight) / modulo
                    )
                    * modulo
                )
            else:
                modulo = 1 if self.videoWidth < 720 or self.videoHeight < 720 else 1
                self.pad_w = math.ceil(self.videoWidth / modulo) * modulo
                self.pad_h = math.ceil(self.videoHeight / modulo) * modulo

            if self.backend == "tensorrt":
                from .TensorRTHandler import TorchTensorRTHandler


                trtHandler = TorchTensorRTHandler(
                    export_format="fallback", # torchscript due to wonky resolution issues with dynamo
                    dynamo_export_format="fallback",
                    trt_optimization_level=self.trt_optimization_level,

                )
                if self.trt_static_shape:
                    dimensions = f"{self.pad_w}x{self.pad_h}"
                else:
                    for i in range(2):
                        self.trt_min_shape[i] = math.ceil(self.trt_min_shape[i] / modulo) * modulo
                        self.trt_opt_shape[i] = math.ceil(self.trt_opt_shape[i] / modulo) * modulo
                        self.trt_max_shape[i] = math.ceil(self.trt_max_shape[i] / modulo) * modulo

                    dimensions = (
                        f"min-{self.trt_min_shape[0]}x{self.trt_min_shape[1]}"
                        f"_opt-{self.trt_opt_shape[0]}x{self.trt_opt_shape[1]}"
                        f"_max-{self.trt_max_shape[0]}x{self.trt_max_shape[1]}"
                    )
                self.trt_engine_name = os.path.join(
                    (
                        f"{os.path.basename(self.modelPath)}"
                        + f"_{dimensions}"
                        + f"_{'fp16' if self.dtype == torch.float16 else 'fp32'}"
                        + f"_{torch.cuda.get_device_name(self.device)}"
                        + f"_trt-{trtHandler.tensorrt_version}"
                        + f"_torch_tensorrt-{trtHandler.torch_tensorrt_version}"
                        + f"_opt-{self.trt_optimization_level}"
                        + (
                            f"_workspace-{self.trt_workspace_size}"
                            if self.trt_workspace_size > 0
                            else ""
                        )
                    ),
                )

                if not trtHandler.check_engine_exists(self.trt_engine_name):
                    inputs = (torch.zeros([1, 3, self.pad_h, self.pad_w], dtype=self.dtype, device=self.device),)
                    if self.trt_static_shape:
                        dynamic_shapes = None
                        
                    else:
                        self.trt_min_shape.reverse()
                        self.trt_opt_shape.reverse()
                        self.trt_max_shape.reverse()

                        _height = torch.export.Dim("height", min=self.trt_min_shape[0] // modulo, max=self.trt_max_shape[0] // modulo)
                        _width = torch.export.Dim("width", min=self.trt_min_shape[1] // modulo, max=self.trt_max_shape[1] // modulo)
                        dim_height = _height * modulo
                        dim_width = _width * modulo
                        dynamic_shapes = {"x": {2: dim_height, 3: dim_width}}

                        

                    # inference and get re-load state dict due to issue with span.

                    model = self.model
                    model(inputs[0])
                    self.model.load_state_dict(model.state_dict())
                    del model
                    torch.cuda.empty_cache()


                    trtHandler.build_engine(
                        self.model,
                        self.dtype,
                        self.device,
                        example_inputs=inputs,
                        trt_engine_name=self.trt_engine_name,
                        trt_multi_precision_engine=False,
                        dynamic_shapes=dynamic_shapes,
                    )


                self.set_self_model(backend="tensorrt")

        self.torchUtils.clear_cache()
        self.torchUtils.sync_all_streams()

    @torch.inference_mode()
    def hotUnload(self):
        self.model = None
        gc.collect()
        self.torchUtils.clear_cache()
        if HAS_PYTORCH_CUDA:
            torch.cuda.reset_max_memory_allocated()
            torch.cuda.reset_max_memory_cached()

    @torch.inference_mode()
    def hotReload(self):
        self._load()

    @torch.inference_mode()
    def loadModel(
        self, modelPath: str, dtype: torch.dtype = torch.float32, device: str = "cuda"
    ) -> torch.nn.Module:
        from .spandrel import ModelLoader, ImageModelDescriptor

        model = ModelLoader().load_from_file(modelPath)
        assert isinstance(model, ImageModelDescriptor)
        # get model attributes
        self.scale = model.scale

        model = model.model
        model.load_state_dict(model.state_dict(), assign=True)
        model.eval().to(self.device, dtype=self.dtype)
        try:
            example_input = torch.zeros((1, 3, 64, 64), device=self.device, dtype=self.dtype)
            model(example_input)
        except Exception as e:
            print("Error occured during model validation, falling back to float32 dtype.\n")
            log(str(e))
            model = model.to(self.device, dtype=torch.float32)
            
        return model

    
    @torch.inference_mode()
    def __call__(self, image: bytes) -> torch.Tensor:
        image = self.torchUtils.frame_to_tensor(image, self.f2tstream, self.device, self.dtype)
        with self.torchUtils.run_stream(self.stream), torch.amp.autocast(
            enabled=self.dtype == torch.float16,device_type="cuda"):
            while self.model is None:
                sleep(1)
            if self.tilesize == 0:
                
                output = self.model(image)
                
            else:
                output = self.renderTiledImage(image)
            
        self.torchUtils.sync_stream(self.stream)
        
        with self.torchUtils.run_stream(self.convertStream):
            output = self.torchUtils.tensor_to_frame(output)
            
        self.torchUtils.sync_all_streams()
        return output
 
    def getScale(self):
        return self.scale

    @torch.inference_mode()
    def renderTiledImage(
        self,
        img: torch.Tensor,
    ) -> torch.Tensor:
        scale = self.scale
        tile = self.tile
        tile_pad = self.tile_pad

        batch, channel, height, width = img.shape
        output_shape = (batch, channel, height * scale, width * scale)

        # start with black image
        output = img.new_zeros(output_shape).to(device=self.device, dtype=self.dtype)

        tiles_x = math.ceil(width / tile[0])
        tiles_y = math.ceil(height / tile[1])

        # loop over all tiles
        for y in range(tiles_y):
            for x in range(tiles_x):
                # extract tile from input image
                ofs_x = x * tile[0]
                ofs_y = y * tile[1]

                # input tile area on total image
                input_start_x = ofs_x
                input_end_x = min(ofs_x + tile[0], width)
                input_start_y = ofs_y
                input_end_y = min(ofs_y + tile[1], height)

                # input tile area on total image with padding
                input_start_x_pad = max(input_start_x - tile_pad, 0)
                input_end_x_pad = min(input_end_x + tile_pad, width)
                input_start_y_pad = max(input_start_y - tile_pad, 0)
                input_end_y_pad = min(input_end_y + tile_pad, height)

                # input tile dimensions
                input_tile_width = input_end_x - input_start_x
                input_tile_height = input_end_y - input_start_y

                input_tile = img[
                    :,
                    :,
                    input_start_y_pad:input_end_y_pad,
                    input_start_x_pad:input_end_x_pad,
                ].to(device=self.device, dtype=self.dtype)

                h, w = input_tile.shape[2:]
                input_tile = F.pad(
                    input_tile, (0, self.pad_w - w, 0, self.pad_h - h), "replicate"
                )

                # process tile
                output_tile = self.model(
                    input_tile
                )

                output_tile = output_tile[:, :, : h * scale, : w * scale]

                # output tile area on total image
                output_start_x = input_start_x * scale
                output_end_x = input_end_x * scale
                output_start_y = input_start_y * scale
                output_end_y = input_end_y * scale

                # output tile area without padding
                output_start_x_tile = (input_start_x - input_start_x_pad) * scale
                output_end_x_tile = output_start_x_tile + input_tile_width * scale
                output_start_y_tile = (input_start_y - input_start_y_pad) * scale
                output_end_y_tile = output_start_y_tile + input_tile_height * scale

                # put tile into output image
                output[
                    :, :, output_start_y:output_end_y, output_start_x:output_end_x
                ] = output_tile[
                    :,
                    :,
                    output_start_y_tile:output_end_y_tile,
                    output_start_x_tile:output_end_x_tile,
                ]

        return output
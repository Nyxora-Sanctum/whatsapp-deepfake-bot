"""
MIT License

Copyright (c) 2024 TNTwise

cPermission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import sys
import os
from ..utils.Util import suppress_stdout_stderr, warnAndLog, log
from ..version import __version__
from ..constants import MODELS_DIRECTORY
with suppress_stdout_stderr():
    import torch
    import torch_tensorrt
    import tensorrt as trt
    from torch._export.converter import TS2EPConverter
    from torch.export.exported_program import ExportedProgram

def torchscript_to_dynamo(
            model: torch.nn.Module, example_inputs: list[torch.Tensor], dynamic_shapes=None
        ) -> ExportedProgram:
            """Converts a TorchScript module to a Dynamo program."""
            module = torch.jit.trace(model, example_inputs)
            exported_program = TS2EPConverter(
                module, sample_args=tuple(example_inputs), sample_kwargs=None, dynamic_shapes=dynamic_shapes
            ).convert()
            del module
            torch.cuda.empty_cache()
            return exported_program

def nnmodule_to_dynamo(
    model: torch.nn.Module, example_inputs: list[torch.Tensor], dynamic_shapes=None
) -> ExportedProgram:
    """Converts a nn.Module to a Dynamo program."""
    return torch.export.export(
        model, tuple(example_inputs), dynamic_shapes=dynamic_shapes
    )

"""onnx_support = True
try:
    import onnx
except ImportError:
    onnx_support = False"""


class TorchTensorRTHandler: 
    """
    Args:
        dynamo_export_format (str): The export format to use when exporting models using Dynamo. Defaults to "nn2exportedprogram".
        trt_workspace_size (int): The workspace size to use when compiling models using TensorRT. Defaults to 0.
        max_aux_streams (int | None): The maximum number of auxiliary streams to use when compiling models using TensorRT. Defaults to None.
        trt_optimization_level (int): The optimization level to use when compiling models using TensorRT. Defaults to 3.
        debug (bool): Whether to enable debugging when compiling models using TensorRT. Defaults to False.
        static_shape (bool): Whether to use static shape when compiling models using TensorRT. Defaults

        dynamo_export_format (str): nn2exportedprogram, torchscript2exportedprogram or fallback, which tries nn2exportedprogram first, and then torchscrip2exportedprogram if nn2exportedprogram fails, torchscript2exportedprogram uses torchscript as an intermediatory as some issues occur when using dynamo with torch.export.export

        multi precision engines seem to not like torchscript2exportedprogram,
        or maybe its just the model not playing nice with explicit_typing,
        either way, forcing one precision helps with speed in some cases.
    """

    trt_path_appendix = "_RVE-VERSION: " + __version__ + ".engine" # this is used to identify the models that were exported with this version of RVE

    def __init__(
        self,
        export_format: str = "dynamo",
        dynamo_export_format: str = "nn2exportedprogram",
        max_aux_streams: int | None = None,
        debug: bool = False,
        static_shape: bool = True,
        
        trt_optimization_level: int = 3,
        trt_workspace_size: int = 0,
        
    ):
        self.tensorrt_version = trt.__version__  # can just grab version from here instead of importing trt and torch trt in all related files
        self.torch_tensorrt_version = torch_tensorrt.__version__

        self.export_format = export_format
        self.dynamo_export_format = dynamo_export_format
        self.trt_workspace_size = trt_workspace_size
        self.max_aux_streams = max_aux_streams
        self.optimization_level = trt_optimization_level
        self.debug = debug
        self.static_shape = static_shape  # Unused for now

        # clear previous tensorrt models
        cleared_models = False
        for model in os.listdir(MODELS_DIRECTORY):
            if not model.endswith(self.trt_path_appendix) and "tensorrt" in model.lower():
                model_path = os.path.join(MODELS_DIRECTORY, model)
                try:
                    os.remove(model_path)
                    cleared_models = True
                    log(f"Removed {model_path}")
                except Exception as e:
                    log(f"Failed to remove {model_path}: {e}")
        if cleared_models:
            print("Cleared old TensorRT models...", file=sys.stderr)
    
    

    def grid_sample_decomp(self, exported_program):
        from torch_tensorrt.dynamo.conversion.impl.grid import GridSamplerInterpolationMode
        GridSamplerInterpolationMode.update(
            {
                0: trt.InterpolationMode.LINEAR,
                1: trt.InterpolationMode.NEAREST,
                2: trt.InterpolationMode.CUBIC,
            }
        )
        return exported_program


    def export_using_dynamo(
        self,
        model: torch.nn.Module,
        example_inputs: list[torch.Tensor],
        device: torch.device,
        dtype: torch.dtype,
        trt_engine_path: str,
        trt_multi_precision_engine: bool = False,
        dynamic_shapes: dict | None = None,
        
    ):
        
        """Exports a model using TensorRT Dynamo."""
        if self.dynamo_export_format == "nn2exportedprogram":
            exported_program = nnmodule_to_dynamo(model, example_inputs, dynamic_shapes=dynamic_shapes)
        elif self.dynamo_export_format == "torchscript2exportedprogram":
            exported_program = torchscript_to_dynamo(model, example_inputs, dynamic_shapes=dynamic_shapes)
        elif self.dynamo_export_format == "fallback":
            try:
                exported_program = nnmodule_to_dynamo(model, example_inputs, dynamic_shapes=dynamic_shapes)
            except Exception as e:
                print(
                    "Failed to export using nn2exportedprogram. Falling back to torchscript2exportedprogram...",
                    file=sys.stderr,
                )
                exported_program = torchscript_to_dynamo(model, example_inputs, dynamic_shapes=dynamic_shapes)
        else:
            raise ValueError(f"Unsupported export format: {self.dynamo_export_format}")

        torch.cuda.empty_cache()

        exported_program = self.grid_sample_decomp(exported_program)
        
        model_trt = torch_tensorrt.dynamo.compile(
            exported_program,
            tuple(example_inputs),
            device=device,
            enabled_precisions={dtype} if not trt_multi_precision_engine else {torch.float},
            use_explicit_typing=trt_multi_precision_engine,
            debug=self.debug,
            num_avg_timing_iters=4,
            workspace_size=self.trt_workspace_size,
            min_block_size=1,
            max_aux_streams=self.max_aux_streams,
            optimization_level=self.optimization_level,
            #tiling_optimization_level="full",
        )
      

        torch_tensorrt.save(
            model_trt,
            trt_engine_path,
            output_format="torchscript",
            inputs=tuple(example_inputs),
        )
        torch.cuda.empty_cache()

    def export_torchscript_model(
        self,
        model: torch.nn.Module,
        example_inputs: list[torch.Tensor],
        device: torch.device,
        dtype: torch.dtype,
        trt_engine_path: str,
        dynamic_shapes: dict | None = None,
    ):
        """Exports a model using TorchScript."""

        model.to(device=device, dtype=dtype)
        module = torch.jit.trace(model, example_inputs)
        torch.cuda.empty_cache()
        del model

        module_trt = torch_tensorrt.compile(
            module,
            ir="ts",
            inputs=example_inputs,
            enabled_precisions={dtype},
            device=torch_tensorrt.Device(gpu_id=0),
            workspace_size=self.trt_workspace_size,
            truncate_long_and_double=True,
            min_block_size=1,
        )
        torch.jit.save(module_trt, trt_engine_path)
    
    def check_engine_exists(self, trt_engine_name: str) -> bool:
        """Checks if a TensorRT engine exists at the specified path."""
        trt_engine_name += self.trt_path_appendix
        trt_engine_path = os.path.join(MODELS_DIRECTORY, trt_engine_name)
        return os.path.exists(trt_engine_path)

    def build_engine(
        self,
        model: torch.nn.Module,
        dtype: torch.dtype,
        device: torch.device,
        example_inputs: list[torch.Tensor],
        trt_engine_name: str,
        trt_multi_precision_engine: bool = False,
        dynamic_shapes: dict | None = None,
        
    ):
        
        trt_engine_name += self.trt_path_appendix
        trt_engine_path = os.path.join(MODELS_DIRECTORY, trt_engine_name)
        torch.cuda.empty_cache()
        """Builds a TensorRT engine from the provided model."""
        print(
            f"Building TensorRT engine {os.path.basename(trt_engine_path)}. This may take a while...",
            file=sys.stderr,
        )
        
        if self.export_format == "dynamo":
            with suppress_stdout_stderr():
                self.export_using_dynamo(
                model, example_inputs, device, dtype, trt_engine_path, trt_multi_precision_engine=trt_multi_precision_engine, dynamic_shapes=dynamic_shapes,
            )
        elif self.export_format == "torchscript":
            self.export_torchscript_model(
                model, example_inputs, device, dtype, trt_engine_path, dynamic_shapes=dynamic_shapes,
            )
        else:
            try:
                 with suppress_stdout_stderr():
                    self.export_using_dynamo(
                        model, example_inputs, device, dtype, trt_engine_path, trt_multi_precision_engine=trt_multi_precision_engine, dynamic_shapes=dynamic_shapes,
                    )
            except Exception as e:
                print(
                    f"{e}",
                    file=sys.stderr,
                )
                if dynamic_shapes is not None:
                    warnAndLog(
                        "Failed to export with Dynamo, trying torchscript2exportedprogram with static shapes.",
                    )
                self.export_torchscript_model(
                    model, example_inputs, device, dtype, trt_engine_path, dynamic_shapes=dynamic_shapes,
                )
        
        torch.cuda.empty_cache()

    def load_engine(self, trt_engine_name: str) -> torch.jit.ScriptModule:
        """Loads a TensorRT engine from the specified path."""
        
        trt_engine_name += self.trt_path_appendix
        trt_engine_path = os.path.join(MODELS_DIRECTORY, trt_engine_name)
        print(f"Loading TensorRT engine from {trt_engine_path}.", file=sys.stderr)
        return torch.jit.load(trt_engine_path).eval()


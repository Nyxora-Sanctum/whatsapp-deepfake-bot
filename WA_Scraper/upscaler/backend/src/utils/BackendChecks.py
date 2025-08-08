from .Util import log, suppress_stdout_stderr, printAndLog

def checkForPytorchCUDA() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        import torch
        import torchvision

        if "cu" in torch.__version__:
            return True
        return False
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))


def checkForPytorchROCM() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        import torch
        import torchvision

        if "rocm" in torch.__version__:
            return True
        return False
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))

def checkForPytorchXPU() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        import torch
        import torchvision

        if torch.xpu.is_available():
            return True
        return False
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))

def checkForPytorchMPS() -> bool:
    try:
        import torch
        return torch.backends.mps.is_available()
    except ImportError as e:
        log(str(e))
        return False

def checkForTensorRT() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        import torch
        import torchvision
        import tensorrt

        with suppress_stdout_stderr():
            import torch_tensorrt
        return True
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))

def check_bfloat16_support() -> bool:
    """
    Function that checks if the torch backend supports bfloat16
    """
    import torch

    try:
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        x = torch.tensor([1.0], dtype=torch.float16).to(device=device)
        return True
    except RuntimeError:
        return False

def checkForDirectML() -> bool:
    """
    Function that checks if the onnxruntime DirectML backend is available
    """
    try:
        import onnxruntime as ort
        import onnx
        import onnxconverter_common

        # Check if DirectML execution provider is available
        providers = ort.get_available_providers()
        if "DmlExecutionProvider" in providers:
            return True
        else:
            log("DirectML execution provider not available")
            return False
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))
        return False
    
def checkForDirectMLHalfPrecisionSupport() -> bool:
    """
    Function that checks if the onnxruntime DirectML backend supports half precision
    """
    try:
        import onnxruntime as ort
        import numpy as np
        import onnx
        from onnx import helper, TensorProto

        # Check if DirectML execution provider is available
        providers = ort.get_available_providers()
        if "DmlExecutionProvider" in providers:
            # Create a dummy model with half precision input
            input_shape = [1, 3, 224, 224]  # Example input shape
            input_tensor = helper.make_tensor_value_info(
                "input", TensorProto.FLOAT16, input_shape
            )
            output_tensor = helper.make_tensor_value_info(
                "output", TensorProto.FLOAT16, input_shape
            )
            node = helper.make_node("Identity", ["input"], ["output"])
            graph = helper.make_graph([node], "test", [input_tensor], [output_tensor])

            # Create the model
            model = helper.make_model(graph, producer_name="test_model")

            # Add opset version
            opset = helper.make_operatorsetid(
                "", 13
            )  # Use opset version 13 or any other appropriate version
            model.opset_import.extend([opset])

            # Set the IR version
            model.ir_version = onnx.IR_VERSION

            # Create an inference session with DirectML execution provider
            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            session_options.add_session_config_entry("session.use_dml", "1")
            session = ort.InferenceSession(model.SerializeToString(), session_options)

            # Check if the model can be run with half precision input
            input_data = np.random.randn(*input_shape).astype(np.float16)
            outputs = session.run(None, {"input": input_data})

            return True
        else:
            log("DirectML execution provider not available")
            return False
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))
        return False


def checkForNCNN() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        from rife_ncnn_vulkan_python import Rife
        import ncnn

        try:
            from upscale_ncnn_py import UPSCALE
        except Exception:
            printAndLog(
                "Warning: Cannot import upscale_ncnn, falling back to default ncnn processing. (Please install vcredlist on your computer to fix this!)"
            )
        return True
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))


def get_gpus_torch():
    """
    Function that returns a list of available GPU names using PyTorch.
    """
    devices = []
    try:
        import torch

        if torch.cuda.is_available():
            for dev_index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(dev_index)
                devices.append(props.name)
        if not devices:
            devices.append("CPU")
    except ImportError as e:
        log(str(e))
        devices.append("CPU")
    except Exception as e:
        log(str(e))
        devices.append("CPU")
    return devices


def get_gpus_ncnn():
    devices = []
    try:
        with suppress_stdout_stderr():
            import ncnn

            gpu_count = ncnn.get_gpu_count()
            if gpu_count < 1:
                return ["CPU"]
            for i in range(gpu_count):
                device = ncnn.get_gpu_device(i)
                gpu_info = device.info()
                devices.append(gpu_info.device_name())
        return devices
    except Exception:
        return ["CPU"]
    except Exception as e:
        log(str(e))
        return "Unable to get NCNN GPU"
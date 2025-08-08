import onnx
import onnxruntime as ort
from onnxruntime import InferenceSession
from onnxconverter_common import float16
import os
import numpy as np
import time
import cv2

def getONNXScale(modelPath: str = "") -> int:
    paramName = os.path.basename(modelPath).lower()
    for i in range(100):
        if f"{i}x" in paramName or f"x{i}" in paramName:
            return i


class UpscaleONNX:
    def __init__(
        self,
        modelPath: str,
        device="default",
        tile_pad: int = 10,
        precision: str = "auto",
        width: int = 1920,
        height: int = 1080,
        tilesize: int = 0,
        gpu_id: int = 0,
        hdr_mode: bool = False,
    ):
        self.width = width
        self.height = height
        self.modelPath = modelPath
        self.device = device
        self.i0 = None
        self.precision = np.float16
        
        self.input_buffer = np.empty((1, 3, 1080, 1920), dtype=self.precision)
        self.output_buffer = np.empty((1, 3, 1080*2, 1920*2), dtype=self.precision)
        
        # Pre-compute normalization factor
        self.norm_factor = np.array(1.0/255.0, dtype=self.precision)

        # load model
        model = onnx.load(self.modelPath)
        if self.precision == np.float16:
            model = float16.convert_float_to_float16(model)
        self.model = model

            # Optimized DirectML provider options
        directml_options = {
            "device_id": gpu_id,
        #    "enable_dynamic_graph_fusion": True,
        #    "disable_memory_arena": False,  # Keep memory arena for better performance
        #   "memory_limit_in_mb": 0,  # Use all available memory
        }
        
        directml_backend = [("DmlExecutionProvider", directml_options)]

        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # session_options.enable_mem_pattern = True
        
        # Add these for better DirectML performance
        #session_options.add_session_config_entry("session.disable_prepacking", "0")
        #session_options.add_session_config_entry("session.enable_memory_efficient_execution", "1")
        
        self.inference_session = InferenceSession(
            self.model.SerializeToString(), session_options, providers=directml_backend
        )

    def bytesToFrame(self, image: bytes) -> tuple:
        temp_view = np.frombuffer(image, dtype=np.uint8)
        temp_view = temp_view.reshape(1080, 1920, 3)
        
        # Use direct assignment to pre-allocated buffer
        self.input_buffer[0] = np.transpose(temp_view, (2, 0, 1))
        
        # In-place normalization
        self.input_buffer *= self.norm_factor
            
        return self.input_buffer
        #image = np.frombuffer(image, dtype=np.uint8).reshape(1080, 1920, 3)
        #image = np.transpose(image, (2, 0, 1))
        #image = np.expand_dims(image, axis=0)
        #image = image.astype(self.precision)
        #image = image.__mul__(1.0 / 255.0)
        #return np.ascontiguousarray(image)

    def renderTensor(self, image_as_np_array: np.ndarray) -> np.ndarray:
        onnx_input = {self.inference_session.get_inputs()[0].name: image_as_np_array}
        onnx_output = self.inference_session.run(None, onnx_input)[0]
        return onnx_output

    def frameToBytes(self, image: np.ndarray) -> bytes:
        # Clip, transpose, scale and convert in optimized sequence
        #image = image[0]
        #image = np.clip(image, 0, 1)
        #image = image.transpose(1, 2, 0)
        
        # Use faster multiplication and conversion
        image *= 255.0
        image = image.astype(np.uint8)
        
        return np.ascontiguousarray(image).tobytes()


        


if __name__ == "__main__":
    #up = UpscaleONNX("2x_ModernSpanimationV1_clamp_fp16_op19_onnxslim.onnx")
    up = UpscaleONNX("converted_models/2x_2x_ModernSpanimationV2.pth.onnx")
    image = cv2.imread("photo.jpg")
    image = cv2.resize(image, (1920, 1080)).astype(np.uint8).tobytes()
    start_time = time.time()
    
    iter = 100
    for i in range(iter):
        image1 = up.bytesToFrame(image)
        output = up.renderTensor(image1)
        o = up.frameToBytes(output)
    end_time = time.time()
    output = up.frameToBytes(output)
    output = np.frombuffer(output, dtype=np.uint8).reshape(1080*2, 1920*2, 3)
    
    print(f"Processing time: {end_time - start_time:.2f} seconds")
    fps= iter / (end_time - start_time)
    print(f"FPS: {fps:.2f}")

    cv2.imwrite("output.jpg", output)
    print("Done")
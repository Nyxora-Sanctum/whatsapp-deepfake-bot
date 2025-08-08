import os
import re

from .Util import createDirectory, log, errorAndLog
from .constants import CUSTOM_MODELS_PATH
from .ui.QTcustom import RegularQTPopup

"""
Key value pairs of the model name in the GUI
Data inside the tuple:
[0] = file in models directory
[1] = file to download
[2] = upscale times
[3] = arch
"""
ncnnInterpolateModels = {
    "RIFE 4.6 (Fastest Model)": ("rife-v4.6", "rife-v4.6.tar.gz", 1, "rife46"),
    "RIFE 4.7 (Smoothest Model)": ("rife-v4.7", "rife-v4.7.tar.gz", 1, "rife47"),
    "RIFE 4.15": ("rife-v4.15", "rife-v4.15.tar.gz", 1, "rife413"),
    "RIFE 4.18 (Realistic)": (
        "rife-v4.18",
        "rife-v4.18.tar.gz",
        1,
        "rife413",
    ),
    "RIFE 4.22 (Slow, Animation)": (
        "rife-v4.22",
        "rife-v4.22.tar.gz",
        1,
        "rife421",
    ),
    "RIFE 4.22-lite (Latest LITE model)": (
        "rife-v4.22-lite",
        "rife-v4.22-lite.tar.gz",
        1,
        "rife422-lite",
    ),
    "RIFE 4.25": (
        "rife-v4.25",
        "rife-v4.25.tar.gz",
        1,
        "rife425",
    ),
    "RIFE 4.26 Heavy (Slowest RIFE Model, Animation)": (
        "rife-v4.26-heavy",
        "rife-v4.26-heavy.tar.gz",
        1,
        "rife425-heavy",
    ),
    "RIFE 4.26 (Latest General Model, Recommended)": (
        "rife-v4.26",
        "rife-v4.26.tar.gz",
        1,
        "rife425",
    ),
}
pytorchInterpolateModels = {
    "GMFSS (Slow Model, Animation)": ("GMFSS.pkl", "GMFSS.pkl", 1, "gmfss"),
    "GMFSS Pro (Slow Model, Animation) (Helps with text warping)": (
        "GMFSS_PRO.pkl",
        "GMFSS_PRO.pkl",
        1,
        "gmfss",
    ),
    "GIMM (Slow Model, Realistic/General)": (
        "GIMMVFI_RAFT.pth",
        "GIMMVFI_RAFT.pth",
        1,
        "gimm",
    ),
    "RIFE 4.6 (Fastest Model)": ("rife4.6.pkl", "rife4.6.pkl", 1, "rife46"),
    "RIFE 4.7 (Smoothest Model)": ("rife4.7.pkl", "rife4.7.pkl", 1, "rife47"),
    "RIFE 4.15": ("rife4.15.pkl", "rife4.15.pkl", 1, "rife413"),
    "RIFE 4.18 (Realistic)": (
        "rife4.18.pkl",
        "rife4.18.pkl",
        1,
        "rife413",
    ),
    "RIFE 4.22 (Slow, Animation)": (
        "rife4.22.pkl",
        "rife4.22.pkl",
        1,
        "rife421",
    ),
    "RIFE 4.22-lite (Latest LITE model)": (
        "rife4.22-lite.pkl",
        "rife4.22-lite.pkl",
        1,
        "rife422-lite",
    ),
    "RIFE 4.25": (
        "rife4.25.pkl",
        "rife4.25.pkl",
        1,
        "rife425",
    ),
    "RIFE 4.26 Heavy (Slowest RIFE Model, Animation)": (
        "rife4.26.heavy.pkl",
        "rife4.26.heavy.pkl",
        1,
        "rife425-heavy",
    ),
    "RIFE 4.26 (Latest General Model, Recommended)": (
        "rife4.26.pkl",
        "rife4.26.pkl",
        1,
        "rife425",
    ),
}
tensorrtInterpolateModels = {
    "GMFSS (Slow Model, Animation)": ("GMFSS.pkl", "GMFSS.pkl", 1, "gmfss"),
    "GMFSS Pro (Slow Model, Animation) (Helps with text warping)": (
        "GMFSS_PRO.pkl",
        "GMFSS_PRO.pkl",
        1,
        "gmfss",
    ),
    "RIFE 4.6 (Fastest Model)": ("rife4.6.pkl", "rife4.6.pkl", 1, "rife46"),
    "RIFE 4.7 (Smoothest Model)": ("rife4.7.pkl", "rife4.7.pkl", 1, "rife47"),
    "RIFE 4.15": ("rife4.15.pkl", "rife4.15.pkl", 1, "rife413"),
    "RIFE 4.18 (Realistic)": (
        "rife4.18.pkl",
        "rife4.18.pkl",
        1,
        "rife413",
    ),
    "RIFE 4.22 (Slow, Animation)": (
        "rife4.22.pkl",
        "rife4.22.pkl",
        1,
        "rife421",
    ),
    "RIFE 4.22-lite (Latest LITE model)": (
        "rife4.22-lite.pkl",
        "rife4.22-lite.pkl",
        1,
        "rife422-lite",
    ),
    "RIFE 4.25": (
        "rife4.25.pkl",
        "rife4.25.pkl",
        1,
        "rife425",
    ),
    "RIFE 4.26 Heavy (Slowest RIFE Model, Animation)": (
        "rife4.26.heavy.pkl",
        "rife4.26.heavy.pkl",
        1,
        "rife425-heavy",
    ),
    "RIFE 4.26 (Latest General Model, Recommended)": (
        "rife4.26.pkl",
        "rife4.26.pkl",
        1,
        "rife425",
    ),
}
ncnnUpscaleModels = {
    "OpenProteus (Realistic) (HD Input) (2X) (Fast)": (
        "2x_OpenProteus_Compact_i2_70K",
        "2x_OpenProteus_Compact_i2_70K.tar.gz",
        2,
        "Compact",
    ),
    
    "Nomos8k (Realistic) (High Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_weak",
        "4xNomos8k_span_otf_weak.tar.gz",
        4,
        "SPAN",
    ),
    "Nomos8k (Realistic) (Medium Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_medium",
        "4xNomos8k_span_otf_medium.tar.gz",
        4,
        "SPAN",
    ),
    "Nomos8k (Realistic) (Low Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_strong",
        "4xNomos8k_span_otf_strong.tar.gz",
        4,
        "SPAN",
    ),
    "RealCUGAN Pro (Animation) (2X) (Slow)": (
        "up2x-conservative",
        "up2x-conservative.tar.gz",
        2,
        "compact",
    ),
    "RealCUGAN Pro (Animation) (3X) (Slow)": (
        "up3x-conservative",
        "up2x-conservative.tar.gz",
        3,
        "compact",
    ),
    "RealisticVideo (4X) (Fast)": (
        "realesr-general-x4v3",
        "realesr-general-x4v3.tar.gz",
        4,
        "Compact",
    ),
    
    "JaNai V2 (Animation) (2X) (Fast)": (
        "2x_AnimeJaNai_V2_Compact_36k",
        "2x_AnimeJaNai_V2_Compact_36k.tar.gz",
        2,
        "Compact",
    ),
    "JaNai V3 (Animation) (2X) (Fast)": (
        "2x_AnimeJaNai_HD_V3_Sharp1_Compact_430k",
        "2x_AnimeJaNai_HD_V3_Sharp1_Compact_430k.tar.gz",
        2,
        "Compact",
    ),
    "Spanimation (Animation) (2X) (Fast)": (
        "2x_ModernSpanimationV2",
        "2x_ModernSpanimationV2.tar.gz",
        2,
        "SPAN",
    ),
    "ESRGAN AnimeVideo V3 (Animation) (2X) (Fast)": (
        "realesr-animevideov3-x2",
        "realesr-animevideov3-x2.tar.gz",
        2,
        "compact",
    ),
    "AniSD (Old Animation) (High Quality Source) (2X) (Fast)": (
        "2x_AniSD_G6i1_SPAN_215K.ncnn",
        "2x_AniSD_G6i1_SPAN_215K.ncnn.tar.gz",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (Medium Quality Source) (2X) (Fast)": (
        "2x_AniSD_AC_G6i2b_SPAN_190K.ncnn",
        "2x_AniSD_AC_G6i2b_SPAN_190K.ncnn.tar.gz",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (Low Quality Source) (2X) (Fast)": (
        "2x_AniSD_DC_SPAN_92500.ncnn",
        "2x_AniSD_DC_SPAN_92500.ncnn.tar.gz",
        2,
        "SPAN",
    ),
    "ESRGAN AnimeVideo V3 (Animation) (3X) (Fast)": (
        "realesr-animevideov3-x3",
        "realesr-animevideov3-x3.tar.gz",
        3,
        "compact",
    ),
    "ESRGAN AnimeVideo V3 (Animation) (4X) (Fast)": (
        "realesr-animevideov3-x4",
        "realesr-animevideov3-x4.tar.gz",
        4,
        "compact",
    ),
    "ESRGAN Plus (General Model) (4X) (Slow)": (
        "realesrgan-x4plus",
        "realesrgan-x4plus.tar.gz",
        4,
        "esrgan",
    ),
    "ESRGAN Plus (Animation Model) (4X) (Slow)": (
        "realesrgan-x4plus-anime",
        "realesrgan-x4plus-anime.tar.gz",
        4,
        "esrgan",
    ),
}

pytorchUpscaleModels = {
    "OpenProteus (Realistic) (HD Input) (2X) (Fast)": (
        "2x_OpenProteus_Compact_i2_70K.pth",
        "2x_OpenProteus_Compact_i2_70K.pth",
        2,
        "Compact",
    ),
    "Nomos8k (Realistic) (High Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_weak_no_update_params.pth",
        "4xNomos8k_span_otf_weak_no_update_params.pth",
        4,
        "SPAN",
    ),
    "Nomos8k (Realistic) (Medium Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_medium_no_update_params.pth",
        "4xNomos8k_span_otf_medium_no_update_params.pth",
        4,
        "SPAN",
    ),
    "Nomos8k (Realistic) (Low Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_strong_no_update_params.pth",
        "4xNomos8k_span_otf_strong_no_update_params.pth",
        4,
        "SPAN",
    ),
    "RealisticVideo (4X) (Fast)": (
        "realesr-general-x4v3.pth",
        "realesr-general-x4v3.pth",
        4,
        "Compact",
    ),
    
    "JaNai V2 (Animation) (2X) (Fast)": (
        "2x_AnimeJaNai_V2_Compact_36k.pth",
        "2x_AnimeJaNai_V2_Compact_36k.pth",
        2,
        "Compact",
    ),
    "JaNai V3 (Animation) (2X) (Fast)": (
        "2x_AnimeJaNai_HD_V3_Sharp1_Compact_430k.pth",
        "2x_AnimeJaNai_HD_V3_Sharp1_Compact_430k.pth",
        2,
        "Compact",
    ),
    "Sudo Shuffle SPAN (Animation) (2X) (Fast)": (
        "2xSudo_Shuffle_Span_no_update_params.pth",
        "2xSudo_Shuffle_Span_no_update_params.pth",
        2,
        "SPAN",
    ),
    "SPAN Spanimation V2 (Animation) (2X) (Fast)": (
        "2x_ModernSpanimationV2.pth",
        "2x_ModernSpanimationV2.pth",
        2,
        "SPAN",
    ),
    "SPANPlus Spanimation V3 (Animation) (2X) (Fast)": (
        "2x_ModernSpanimationV3.pth",
        "2x_ModernSpanimationV3.pth",
        2,
        "SPANPlus",
    ),
    "SPANPlus Dynamic BHI (Realistic) (2X) (Fast)": (
        "2x_BHI_SpanPlusDynamic_Light.pth",
        "2x_BHI_SpanPlusDynamic_Light.pth",
        2,
        "SPANPlus",
    ),
    "AniSD (Old Animation) (High Quality Source) (2X) (Fast)": (
        "2x_AniSD_G6i1_SPAN_215K.pth",
        "2x_AniSD_G6i1_SPAN_215K.pth",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (Medium Quality Source) (2X) (Fast)": (
        "2x_AniSD_AC_G6i2b_SPAN_190K.pth",
        "2x_AniSD_AC_G6i2b_SPAN_190K.pth",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (Low Quality Source) (2X) (Fast)": (
        "2x_AniSD_DC_SPAN_92500.pth",
        "2x_AniSD_DC_SPAN_92500.pth",
        2,
        "SPAN",
    ),
}

tensorrtUpscaleModels = {

    "OpenProteus (Realistic) (HD Input) (2X) (Fast)": (
        "2x_OpenProteus_Compact_i2_70K.pth",
        "2x_OpenProteus_Compact_i2_70K.pth",
        2,
        "Compact",
    ),

    "Nomos8k (Realistic) (High Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_weak_no_update_params.pth",
        "4xNomos8k_span_otf_weak_no_update_params.pth",
        4,
        "SPAN",
    ),
    "Nomos8k (Realistic) (Medium Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_medium_no_update_params.pth",
        "4xNomos8k_span_otf_medium_no_update_params.pth",
        4,
        "SPAN",
    ),
    "Nomos8k (Realistic) (Low Quality Source) (4X) (Fast)": (
        "4xNomos8k_span_otf_strong_no_update_params.pth",
        "4xNomos8k_span_otf_strong_no_update_params.pth",
        4,
        "SPAN",
    ),
    
    "RealisticVideo (4X) (Fast)": (
        "realesr-general-x4v3.pth",
        "realesr-general-x4v3.pth",
        4,
        "Compact",
    ),
    "JaNai V2 (Animation) (2X) (Fast)": (
        "2x_AnimeJaNai_V2_Compact_36k.pth",
        "2x_AnimeJaNai_V2_Compact_36k.pth",
        2,
        "Compact",
    ),
    "JaNai V3 (Animation) (2X) (Fast)": (
        "2x_AnimeJaNai_HD_V3_Sharp1_Compact_430k.pth",
        "2x_AnimeJaNai_HD_V3_Sharp1_Compact_430k.pth",
        2,
        "Compact",
    ),
    "Spanimation V2 (Animation) (2X) (Fast)": (
        "2x_ModernSpanimationV2.pth",
        "2x_ModernSpanimationV2.pth",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (High Quality Source) (2X) (Fast)": (
        "2x_AniSD_G6i1_SPAN_215K.pth",
        "2x_AniSD_G6i1_SPAN_215K.pth",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (Medium Quality Source) (2X) (Fast)": (
        "2x_AniSD_AC_G6i2b_SPAN_190K.pth",
        "2x_AniSD_AC_G6i2b_SPAN_190K.pth",
        2,
        "SPAN",
    ),
    "AniSD (Old Animation) (Low Quality Source) (2X) (Fast)": (
        "2x_AniSD_DC_SPAN_92500.pth",
        "2x_AniSD_DC_SPAN_92500.pth",
        2,
        "SPAN",
    ),

}

ncnnDeblurModels = {
    "NAFNet GoPro (Deblur) (Slow)": (
        "nafnet_gopro1x.ncnn",
        "nafnet_gopro1x.ncnn.tar.gz",
        1,
        "nafnet",
    ),
}

pytorchDeblurModels = {
    "NAFNet GoPro (Deblur) (Slow)": (
        "nafnet_gopro1x.pth",
        "nafnet_gopro1x.pth",
        1,
        "nafnet",
    ),
}

tensorrtDeblurModels = {
    "NAFNet GoPro (Deblur) (Slow)": (
        "nafnet_gopro1x.pth",
        "nafnet_gopro1x.pth",
        1,
        "nafnet",
    ),
}
ncnnDenoiseModels = {
    "NAFNet SIDD (1x) (Slow)": (
        "1x_NAFNet-SIDD-width32",
        "1x_NAFNet-SIDD-width32.tar.gz",
        1,
        "scunet",
    )
}

pytorchDenoiseModels = {
    "NAFNet SIDD (1x) (Slow)": (
        "1xNAFNet-SIDD-width32.pth",
        "1xNAFNet-SIDD-width32.pth",
        1,
        "scunet",
    ),
    "SCUNet Color (1x) (Slow)": (
        "scunet_color_real_psnr.pth",
        "scunet_color_real_psnr.pth",
        1,
        "scunet",
    )
}

tensorrtDenoiseModels = {
    "NAFNet SIDD (1x) (Slow)": (
        "1xNAFNet-SIDD-width32.pth",
        "1xNAFNet-SIDD-width32.pth",
        1,
        "scunet",
    ),
    "SCUNet Color (1x) (Slow)": (
        "scunet_color_real_psnr.pth",
        "scunet_color_real_psnr.pth",
        1,
        "scunet",
    )
}

onnxInterpolateModels = {
    "RIFE 4.22 (Recommended Model)": (
        "rife422_v2_ensembleFalse_op20_clamp.onnx",
        "rife422_v2_ensembleFalse_op20_clamp.onnx",
        1,
        "rife422-lite",
    ),
}
onnxUpscaleModels = {
    "SPAN (Animation) (2X)": (
        "2x_ModernSpanimationV2_clamp_op20.onnx",
        "2x_ModernSpanimationV2_clamp_op20.onnx",
        2,
        "SPAN",
    ),
}



def getCustomModelScale(model):
    pattern = r"\d+x|x+\d"
    matches = re.findall(pattern, model)
    if len(matches) > 0:
        upscaleFactor = int(matches[0].replace("x", ""))
        return upscaleFactor
    return None


# detect custom models
createDirectory(CUSTOM_MODELS_PATH)
customPytorchUpscaleModels = {}
customNCNNUpscaleModels = {}
for model in os.listdir(CUSTOM_MODELS_PATH):
    upscaleFactor = getCustomModelScale(model)
    if upscaleFactor:
        model_path = os.path.join(CUSTOM_MODELS_PATH, model)
        if os.path.exists(model_path):
            if not os.path.isfile(model_path):
                customNCNNUpscaleModels[model] = (model, model, upscaleFactor, "custom")
        if model.endswith(".pth") or model.endswith(".safetensors"):
            customPytorchUpscaleModels[model] = (model, model, upscaleFactor, "custom")
    else:
        log(
            f"Custom model {model} does not have a valid upscale factor in the name, example: 2x or x2. Skipping import..."
        )

pytorchUpscaleModels = pytorchUpscaleModels | customPytorchUpscaleModels
tensorrtUpscaleModels = tensorrtUpscaleModels | customPytorchUpscaleModels
ncnnUpscaleModels = ncnnUpscaleModels | customNCNNUpscaleModels
totalModels = (
    onnxInterpolateModels
    | onnxUpscaleModels
    | pytorchInterpolateModels
    | pytorchUpscaleModels
    | pytorchDenoiseModels
    | pytorchDeblurModels
    | ncnnDeblurModels
    | ncnnInterpolateModels
    | ncnnUpscaleModels
    | tensorrtInterpolateModels
    | tensorrtUpscaleModels
    | tensorrtDeblurModels
)  # this doesnt include all models due to overwriting, but includes every case of every unique model name


def getModels(backend:str):
    """
    returns models based on backend, used for populating the model comboboxes [interpolate, upscale]
    """
    match backend.split(" ")[0]:
        case "ncnn":
            interpolateModels = ncnnInterpolateModels
            upscaleModels = ncnnUpscaleModels
            deblurModels = ncnnDeblurModels
            denoiseModels = ncnnDenoiseModels
        case "pytorch":
            interpolateModels = pytorchInterpolateModels
            upscaleModels = pytorchUpscaleModels
            deblurModels = pytorchDeblurModels
            denoiseModels = pytorchDenoiseModels
        case "tensorrt":
            interpolateModels = tensorrtInterpolateModels
            upscaleModels = tensorrtUpscaleModels
            deblurModels = tensorrtDeblurModels
            denoiseModels = tensorrtDenoiseModels
        case "directml":
            interpolateModels = onnxInterpolateModels
            upscaleModels = onnxUpscaleModels
            deblurModels = {}
        case _:
            RegularQTPopup(
                "Failed to import any backends!, please try to reinstall the app!"
            )
            errorAndLog("Failed to import any backends!")
            return {}
    return interpolateModels, upscaleModels, deblurModels, denoiseModels

"""
美颜参数辅助（headphoto / zhpt-new 共用）

美颜的取值范围与裁剪逻辑统一由 ``services/hivision_processor.normalize_beauty`` 负责，
这里只负责把 API 层的表单参数组装成它需要的字典。

⚠️ 全部默认 0 = 不做任何美颜，**保持历史行为不变**。
"""

# API 表单参数 → hivision IDCreator 参数名 的映射
BEAUTY_FORM_FIELDS = (
    ("whitening_strength", 0),   # 美白强度 0-30
    ("brightness_strength", 0),  # 亮度 -20~20
    ("contrast_strength", 0),    # 对比度 -100~100
    ("sharpen_strength", 0),     # 锐化 0-5
    ("saturation_strength", 0),  # 饱和度 -100~100
)


def build_beauty_params(
    whitening_strength: int = 0,
    brightness_strength: int = 0,
    contrast_strength: int = 0,
    sharpen_strength: int = 0,
    saturation_strength: int = 0,
) -> dict:
    """把 API 层的美颜表单参数组装成 processor 层需要的字典。"""
    return {
        "whitening_strength": whitening_strength,
        "brightness_strength": brightness_strength,
        "contrast_strength": contrast_strength,
        "sharpen_strength": sharpen_strength,
        "saturation_strength": saturation_strength,
    }

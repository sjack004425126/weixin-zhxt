import cv2
from hivision.creator.context import Context
from hivision.plugin.beauty.whitening import make_whitening
from hivision.plugin.beauty.base_adjust import (
    adjust_brightness_contrast_sharpen_saturation,
)


def beauty_face(ctx: Context):
    """
    对人脸进行美颜处理
    1. 美白
    2. 亮度/对比度/锐化/饱和度

    通道约定：``ctx.origin_image`` 与 ``ctx.matting_image`` 均为 **BGR**（OpenCV 内存布局）。
    美白 LUT 与亮度调整都按 BGR 设计，因此这里不做任何色彩空间转换。

    :param ctx: Context对象，包含处理参数和图像
    """
    middle_image = ctx.origin_image.copy()
    processed = False

    # 如果美白强度大于0，进行美白处理
    if ctx.params.whitening_strength > 0:
        middle_image = make_whitening(middle_image, ctx.params.whitening_strength)
        processed = True

    # 如果亮度、对比度、锐化强度不为0，进行亮度、对比度、锐化处理
    if (
        ctx.params.brightness_strength != 0
        or ctx.params.contrast_strength != 0
        or ctx.params.sharpen_strength != 0
        or ctx.params.saturation_strength != 0
    ):
        middle_image = adjust_brightness_contrast_sharpen_saturation(
            middle_image,
            ctx.params.brightness_strength,
            ctx.params.contrast_strength,
            ctx.params.sharpen_strength,
            ctx.params.saturation_strength,
        )
        processed = True

    # 如果进行了美颜处理，更新matting_image
    if processed:
        middle_image = middle_image[:, :, :3]

        # 抠图结果可能是 3 通道（无 alpha）或 4 通道（BGRA）。
        # 原实现硬编码 `cv2.split(ctx.matting_image)` 取 4 个通道，
        # 遇到 3 通道输入会直接抛 ValueError；这里按实际通道数自适应。
        if ctx.matting_image is not None and ctx.matting_image.ndim == 3:
            if ctx.matting_image.shape[2] >= 4:
                # 分离中间图像的BGR通道
                b, g, r = cv2.split(middle_image)
                # 从原始matting_image中获取alpha通道
                _, _, _, alpha = cv2.split(ctx.matting_image)
                # 合并处理后的BGR通道和原始alpha通道
                ctx.matting_image = cv2.merge((b, g, r, alpha))
            else:
                # 无 alpha 通道，直接整体替换
                ctx.matting_image = middle_image.copy()
        else:
            ctx.matting_image = middle_image.copy()

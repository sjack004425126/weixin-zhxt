"""
HivisionIDPhotos 证件照处理服务
功能：人像抠图、背景替换、尺寸调整、美颜
可配置：输出尺寸、背景颜色、美颜强度
"""
import os
import logging
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CONFIG = {
    # 证件照尺寸 (高度, 宽度)
    "size": (626, 413),  # 一寸照片
    # 背景颜色 (B, G, R)
    "bg_color": (219, 142, 67),  # 蓝色背景 RGB(67, 142, 219)
    # 抠图模型
    "matting_model": "modnet_photographic_portrait_matting",
    # 人脸检测模型
    "face_detect_model": "mtcnn",
    # 是否输出高清照
    "hd": True,
    # DPI
    "dpi": 300,
    # 去背景处理后的目标宽度（像素），按比例缩放高度，为None则保持原图比例
    # 413 = 二寸证件照标准宽度（与 PHOTO_SIZES["two_inch"] 保持一致）
    "target_width": 413,
    # 去背景处理后的目标高度（像素），按比例缩放宽度，为None则保持原图比例
    "target_height": None,
}

# 美颜参数默认值（全部为 0 = 不做任何美颜，保持历史行为）
DEFAULT_BEAUTY: Dict[str, int] = {
    "whitening_strength": 0,      # 美白强度 0-30
    "brightness_strength": 0,     # 亮度 -20 ~ 20
    "contrast_strength": 0,       # 对比度 -100 ~ 100
    "sharpen_strength": 0,        # 锐化 0-5
    "saturation_strength": 0,     # 饱和度 -100 ~ 100
}

# 美颜参数取值范围（用于入参裁剪，避免异常值把图处理坏）
BEAUTY_LIMITS: Dict[str, Tuple[int, int]] = {
    "whitening_strength": (0, 30),
    "brightness_strength": (-20, 20),
    "contrast_strength": (-100, 100),
    "sharpen_strength": (0, 5),
    "saturation_strength": (-100, 100),
}

# 预设尺寸
PHOTO_SIZES = {
    "one_inch": (413, 295),      # 一寸 35x25mm
    "two_inch": (626, 413),      # 二寸 53x35mm
    "small_one_inch": (378, 260), # 小一寸 32x22mm
    "small_two_inch": (531, 413), # 小二寸 45x35mm
    "large_one_inch": (567, 390), # 大一寸 48x33mm
    "large_two_inch": (626, 413), # 大二寸 53x35mm
}

# 预设背景颜色 (B, G, R)
BG_COLORS = {
    "blue": (219, 142, 67),      # 蓝色 RGB(67, 142, 219)
    "white": (255, 255, 255),    # 白色
    "red": (0, 0, 255),          # 红色
    "light_blue": (238, 216, 173), # 浅蓝色 RGB(173, 216, 238)
}


def normalize_beauty(beauty: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """把外部传入的美颜参数规整成安全的整数字典。

    - 未知键忽略
    - 缺省键补 0（即不做该项美颜）
    - 数值裁剪到 BEAUTY_LIMITS 定义的范围
    - 非数值一律按 0 处理

    这样即使前端传了脏数据，也不会把图片处理坏。
    """
    result = dict(DEFAULT_BEAUTY)
    if not beauty:
        return result

    for key, default in DEFAULT_BEAUTY.items():
        if key not in beauty:
            continue
        value = beauty.get(key)
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            logger.warning(f"美颜参数 {key}={value!r} 不是有效整数，已忽略")
            continue
        lo, hi = BEAUTY_LIMITS[key]
        if ivalue < lo or ivalue > hi:
            logger.warning(f"美颜参数 {key}={ivalue} 超出范围 [{lo}, {hi}]，已裁剪")
            ivalue = max(lo, min(hi, ivalue))
        result[key] = ivalue

    return result


def has_beauty(beauty: Dict[str, int]) -> bool:
    """判断美颜参数里是否有任何一项非 0。"""
    return any(v != 0 for v in beauty.values())


class HivisionProcessor:
    """HivisionIDPhotos 证件照处理器"""

    def __init__(self):
        self.creator = None
        self._initialized = False

    def _init_creator(self):
        """延迟初始化 IDCreator"""
        if self._initialized:
            return

        try:
            from hivision import IDCreator
            from hivision.creator.choose_handler import choose_handler

            self.creator = IDCreator()
            choose_handler(
                self.creator,
                DEFAULT_CONFIG["matting_model"],
                DEFAULT_CONFIG["face_detect_model"]
            )
            self._initialized = True
            logger.info("HivisionIDPhotos 初始化成功")
        except Exception as e:
            logger.error(f"HivisionIDPhotos 初始化失败: {str(e)}")
            raise

    def process_id_photo(
        self,
        image_data: bytes,
        size: Tuple[int, int] = None,
        bg_color: Tuple[int, int, int] = None,
        size_name: str = None,
        bg_color_name: str = None,
        beauty: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        处理证件照

        Args:
            image_data: 原始图片二进制数据
            size: 输出尺寸 (高度, 宽度)，优先级高于 size_name
            bg_color: 背景颜色 (B, G, R)，优先级高于 bg_color_name
            size_name: 预设尺寸名称 (one_inch, two_inch, etc.)
            bg_color_name: 预设颜色名称 (blue, white, red, light_blue)
            beauty: 美颜参数（whitening/brightness/contrast/sharpen/saturation），
                    默认全 0 = 不美颜

        Returns:
            处理后的图片二进制数据
        """
        logger.info(f"开始处理证件照，原始大小: {len(image_data)} bytes")

        beauty_params = normalize_beauty(beauty)
        apply_beauty = has_beauty(beauty_params)
        if apply_beauty:
            logger.info(f"启用美颜: {beauty_params}")

        # 解析尺寸
        if size is None:
            if size_name and size_name in PHOTO_SIZES:
                size = PHOTO_SIZES[size_name]
            else:
                size = DEFAULT_CONFIG["size"]

        # 解析背景颜色
        if bg_color is None:
            if bg_color_name and bg_color_name in BG_COLORS:
                bg_color = BG_COLORS[bg_color_name]
            else:
                bg_color = DEFAULT_CONFIG["bg_color"]

        logger.info(f"输出尺寸: {size}, 背景颜色BGR: {bg_color}")

        try:
            self._init_creator()

            # 将bytes转换为numpy数组
            nparr = np.frombuffer(image_data, np.uint8)
            input_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if input_image is None:
                raise ValueError("无法解析图片数据")

            # 调用HivisionIDPhotos处理
            from hivision.error import FaceError
            from hivision.utils import add_background

            try:
                result = self.creator(input_image, size=size, **beauty_params)
            except (FaceError, ValueError, Exception) as e:
                logger.warning(f"人脸检测失败: {str(e)}，尝试仅抠图模式")
                try:
                    # 兜底分支同样要带上美颜参数，否则美颜会被静默丢弃
                    result = self.creator(input_image, change_bg_only=True, **beauty_params)
                except Exception as e2:
                    logger.error(f"抠图模式也失败: {str(e2)}")
                    raise ValueError("照片处理失败，请确保照片中有清晰的人像，建议重新拍摄或选择光线充足的照片")

            # 获取抠图结果并添加背景
            matting_image = result.hd if result.hd is not None else result.standard

            # 添加背景颜色
            result_image = add_background(matting_image, bgr=bg_color, mode="pure_color")
            result_image = result_image.astype(np.uint8)

            # 如果有标准尺寸结果，使用它
            if result.standard is not None and not np.array_equal(result.standard, result.hd):
                standard_with_bg = add_background(result.standard, bgr=bg_color, mode="pure_color")
                result_image = standard_with_bg.astype(np.uint8)

            # 转换颜色空间 (BGR -> RGB)
            result_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB)

            # 保存为JPEG
            img = Image.fromarray(result_image)
            output_buffer = BytesIO()
            img.save(output_buffer, format='JPEG', quality=95, dpi=(DEFAULT_CONFIG["dpi"], DEFAULT_CONFIG["dpi"]))
            output_buffer.seek(0)

            output_data = output_buffer.getvalue()
            logger.info(f"证件照处理成功，输出大小: {len(output_data)} bytes")
            return output_data

        except ImportError as e:
            logger.error(f"HivisionIDPhotos 导入失败: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"证件照处理失败: {str(e)}")
            raise

    def remove_background(
        self,
        image_data: bytes,
        bg_color: Tuple[int, int, int] = None,
        bg_color_name: str = None,
        target_width: int = None,
        target_height: int = None,
        beauty: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        去除背景并替换为纯色背景

        Args:
            image_data: 原始图片二进制数据
            bg_color: 背景颜色 (B, G, R)
            bg_color_name: 预设颜色名称 (blue, white, red, light_blue)
            target_width: 目标宽度（像素），按比例缩放高度，为None则保持原图比例
            target_height: 目标高度（像素），按比例缩放宽度，为None则保持原图比例
            beauty: 美颜参数，默认全 0 = 不美颜

        Returns:
            处理后的图片二进制数据
        """
        logger.info(f"开始去背景处理，原始大小: {len(image_data)} bytes")

        beauty_params = normalize_beauty(beauty)
        apply_beauty = has_beauty(beauty_params)
        if apply_beauty:
            logger.info(f"启用美颜: {beauty_params}")

        # 解析背景颜色
        if bg_color is None:
            if bg_color_name and bg_color_name in BG_COLORS:
                bg_color = BG_COLORS[bg_color_name]
            else:
                bg_color = BG_COLORS["white"]  # 默认白色背景

        # 使用默认值
        if target_width is None:
            target_width = DEFAULT_CONFIG.get("target_width")
        if target_height is None:
            target_height = DEFAULT_CONFIG.get("target_height")

        logger.info(f"背景颜色BGR: {bg_color}")
        logger.info(f"目标尺寸: target_width={target_width}, target_height={target_height}")

        try:
            self._init_creator()

            # 将bytes转换为numpy数组
            nparr = np.frombuffer(image_data, np.uint8)
            input_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if input_image is None:
                raise ValueError("无法解析图片数据")

            original_height, original_width = input_image.shape[:2]

            from hivision.utils import add_background

            # 只做抠图，不调整尺寸
            try:
                result = self.creator(input_image, change_bg_only=True, **beauty_params)
            except Exception as e:
                logger.error(f"抠图失败: {str(e)}")
                raise ValueError("照片处理失败，请确保照片中有清晰的人像，建议重新拍摄或选择光线充足的照片")

            # 获取抠图结果
            matting_image = result.hd if result.hd is not None else result.standard

            # 添加背景颜色
            result_image = add_background(matting_image, bgr=bg_color, mode="pure_color")
            result_image = result_image.astype(np.uint8)

            # 按比例缩放图片
            if target_width is not None or target_height is not None:
                h, w = result_image.shape[:2]
                if target_width is not None and target_height is not None:
                    # 固定宽高（可能变形，不推荐）
                    new_w, new_h = target_width, target_height
                elif target_width is not None:
                    # 固定宽度，按比例缩放高度
                    new_w, new_h = target_width, int(h * target_width / w)
                else:  # target_height is not None
                    # 固定高度，按比例缩放宽度
                    new_w, new_h = int(w * target_height / h), target_height

                result_image = cv2.resize(result_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
                logger.info(f"图片已缩放至 {new_w}x{new_h}")

            # 转换颜色空间 (BGR -> RGB)
            result_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB)

            # 保存为JPEG
            img = Image.fromarray(result_image)
            output_buffer = BytesIO()
            img.save(output_buffer, format='JPEG', quality=95)
            output_buffer.seek(0)

            output_data = output_buffer.getvalue()
            logger.info(f"去背景处理成功，输出大小: {len(output_data)} bytes")
            return output_data

        except ImportError as e:
            logger.error(f"HivisionIDPhotos 导入失败: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"去背景处理失败: {str(e)}")
            raise

# 全局处理器实例
_processor: Optional[HivisionProcessor] = None


def get_processor() -> HivisionProcessor:
    """获取全局处理器实例"""
    global _processor
    if _processor is None:
        _processor = HivisionProcessor()
    return _processor


def process_id_photo(
    image_data: bytes,
    size: Tuple[int, int] = None,
    bg_color: Tuple[int, int, int] = None,
    size_name: str = None,
    bg_color_name: str = None,
    beauty: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    处理证件照的便捷函数

    Args:
        image_data: 原始图片二进制数据
        size: 输出尺寸 (高度, 宽度)
        bg_color: 背景颜色 (B, G, R)
        size_name: 预设尺寸名称
        bg_color_name: 预设颜色名称
        beauty: 美颜参数（默认全 0 = 不美颜）

    Returns:
        处理后的图片二进制数据
    """
    processor = get_processor()
    return processor.process_id_photo(
        image_data,
        size=size,
        bg_color=bg_color,
        size_name=size_name,
        bg_color_name=bg_color_name,
        beauty=beauty,
    )


def remove_background(
    image_data: bytes,
    bg_color: Tuple[int, int, int] = None,
    bg_color_name: str = None,
    target_width: int = None,
    target_height: int = None,
    beauty: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    去除背景并替换为纯色背景

    Args:
        image_data: 原始图片二进制数据
        bg_color: 背景颜色 (B, G, R)
        bg_color_name: 预设颜色名称
        target_width: 目标宽度（像素），按比例缩放高度
        target_height: 目标高度（像素），按比例缩放宽度
        beauty: 美颜参数（默认全 0 = 不美颜）

    Returns:
        处理后的图片二进制数据
    """
    processor = get_processor()
    return processor.remove_background(
        image_data,
        bg_color=bg_color,
        bg_color_name=bg_color_name,
        target_width=target_width,
        target_height=target_height,
        beauty=beauty,
    )

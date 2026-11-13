import cv2
import numpy as np
import os


class LutWhite:
    """3D LUT 查表美白。

    ⚠️ ``lut_origin.png`` 的真实结构是 **8x8 网格、每格 64x64**（512 = 8 x 64），
    每格是一个 64 级色立方体的切片。原实现切片时误用了 ``CUBE256_SIZE``(256)
    作为格子边长，取到的根本不是正确的立方体切片，导致查表结果全黑。
    """

    CUBE64_ROWS = 8
    CUBE64_SIZE = 64
    CUBE256_SIZE = 256
    CUBE_SCALE = CUBE256_SIZE // CUBE64_SIZE  # 4

    def __init__(self, lut_image):
        self.lut = self._create_lut(lut_image)

    def _create_lut(self, lut_image):
        reshape_lut = np.zeros(
            (self.CUBE256_SIZE, self.CUBE256_SIZE, self.CUBE256_SIZE, 3), dtype=np.uint8
        )
        for i in range(self.CUBE64_SIZE):
            tmp = i // self.CUBE64_ROWS
            cx = (i % self.CUBE64_ROWS) * self.CUBE64_SIZE
            cy = tmp * self.CUBE64_SIZE
            cube64 = lut_image[cy : cy + self.CUBE64_SIZE, cx : cx + self.CUBE64_SIZE]
            if cube64.size == 0:
                continue
            cube256 = cv2.resize(cube64, (self.CUBE256_SIZE, self.CUBE256_SIZE))
            reshape_lut[i * self.CUBE_SCALE : (i + 1) * self.CUBE_SCALE] = cube256
        return reshape_lut

    def apply(self, src):
        b, g, r = src[:, :, 0], src[:, :, 1], src[:, :, 2]
        return self.lut[b, g, r]


class MakeWhiter:
    def __init__(self, lut_image):
        self.lut_white = LutWhite(lut_image)

    def run(self, src: np.ndarray, strength: int) -> np.ndarray:
        strength = np.clip(strength / 10.0, 0, 1)
        if strength <= 0:
            return src
        img = self.lut_white.apply(src[:, :, :3])
        return cv2.addWeighted(src[:, :, :3], 1 - strength, img, strength, 0)


base_dir = os.path.dirname(os.path.abspath(__file__))
default_lut = cv2.imread(os.path.join(base_dir, "lut/lut_origin.png"))
make_whiter = MakeWhiter(default_lut)


def make_whitening(image, strength):
    """对图像做美白（LUT）。

    ⚠️ 通道约定：**输入输出均为 BGR**（OpenCV 内存布局）。

    历史包袱：原实现写成 ``COLOR_RGB2BGR`` → 处理 → ``COLOR_BGR2RGB``，
    相当于把 RGB 数据当成 BGR 处理、再转回去，**净效果是一次通道翻转**，
    导致肤色偏色（实测：同一张肤色图，按 BGR 传入亮度仅 +2，按 RGB 传入 +51.7）。

    这里的 LUT 是按 (B, G, R) 索引的标准 3D LUT，直接作用在 BGR 上即可，
    不需要任何色彩空间转换。调用方（beauty/handler.py）传入的也是 BGR。
    """
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("美白输入必须是 HxWx3 或 HxWx4 的图像数组")

    bgr = image[:, :, :3]

    iteration = strength // 10
    bias = strength % 10

    for _ in range(iteration):
        bgr = make_whiter.run(bgr, 10)

    bgr = make_whiter.run(bgr, bias)

    return bgr


def make_whitening_png(image, strength):
    """RGBA 版本美白，保留 alpha 通道。输入输出均为 BGR。"""
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError("make_whitening_png 输入必须是 HxWx4 的图像数组")

    b, g, r, a = cv2.split(image)
    bgr_image = cv2.merge((b, g, r))

    b_w, g_w, r_w = cv2.split(make_whiter.run(bgr_image, strength))
    output_image = cv2.merge((b_w, g_w, r_w, a))

    return output_image


# 启动Gradio应用（仅手动调试用；gradio 不是运行期依赖）
if __name__ == "__main__":
    import gradio as gr

    demo = gr.Interface(
        fn=make_whitening,
        inputs=[
            gr.Image(type="numpy", label="Input Image"),
            gr.Slider(0, 30, step=1, label="Whitening Strength"),
        ],
        outputs=gr.Image(type="numpy"),
        title="Image Whitening Demo",
        description="Upload an image and adjust the whitening strength to see the effect.",
    )
    demo.launch()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF文本添加工具类
支持在PDF的指定页面和位置添加文本
"""

import os
import io
import logging
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.colors import Color, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class PdfTextGenerator:
    """PDF文本添加工具类"""
    
    def __init__(self):
        """初始化"""
        self.chinese_font_name = 'KaiTi_GB2312'
        self.setup_fonts()

    def setup_fonts(self):
        """设置字体，支持中文"""
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            current_dir = os.path.dirname(os.path.abspath(__file__))
            font_paths = [
                # 优先使用仿宋 GB2312（公文字体，录取通知书正式感强）
                os.path.join(current_dir, '..', 'static', 'fonts', '仿宋_GB2312.ttf'),
                os.path.join(current_dir, '..', 'static', 'fonts', 'simfang.ttf'),
                os.path.join(current_dir, '..', 'static', 'fonts', '仿宋GB2312.ttf'),
                os.path.join(current_dir, '..', 'static', 'fonts', 'FangSong_GB2312.ttf'),
                # 仿宋找不到时用楷体（也是公文字体）
                os.path.join(current_dir, '..', 'static', 'fonts', '楷体_GB2312.ttf'),
                os.path.join(current_dir, '..', 'static', 'fonts', 'simkai.ttf'),
                os.path.join(current_dir, '..', 'static', 'fonts', 'KaiTi_GB2312.ttf'),
                # 兜底：字符集最全的微软雅黑（保证生僻字不丢字）
                os.path.join(current_dir, '..', 'static', 'fonts', 'msyh.ttc'),
                os.path.join(current_dir, '..', 'static', 'fonts', 'simhei.ttf'),
                os.path.join(current_dir, '..', 'static', 'fonts', 'simsun.ttc'),
                # 艺术字体最后兜底（字符集不全，生僻字会显示为方框）
                os.path.join(current_dir, '..', 'static', 'fonts', '青鸟华光简琥珀.ttf'),
            ]

            # 尝试注册第一个可用的字体
            registered = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(self.chinese_font_name, font_path))
                        logging.info(f"成功注册中文字体: {font_path}")
                        registered = True
                        break
                    except Exception as e:
                        logging.warning(f"注册字体失败 {font_path}: {str(e)}")
                        continue

            if not registered:
                logging.warning("未找到可用的中文字体，中文内容可能显示为方框")

        except Exception as e:
            logging.warning(f"字体注册失败: {str(e)}")

    def _contains_chinese(self, text):
        """检查文本是否包含中文字符"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    def add_texts_to_pdf(self, input_pdf_path, text_items, pagesize=A4, input_pdf_bytes=None):
        """
        在PDF文件的指定位置添加多个文本

        Args:
            input_pdf_path (str): 输入PDF文件路径（当 input_pdf_bytes 为 None 时使用）
            text_items (list): 文本项列表，每个项目包含：
                {
                    'text': '要添加的文字',
                    'page': 页码（从1开始），
                    'x': x坐标,
                    'y': y坐标,
                    'font_size': 字体大小（可选，默认12）,
                    'font_color': 字体颜色（可选，默认黑色）,
                    'font_name': 字体名称（可选，默认Helvetica）
                }
            pagesize: 页面大小，默认A4
            input_pdf_bytes (bytes): PDF二进制数据（可选，优先于 input_pdf_path）

        Returns:
            bytes: 生成的PDF文件二进制数据，失败返回None
        """
        try:
            # 获取PDF数据（优先使用传入的 bytes，否则从文件读取）
            if input_pdf_bytes is not None:
                pdf_data = input_pdf_bytes
            elif os.path.exists(input_pdf_path):
                with open(input_pdf_path, "rb") as f:
                    pdf_data = f.read()
            else:
                logging.error(f"输入PDF文件不存在: {input_pdf_path}")
                return None
            
            # 验证文本项
            if not text_items or not isinstance(text_items, list):
                logging.error("文本项列表为空或格式错误")
                return None
            
            # 读取原始PDF
            existing_pdf = PdfReader(io.BytesIO(pdf_data))
            total_pages = len(existing_pdf.pages)

            # 按页面分组文本项
            pages_texts = {}
            for item in text_items:
                if not self._validate_text_item(item, total_pages):
                    continue

                page_num = item['page']
                if page_num not in pages_texts:
                    pages_texts[page_num] = []
                pages_texts[page_num].append(item)

            # 创建输出PDF
            output = PdfWriter()

            # 处理每一页
            for page_num in range(1, total_pages + 1):
                original_page = existing_pdf.pages[page_num - 1]

                # 如果这一页有文本要添加
                if page_num in pages_texts:
                    # 创建文本覆盖层
                    text_overlay = self._create_text_overlay(
                        pages_texts[page_num],
                        pagesize
                    )

                    if text_overlay:
                        # 合并原页面和文本层
                        original_page.merge_page(text_overlay)

                # 添加页面到输出
                output.add_page(original_page)

            # 输出到内存
            output_buffer = io.BytesIO()
            output.write(output_buffer)
            output_buffer.seek(0)

            return output_buffer.getvalue()

        except Exception as e:
            logging.error(f"PDF文本添加失败: {str(e)}")
            return None
    
    def _validate_text_item(self, item, total_pages):
        """验证文本项格式"""
        try:
            # 检查必填字段
            required_fields = ['text', 'page', 'x', 'y']
            for field in required_fields:
                if field not in item:
                    logging.error(f"文本项缺少必填字段: {field}")
                    return False
            
            # 验证页码
            page = item['page']
            if not isinstance(page, int) or page < 1 or page > total_pages:
                logging.error(f"页码无效: {page}，总页数: {total_pages}")
                return False
            
            # 验证坐标
            x, y = item['x'], item['y']
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                logging.error(f"坐标格式错误: x={x}, y={y}")
                return False
            
            # 验证文本
            text = item['text']
            if not isinstance(text, str) or not text.strip():
                logging.error(f"文本内容无效: {text}")
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"文本项验证失败: {str(e)}")
            return False
    
    def _create_text_overlay(self, text_items, pagesize):
        """创建文本覆盖层"""
        try:
            # 创建内存缓冲区
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=pagesize)
            
            # 添加每个文本项
            for item in text_items:
                self._add_single_text(can, item)
            
            # 保存canvas
            can.save()
            
            # 读取生成的PDF
            packet.seek(0)
            overlay_pdf = PdfReader(packet)
            
            return overlay_pdf.pages[0]
            
        except Exception as e:
            logging.error(f"创建文本覆盖层失败: {str(e)}")
            return None
    
    def _add_single_text(self, canvas_obj, item):
        """在canvas上添加单个文本"""
        try:
            # 获取参数
            text = item['text']
            x = item['x']
            y = item['y']
            font_size = item.get('font_size', 12)
            font_color = item.get('font_color', (0, 0, 0))  # 默认黑色
            font_name = item.get('font_name', 'Helvetica')

            # 检查是否包含中文，如果包含则使用中文字体
            if self._contains_chinese(text):
                font_name = self.chinese_font_name

            # 设置字体
            try:
                canvas_obj.setFont(font_name, font_size)
            except Exception as e:
                if font_name == self.chinese_font_name:
                    # 中文字体未注册时不能回退到 Helvetica，否则仍显示方框
                    logging.error(f"中文字体 {font_name} 未注册，无法显示中文: {str(e)}")
                    return
                # 如果字体设置失败，使用默认字体
                canvas_obj.setFont('Helvetica', font_size)
                logging.warning(f"字体 {font_name} 设置失败，使用默认字体: {str(e)}")

            # 设置颜色
            if isinstance(font_color, (list, tuple)) and len(font_color) == 3:
                # RGB颜色 (0-1范围)
                canvas_obj.setFillColor(Color(*font_color))
            else:
                # 默认黑色
                canvas_obj.setFillColor(black)

            # 添加文本
            canvas_obj.drawString(x, y, text)

        except Exception as e:
            logging.error(f"添加文本失败: {str(e)}")
    
    def add_text_to_pdf_simple(self, input_pdf_path, text, page=1, x=100, y=100, 
                              font_size=12, font_color=(0, 0, 0), pagesize=A4):
        """
        简化版本：在PDF指定位置添加单个文本
        
        Args:
            input_pdf_path (str): 输入PDF文件路径
            text (str): 要添加的文字
            page (int): 页码（从1开始）
            x (float): x坐标
            y (float): y坐标
            font_size (int): 字体大小
            font_color (tuple): 字体颜色RGB (0-1范围)
            pagesize: 页面大小
            
        Returns:
            bytes: 生成的PDF文件二进制数据
        """
        text_items = [{
            'text': text,
            'page': page,
            'x': x,
            'y': y,
            'font_size': font_size,
            'font_color': font_color
        }]
        
        return self.add_texts_to_pdf(input_pdf_path, text_items, pagesize)
    
    @staticmethod
    def save_pdf_bytes(pdf_bytes, output_path):
        """
        保存PDF二进制数据到文件
        
        Args:
            pdf_bytes (bytes): PDF二进制数据
            output_path (str): 输出文件路径
            
        Returns:
            bool: 保存是否成功
        """
        try:
            if not pdf_bytes:
                logging.error("PDF数据为空")
                return False
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 保存文件
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
            
            logging.info(f"PDF文件已保存: {output_path}")
            return True
            
        except Exception as e:
            logging.error(f"保存PDF文件失败: {str(e)}")
            return False
    
    @staticmethod
    def get_pdf_info(pdf_path):
        """
        获取PDF文件信息

        Args:
            pdf_path (str): PDF文件路径

        Returns:
            dict: PDF信息 {'pages': 页数, 'size': 文件大小}
        """
        try:
            if not os.path.exists(pdf_path):
                return None

            with open(pdf_path, "rb") as f:
                pdf_reader = PdfReader(f)
                pages = len(pdf_reader.pages)
                size = os.path.getsize(pdf_path)

                return {
                    'pages': pages,
                    'size': size,
                    'size_mb': round(size / (1024 * 1024), 2)
                }

        except Exception as e:
            logging.error(f"获取PDF信息失败: {str(e)}")
            return None

    def add_watermark_to_pdf(self, input_pdf_path, watermark_text, pages=None,
                             font_size=14, font_color=(0.78, 0.78, 0.78),
                             angle=-20, input_pdf_bytes=None):
        """
        在PDF指定页面添加斜向重复水印文字

        Args:
            input_pdf_path (str): 输入PDF文件路径（当 input_pdf_bytes 为 None 时使用）
            watermark_text (str): 水印文字，如 "黔东南中等职业技术学校 · 张三 · 138****1234"
            pages (list): 要添加水印的页码列表（从1开始），None 表示所有页
            font_size (int): 水印字体大小
            font_color (tuple): RGB (0-1范围)，如 (0.78, 0.78, 0.78) 为浅灰色
            angle (float): 水印文字倾斜角度（度），默认 -20 度
            input_pdf_bytes (bytes): PDF二进制数据（可选，优先于 input_pdf_path）

        Returns:
            bytes: 添加水印后的PDF二进制数据，失败返回None
        """
        try:
            # 获取PDF数据（优先使用传入的 bytes，否则从文件读取）
            if input_pdf_bytes is not None:
                pdf_data = input_pdf_bytes
            elif os.path.exists(input_pdf_path):
                with open(input_pdf_path, "rb") as f:
                    pdf_data = f.read()
            else:
                logging.error(f"输入PDF文件不存在: {input_pdf_path}")
                return None

            if not watermark_text or not watermark_text.strip():
                logging.warning("水印文字为空，跳过添加水印")
                return None


            # 读取原始PDF
            existing_pdf = PdfReader(io.BytesIO(pdf_data))
            total_pages = len(existing_pdf.pages)

            # 确定要处理的页面
            if pages is None:
                target_pages = list(range(1, total_pages + 1))
            else:
                target_pages = [p for p in pages if 1 <= p <= total_pages]


            output = PdfWriter()

            # 处理每一页
            for page_num in range(1, total_pages + 1):
                original_page = existing_pdf.pages[page_num - 1]

                if page_num in target_pages:
                    # 获取原始页面尺寸
                    mediabox = original_page.mediabox
                    page_width = float(mediabox.width)
                    page_height = float(mediabox.height)

                    # 创建水印覆盖层
                    watermark_overlay = self._create_watermark_overlay(
                        watermark_text,
                        page_width,
                        page_height,
                        font_size,
                        font_color,
                        angle,
                    )
                    if watermark_overlay:
                        original_page.merge_page(watermark_overlay)

                output.add_page(original_page)

            # 输出到内存
            output_buffer = io.BytesIO()
            output.write(output_buffer)
            output_buffer.seek(0)
            result = output_buffer.getvalue()
            return result

        except Exception as e:
            logging.error(f"PDF添加水印失败: {str(e)}")
            return None

    def _create_watermark_overlay(self, text, page_width, page_height,
                                   font_size, font_color, angle):
        """创建水印覆盖层（斜向重复文字）"""
        try:
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            # 在 saveState 之前设好字体/颜色，setFont/setFillColorRGB 内部会 saveState/restoreState
            # 但我们外层也压一次栈保护整页状态，确保循环内变换不影响外部
            if self._contains_chinese(text):
                font_name = self.chinese_font_name
                try:
                    can.setFont(font_name, font_size)
                except Exception as e:
                    logging.warning(f"水印中文字体 {font_name} 未注册，使用替代字体: {e}")
                    font_name = 'Helvetica'
                    can.setFont(font_name, font_size)
            else:
                font_name = 'Helvetica'
                can.setFont(font_name, font_size)

            r, g, b = font_color
            from reportlab.lib.colors import Color
            fill_color = Color(r, g, b, alpha=0.4)
            can.setFillColor(fill_color)
            can.setStrokeColor(fill_color)

            # 计算文字宽度（用于居中定位）
            text_width = can.stringWidth(text, font_name, font_size)

            # 计算行列间距（水印密度控制）
            # col_width 至少要比文字宽度大，留出左右边距
            col_width = max(int(text_width * 1.6), 700)
            row_height = max(font_size * 12, 200)

            cols = int(page_width / col_width) + 3
            rows = int(page_height / row_height) + 3

            import math
            angle_rad = angle * math.pi / 180.0
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            half_w = text_width / 2
            half_h = font_size / 2

            # 用 saveState/restoreState 包裹每次水印绘制，变换不会跨迭代污染
            for i in range(-1, cols):
                for j in range(-1, rows):
                    x = i * col_width
                    y = j * row_height
                    # 奇偶行错开半格
                    x_off = (j % 2) * (col_width / 2)
                    # 水印文字中心在页面上的绝对坐标（绕自身中心旋转）
                    cx = x + x_off + half_w
                    cy = y + half_h
                    # rotated_BL = (cx, cy) + R(θ) · (-half_w, -half_h)
                    bl_x = cx + (-half_w) * cos_a - (-half_h) * sin_a
                    bl_y = cy + (-half_w) * sin_a + (-half_h) * cos_a
                    # translate 使得 drawString(0,0) → bl_x,bl_y，再 rotate 绕原点（bl点）旋转 angle
                    can.saveState()
                    can.translate(bl_x, bl_y)
                    can.rotate(angle)
                    can.drawString(0, 0, text)
                    can.restoreState()

            can.save()
            packet.seek(0)
            overlay_pdf = PdfReader(packet)
            return overlay_pdf.pages[0]

        except Exception as e:
            return None

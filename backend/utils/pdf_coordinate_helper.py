"""
PDF坐标计算辅助工具
用于帮助计算PDF中文本的准确位置
支持生成坐标网格模板文件
"""

import logging
import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm, inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue, gray, black
from PyPDF2 import PdfReader, PdfWriter


class PDFCoordinateHelper:
    """PDF坐标计算辅助类"""
    
    def __init__(self, pagesize=A4):
        """
        初始化坐标助手
        
        Args:
            pagesize: 页面大小，默认A4
        """
        self.pagesize = pagesize
        self.page_width = pagesize[0]
        self.page_height = pagesize[1]
        
        # A4纸张尺寸（点）
        # 1英寸 = 72点
        # A4 = 210mm × 297mm = 8.27" × 11.69" = 595.2 × 841.9 点
        
        logging.info(f"页面尺寸: {self.page_width:.1f} × {self.page_height:.1f} 点")
        logging.info(f"页面尺寸: {self.page_width/mm:.1f} × {self.page_height/mm:.1f} mm")
    
    def mm_to_points(self, mm_value):
        """毫米转换为点"""
        return mm_value * mm
    
    def cm_to_points(self, cm_value):
        """厘米转换为点"""
        return cm_value * cm
    
    def inch_to_points(self, inch_value):
        """英寸转换为点"""
        return inch_value * inch
    
    def points_to_mm(self, points):
        """点转换为毫米"""
        return points / mm
    
    def get_position_by_percentage(self, x_percent, y_percent):
        """
        根据百分比获取坐标
        
        Args:
            x_percent: X轴百分比 (0-100)
            y_percent: Y轴百分比 (0-100，0为底部，100为顶部)
            
        Returns:
            tuple: (x, y) 坐标
        """
        x = self.page_width * (x_percent / 100)
        y = self.page_height * (y_percent / 100)
        return (x, y)
    
    def get_position_by_mm(self, x_mm, y_mm, origin='bottom_left'):
        """
        根据毫米单位获取坐标
        
        Args:
            x_mm: X轴毫米数（从左边距）
            y_mm: Y轴毫米数
            origin: 坐标原点 ('bottom_left' 或 'top_left')
            
        Returns:
            tuple: (x, y) 坐标
        """
        x = self.mm_to_points(x_mm)
        
        if origin == 'top_left':
            # 从顶部开始计算
            y = self.page_height - self.mm_to_points(y_mm)
        else:
            # 从底部开始计算（PDF默认）
            y = self.mm_to_points(y_mm)
        
        return (x, y)
    
    def get_center_position(self, text_width_mm=0):
        """
        获取页面中心位置
        
        Args:
            text_width_mm: 文本宽度（毫米），用于居中对齐
            
        Returns:
            tuple: (x, y) 坐标
        """
        center_x = self.page_width / 2
        center_y = self.page_height / 2
        
        # 如果提供了文本宽度，调整X坐标以实现居中
        if text_width_mm > 0:
            text_width_points = self.mm_to_points(text_width_mm)
            center_x = center_x - (text_width_points / 2)
        
        return (center_x, center_y)
    
    def get_margin_position(self, left_margin_mm=20, top_margin_mm=20):
        """
        根据页边距获取位置
        
        Args:
            left_margin_mm: 左边距（毫米）
            top_margin_mm: 上边距（毫米）
            
        Returns:
            tuple: (x, y) 坐标
        """
        x = self.mm_to_points(left_margin_mm)
        y = self.page_height - self.mm_to_points(top_margin_mm)
        return (x, y)
    
    def calculate_text_positions(self, template_config):
        """
        根据模板配置计算文本位置
        
        Args:
            template_config: 模板配置字典，包含各个字段的位置信息
            
        Returns:
            dict: 计算后的坐标字典
        """
        positions = {}
        
        for field_name, config in template_config.items():
            if 'position_type' in config:
                pos_type = config['position_type']
                
                if pos_type == 'percentage':
                    x_percent = config.get('x_percent', 50)
                    y_percent = config.get('y_percent', 50)
                    positions[field_name] = self.get_position_by_percentage(x_percent, y_percent)
                
                elif pos_type == 'mm':
                    x_mm = config.get('x_mm', 20)
                    y_mm = config.get('y_mm', 20)
                    origin = config.get('origin', 'top_left')
                    positions[field_name] = self.get_position_by_mm(x_mm, y_mm, origin)
                
                elif pos_type == 'margin':
                    left_margin = config.get('left_margin_mm', 20)
                    top_margin = config.get('top_margin_mm', 20)
                    positions[field_name] = self.get_margin_position(left_margin, top_margin)
                
                elif pos_type == 'center':
                    text_width = config.get('text_width_mm', 0)
                    positions[field_name] = self.get_center_position(text_width)
                
                else:
                    # 直接使用点坐标
                    x = config.get('x', 100)
                    y = config.get('y', 100)
                    positions[field_name] = (x, y)
            
            else:
                # 兼容旧格式
                x = config.get('x', 100)
                y = config.get('y', 100)
                positions[field_name] = (x, y)
        
        return positions
    
    def print_coordinate_guide(self):
        """打印坐标参考指南"""
        print("\n=== PDF坐标参考指南 ===")
        print(f"页面尺寸: {self.page_width:.1f} × {self.page_height:.1f} 点")
        print(f"页面尺寸: {self.points_to_mm(self.page_width):.1f} × {self.points_to_mm(self.page_height):.1f} mm")
        print("\n常用位置坐标（点）:")
        
        # 四个角
        print(f"左下角: (0, 0)")
        print(f"右下角: ({self.page_width:.1f}, 0)")
        print(f"左上角: (0, {self.page_height:.1f})")
        print(f"右上角: ({self.page_width:.1f}, {self.page_height:.1f})")
        
        # 中心点
        center = self.get_center_position()
        print(f"页面中心: ({center[0]:.1f}, {center[1]:.1f})")
        
        # 常用边距位置
        margin_20mm = self.get_margin_position(20, 20)
        print(f"20mm边距位置: ({margin_20mm[0]:.1f}, {margin_20mm[1]:.1f})")
        
        print("\n坐标系说明:")
        print("- PDF坐标系原点在左下角")
        print("- X轴向右为正")
        print("- Y轴向上为正")
        print("- 1英寸 = 72点")
        print("- 1毫米 ≈ 2.83点")

    def generate_coordinate_template(self, template_pdf_path, output_path=None, grid_spacing_mm=10):
        """
        在模板PDF上生成坐标网格和参考点

        Args:
            template_pdf_path: 模板PDF文件路径
            output_path: 输出文件路径，默认为原文件名_coordinate_template.pdf
            grid_spacing_mm: 网格间距（毫米），默认10mm

        Returns:
            str: 生成的坐标模板文件路径
        """
        try:
            if not os.path.exists(template_pdf_path):
                raise FileNotFoundError(f"模板文件不存在: {template_pdf_path}")

            # 生成输出文件名
            if output_path is None:
                base_name = os.path.splitext(template_pdf_path)[0]
                output_path = f"{base_name}_coordinate_template.pdf"

            # 读取原始PDF
            with open(template_pdf_path, 'rb') as file:
                reader = PdfReader(file)
                writer = PdfWriter()

                # 处理每一页
                for page_num, page in enumerate(reader.pages, 1):
                    # 创建坐标网格覆盖层
                    overlay_buffer = self._create_coordinate_overlay(grid_spacing_mm)

                    # 读取覆盖层
                    overlay_reader = PdfReader(overlay_buffer)
                    overlay_page = overlay_reader.pages[0]

                    # 合并原页面和坐标网格
                    page.merge_page(overlay_page)
                    writer.add_page(page)

                # 保存结果
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)

            logging.info(f"坐标模板已生成: {output_path}")
            return output_path

        except Exception as e:
            logging.error(f"生成坐标模板失败: {str(e)}")
            return None

    def _create_coordinate_overlay(self, grid_spacing_mm=10):
        """创建坐标网格覆盖层"""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=self.pagesize)

        # 设置透明度
        c.setFillAlpha(0.3)
        c.setStrokeAlpha(0.5)

        # 绘制网格线
        self._draw_grid_lines(c, grid_spacing_mm)

        # 绘制坐标标注
        self._draw_coordinate_labels(c, grid_spacing_mm)

        # 绘制边框和角点标记
        self._draw_border_and_corners(c)

        # 绘制中心点
        self._draw_center_point(c)

        c.save()
        buffer.seek(0)
        return buffer

    def _draw_grid_lines(self, canvas_obj, grid_spacing_mm):
        """绘制网格线"""
        grid_spacing = self.mm_to_points(grid_spacing_mm)

        # 设置网格线样式
        canvas_obj.setStrokeColor(gray)
        canvas_obj.setLineWidth(0.5)

        # 垂直线
        x = 0
        while x <= self.page_width:
            canvas_obj.line(x, 0, x, self.page_height)
            x += grid_spacing

        # 水平线
        y = 0
        while y <= self.page_height:
            canvas_obj.line(0, y, self.page_width, y)
            y += grid_spacing

    def _draw_coordinate_labels(self, canvas_obj, grid_spacing_mm):
        """绘制坐标标注"""
        grid_spacing = self.mm_to_points(grid_spacing_mm)

        # 设置文字样式
        canvas_obj.setFillColor(blue)
        canvas_obj.setFont("Helvetica", 7)  # 稍微小一点的字体

        # 计算标注间隔，避免文字重叠
        label_interval = max(2, int(40 / grid_spacing))  # 至少间隔40点

        # X轴标注（底部）- 直接显示点坐标
        x = 0
        count = 0
        while x <= self.page_width:
            if x > 0 and count % label_interval == 0:  # 间隔显示标注
                # 直接显示点坐标，便于直接使用
                canvas_obj.drawString(x + 2, 8, f"{x:.0f}pt")
            x += grid_spacing
            count += 1

        # Y轴标注（左侧）- 直接显示点坐标
        y = 0
        count = 0
        while y <= self.page_height:
            if y > 0 and count % label_interval == 0:  # 间隔显示标注
                # 直接显示点坐标，便于直接使用
                canvas_obj.drawString(8, y + 2, f"{y:.0f}pt")
            y += grid_spacing
            count += 1

        # 在页面四角添加详细坐标信息
        self._draw_corner_coordinates(canvas_obj)

    def _draw_corner_coordinates(self, canvas_obj):
        """在页面四角绘制详细坐标信息"""
        canvas_obj.setFillColor(blue)
        canvas_obj.setFont("Helvetica-Bold", 9)

        # 左下角 (0,0)
        canvas_obj.drawString(15, 15, "原点 (0, 0)")
        canvas_obj.drawString(15, 5, "0pt, 0pt")

        # 右下角
        canvas_obj.drawString(self.page_width - 80, 15, f"({self.page_width:.0f}, 0)")
        canvas_obj.drawString(self.page_width - 80, 5, f"{self.page_width:.0f}pt, 0pt")

        # 左上角
        canvas_obj.drawString(15, self.page_height - 25, f"(0, {self.page_height:.0f})")
        canvas_obj.drawString(15, self.page_height - 15, f"0pt, {self.page_height:.0f}pt")

        # 右上角
        canvas_obj.drawString(self.page_width - 100, self.page_height - 25,
                            f"({self.page_width:.0f}, {self.page_height:.0f})")
        canvas_obj.drawString(self.page_width - 100, self.page_height - 15,
                            f"{self.page_width:.0f}pt, {self.page_height:.0f}pt")

    def _draw_border_and_corners(self, canvas_obj):
        """绘制边框和角点标记"""
        # 设置边框样式
        canvas_obj.setStrokeColor(red)
        canvas_obj.setLineWidth(2)

        # 绘制页面边框
        canvas_obj.rect(0, 0, self.page_width, self.page_height)

        # 绘制角点标记
        corner_size = 20
        canvas_obj.setFillColor(red)

        # 四个角点
        corners = [
            (0, 0, "左下角\n(0,0)"),
            (self.page_width, 0, f"右下角\n({self.page_width:.0f},0)"),
            (0, self.page_height, f"左上角\n(0,{self.page_height:.0f})"),
            (self.page_width, self.page_height, f"右上角\n({self.page_width:.0f},{self.page_height:.0f})")
        ]

        for x, y, label in corners:
            # 绘制角点圆圈
            canvas_obj.circle(x, y, 5, fill=1)

            # 标注文字
            canvas_obj.setFont("Helvetica-Bold", 10)
            if x == 0:  # 左侧
                text_x = x + 10
            else:  # 右侧
                text_x = x - 60

            if y == 0:  # 底部
                text_y = y + 10
            else:  # 顶部
                text_y = y - 30

            canvas_obj.drawString(text_x, text_y, label)

    def _draw_center_point(self, canvas_obj):
        """绘制中心点标记"""
        center_x, center_y = self.get_center_position()

        # 绘制中心点
        canvas_obj.setFillColor(red)
        canvas_obj.setStrokeColor(red)
        canvas_obj.circle(center_x, center_y, 8, fill=1)

        # 绘制十字线
        canvas_obj.setLineWidth(2)
        cross_size = 15
        canvas_obj.line(center_x - cross_size, center_y, center_x + cross_size, center_y)
        canvas_obj.line(center_x, center_y - cross_size, center_x, center_y + cross_size)

        # 标注文字
        canvas_obj.setFont("Helvetica-Bold", 12)
        canvas_obj.drawString(center_x + 20, center_y + 5, f"页面中心")
        canvas_obj.drawString(center_x + 20, center_y - 10, f"({center_x:.0f},{center_y:.0f})")

    def generate_coordinate_reference_file(self, template_pdf_path, output_dir=None):
        """
        生成完整的坐标参考文件包

        Args:
            template_pdf_path: 模板PDF文件路径
            output_dir: 输出目录，默认为模板文件所在目录

        Returns:
            dict: 生成的文件信息
        """
        try:
            if output_dir is None:
                output_dir = os.path.dirname(template_pdf_path)

            base_name = os.path.splitext(os.path.basename(template_pdf_path))[0]

            # 生成不同网格密度的坐标模板
            templates = {}

            # 粗网格 (20mm)
            coarse_template = os.path.join(output_dir, f"{base_name}_coordinate_coarse_20mm.pdf")
            templates['coarse'] = self.generate_coordinate_template(
                template_pdf_path, coarse_template, 20
            )

            # 中等网格 (10mm)
            medium_template = os.path.join(output_dir, f"{base_name}_coordinate_medium_10mm.pdf")
            templates['medium'] = self.generate_coordinate_template(
                template_pdf_path, medium_template, 10
            )

            # 细网格 (5mm)
            fine_template = os.path.join(output_dir, f"{base_name}_coordinate_fine_5mm.pdf")
            templates['fine'] = self.generate_coordinate_template(
                template_pdf_path, fine_template, 5
            )

            # 生成坐标配置文件
            config_file = os.path.join(output_dir, f"{base_name}_coordinate_config.py")
            self._generate_coordinate_config_file(template_pdf_path, config_file)
            templates['config'] = config_file

            logging.info(f"坐标参考文件包已生成到: {output_dir}")
            return templates

        except Exception as e:
            logging.error(f"生成坐标参考文件包失败: {str(e)}")
            return None

    def _generate_coordinate_config_file(self, template_pdf_path, config_file_path):
        """生成坐标配置文件"""
        try:
            template_name = os.path.splitext(os.path.basename(template_pdf_path))[0]

            config_content = f'''"""
{template_name} 坐标配置文件
自动生成于: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

使用方法:
from utils.pdf_coordinate_helper import PDFCoordinateHelper

helper = PDFCoordinateHelper()
positions = helper.calculate_text_positions(COORDINATE_CONFIG)
"""

# PDF页面信息
PAGE_WIDTH = {self.page_width:.1f}  # 点
PAGE_HEIGHT = {self.page_height:.1f}  # 点
PAGE_WIDTH_MM = {self.points_to_mm(self.page_width):.1f}  # 毫米
PAGE_HEIGHT_MM = {self.points_to_mm(self.page_height):.1f}  # 毫米

# 常用坐标位置（点）
COMMON_POSITIONS = {{
    'left_bottom': (0, 0),
    'right_bottom': ({self.page_width:.1f}, 0),
    'left_top': (0, {self.page_height:.1f}),
    'right_top': ({self.page_width:.1f}, {self.page_height:.1f}),
    'center': ({self.page_width/2:.1f}, {self.page_height/2:.1f}),
    'margin_20mm': ({self.mm_to_points(20):.1f}, {self.page_height - self.mm_to_points(20):.1f}),
}}

# 坐标配置模板
# 根据实际需要修改以下配置
COORDINATE_CONFIG = {{
    # 示例：学生姓名位置
    'student_name': {{
        'position_type': 'mm',
        'x_mm': 85,  # 距离左边85毫米
        'y_mm': 180,  # 距离顶部180毫米
        'origin': 'top_left',
        'font_size': 14,
        'description': '学生姓名填写位置'
    }},

    # 示例：学号位置
    'student_id': {{
        'position_type': 'mm',
        'x_mm': 85,
        'y_mm': 160,
        'origin': 'top_left',
        'font_size': 12,
        'description': '学号填写位置'
    }},

    # 示例：日期位置
    'date': {{
        'position_type': 'mm',
        'x_mm': 150,
        'y_mm': 50,
        'origin': 'top_left',
        'font_size': 12,
        'description': '日期填写位置'
    }},

    # 示例：使用百分比定位
    'title': {{
        'position_type': 'percentage',
        'x_percent': 50,  # 水平居中
        'y_percent': 80,  # 距离底部80%
        'font_size': 18,
        'description': '标题位置'
    }},

    # 示例：使用边距定位
    'content': {{
        'position_type': 'margin',
        'left_margin_mm': 25,
        'top_margin_mm': 30,
        'font_size': 12,
        'description': '正文内容位置'
    }}
}}

# 使用示例
if __name__ == "__main__":
    from utils.pdf_coordinate_helper import PDFCoordinateHelper

    helper = PDFCoordinateHelper()
    positions = helper.calculate_text_positions(COORDINATE_CONFIG)

    print("计算的坐标位置:")
    for field, pos in positions.items():
        config = COORDINATE_CONFIG[field]
        print(f"{{field}}: ({{pos[0]:.1f}}, {{pos[1]:.1f}}) - {{config.get('description', '')}}")
'''

            with open(config_file_path, 'w', encoding='utf-8') as f:
                f.write(config_content)

            logging.info(f"坐标配置文件已生成: {config_file_path}")

        except Exception as e:
            logging.error(f"生成坐标配置文件失败: {str(e)}")


def create_school_certificate_template():
    """创建学校证明模板的坐标配置"""
    return {
        'student_name': {
            'position_type': 'mm',
            'x_mm': 85,  # 姓名位置
            'y_mm': 180,
            'origin': 'top_left'
        },
        'student_id': {
            'position_type': 'mm',
            'x_mm': 85,  # 学号位置
            'y_mm': 160,
            'origin': 'top_left'
        },
        'start_date': {
            'position_type': 'mm',
            'x_mm': 120,  # 开始日期
            'y_mm': 140,
            'origin': 'top_left'
        },
        'end_date': {
            'position_type': 'mm',
            'x_mm': 180,  # 结束日期
            'y_mm': 140,
            'origin': 'top_left'
        }
    }


if __name__ == "__main__":
    # 测试坐标计算
    helper = PDFCoordinateHelper()
    helper.print_coordinate_guide()
    
    # 测试模板配置
    template = create_school_certificate_template()
    positions = helper.calculate_text_positions(template)
    
    print("\n=== 学校证明模板坐标（点坐标，可直接使用）===")
    for field, pos in positions.items():
        print(f"{field}: ({pos[0]:.1f}, {pos[1]:.1f})")

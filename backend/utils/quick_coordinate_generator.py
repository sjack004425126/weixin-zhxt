#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
快速坐标模板生成器
支持在现有PDF模板上叠加坐标网格，生成组合文档到static目录
"""

import os
import sys
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import blue, red, gray, black
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO


class CoordinateTemplateConfig:
    """坐标模板配置类"""

    # 预定义的模板路径列表（按优先级排序）
    TEMPLATE_PATHS = [
        "static/admission_notice.pdf",      # 录取通知书模板
        "static/录取通知书空白.pdf",          # 中文名录取通知书模板
        "static/school_certificate.pdf",    # 学校证明模板
        "static/certificate_template.pdf",  # 通用证书模板
        "static/form_template.pdf"          # 表单模板
    ]

    # 网格配置
    GRID_CONFIGS = [
        (20, "coarse", "粗网格"),
        (10, "medium", "中等网格"),
        (5, "fine", "细网格")
    ]

    @classmethod
    def find_available_template(cls):
        """查找可用的模板文件"""
        for template_path in cls.TEMPLATE_PATHS:
            if os.path.exists(template_path):
                return template_path
        return None

    @classmethod
    def get_template_list(cls):
        """获取支持的模板文件列表"""
        return [os.path.basename(path) for path in cls.TEMPLATE_PATHS]

def generate_coordinate_template_with_pdf():
    """
    生成坐标模板，在预定义的PDF模板上叠加坐标网格
    """
    print("🎯 快速坐标模板生成器")
    print("=" * 50)

    # 查找可用的模板文件
    template_pdf_path = CoordinateTemplateConfig.find_available_template()

    if template_pdf_path:
        print(f"📄 找到模板PDF: {template_pdf_path}")
    else:
        print("📄 未找到预定义模板，生成空白坐标模板")
        print(f"💡 支持的模板文件: {', '.join(CoordinateTemplateConfig.get_template_list())}")
    
    try:
        # 获取static目录路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        static_dir = os.path.join(project_root, "static")
        
        # 确保static目录存在
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
            print(f"✅ 创建目录: {static_dir}")
        
        print(f"📁 输出目录: {static_dir}")
        
        # 使用配置类中的网格设置
        templates = CoordinateTemplateConfig.GRID_CONFIGS
        
        generated_files = []
        
        for grid_mm, suffix, description in templates:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if template_pdf_path:
                # 如果有模板PDF，生成带模板名称的文件名
                template_name = os.path.splitext(os.path.basename(template_pdf_path))[0]
                filename = f"{template_name}_coordinate_{suffix}_{grid_mm}mm_{timestamp}.pdf"
            else:
                filename = f"coordinate_template_{suffix}_{grid_mm}mm_{timestamp}.pdf"

            filepath = os.path.join(static_dir, filename)

            print(f"\n--- 生成 {description} ({grid_mm}mm) ---")

            if template_pdf_path:
                # 在现有PDF上叠加坐标网格
                success = _overlay_coordinates_on_pdf(template_pdf_path, filepath, grid_mm, description)
                if success:
                    file_size = os.path.getsize(filepath)
                    generated_files.append({
                        'filename': filename,
                        'description': description,
                        'size': file_size,
                        'grid_mm': grid_mm
                    })
                    print(f"✅ {description}生成成功")
                    print(f"   文件: {filename}")
                    print(f"   大小: {file_size/1024:.1f}KB")
                else:
                    print(f"❌ {description}生成失败")
            else:
                # 生成空白坐标模板
                success = _create_blank_coordinate_template(filepath, grid_mm, description)
                if success:
                    file_size = os.path.getsize(filepath)
                    generated_files.append({
                        'filename': filename,
                        'description': description,
                        'size': file_size,
                        'grid_mm': grid_mm
                    })
                    print(f"✅ {description}生成成功")
                    print(f"   文件: {filename}")
                    print(f"   大小: {file_size/1024:.1f}KB")
                else:
                    print(f"❌ {description}生成失败")

        
        print("\n" + "=" * 50)
        print(f"🎉 生成完成！共生成 {len(generated_files)} 个模板文件")
        print(f"📁 文件保存在: {static_dir}")
        print()
        
        print("📋 生成的文件:")
        for i, file_info in enumerate(generated_files, 1):
            print(f"  {i}. {file_info['description']} - {file_info['filename']}")
            print(f"     大小: {file_info['size']/1024:.1f}KB, 网格: {file_info['grid_mm']}mm")
        
        print("\n📖 使用说明:")
        print("1. 在PDF查看器中打开生成的模板文件")
        print("2. 先用粗网格(20mm)进行大致定位")
        print("3. 再用中等网格(10mm)进行精确定位")
        print("4. 最后用细网格(5mm)进行微调")
        print("5. 读取坐标标注，直接在代码中使用")
        
        return True

    except Exception as e:
        print(f"❌ 生成失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def _overlay_coordinates_on_pdf(template_pdf_path, output_path, grid_mm, description):
    """在现有PDF上叠加坐标网格"""
    try:
        # 读取模板PDF
        reader = PdfReader(template_pdf_path)
        writer = PdfWriter()

        # 获取第一页的尺寸
        first_page = reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)

        print(f"   模板页面尺寸: {page_width:.1f} × {page_height:.1f} 点")

        # 为每一页添加坐标网格
        for page_num, page in enumerate(reader.pages):
            # 创建坐标网格覆盖层
            overlay_buffer = BytesIO()
            overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))

            # 绘制坐标网格
            _draw_coordinate_grid(overlay_canvas, grid_mm, page_width, page_height, description, page_num + 1)
            overlay_canvas.save()

            # 读取覆盖层
            overlay_buffer.seek(0)
            overlay_reader = PdfReader(overlay_buffer)
            overlay_page = overlay_reader.pages[0]

            # 合并页面
            page.merge_page(overlay_page)
            writer.add_page(page)

        # 保存合并后的PDF
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

        return True

    except Exception as e:
        print(f"   ❌ PDF合并失败: {str(e)}")
        return False


def _create_blank_coordinate_template(output_path, grid_mm, description):
    """创建空白坐标模板"""
    try:
        page_width, page_height = A4
        c = canvas.Canvas(output_path, pagesize=A4)

        # 绘制坐标网格
        _draw_coordinate_grid(c, grid_mm, page_width, page_height, description, 1)
        c.save()

        return True

    except Exception as e:
        print(f"   ❌ 空白模板创建失败: {str(e)}")
        return False


def _draw_coordinate_grid(c, grid_mm, page_width, page_height, description, page_num):
    """绘制坐标网格"""
    grid_spacing = grid_mm * 2.834645669  # mm转点

    # 绘制网格线
    c.setStrokeColor(gray)
    c.setLineWidth(0.5)

    # 垂直线
    x = 0
    while x <= page_width:
        c.line(x, 0, x, page_height)
        x += grid_spacing

    # 水平线
    y = 0
    while y <= page_height:
        c.line(0, y, page_width, y)
        y += grid_spacing

    # 坐标标注
    c.setFillColor(blue)
    c.setFont("Helvetica", 7 if grid_mm <= 5 else 8)

    # 计算标注间隔
    label_interval = max(1, int(40 / grid_spacing))

    # X轴标注
    x = 0
    count = 0
    while x <= page_width:
        if x > 0 and count % label_interval == 0:
            c.drawString(x + 2, 5, f"{x:.0f}pt")
        x += grid_spacing
        count += 1

    # Y轴标注
    y = 0
    count = 0
    while y <= page_height:
        if y > 0 and count % label_interval == 0:
            c.drawString(5, y + 2, f"{y:.0f}pt")
        y += grid_spacing
        count += 1

    # 标题和信息（只在第一页显示）
    if page_num == 1:
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, page_height - 30, f"PDF坐标模板 - {description} ({grid_mm}mm)")

        c.setFont("Helvetica", 10)
        info_y = page_height - 50
        info_lines = [
            f"页面尺寸: {page_width:.1f} × {page_height:.1f} 点",
            f"网格间距: {grid_mm}mm ({grid_spacing:.1f}pt)",
            "坐标系: 原点在左下角，X轴向右，Y轴向上",
            "标注: 直接显示点坐标，可直接使用",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]

        for line in info_lines:
            c.drawString(50, info_y, line)
            info_y -= 15

    # 四角坐标
    c.setFillColor(red)
    c.setFont("Helvetica-Bold", 9)

    corners = [
        (15, 15, "(0, 0)"),
        (page_width - 80, 15, f"({page_width:.0f}, 0)"),
        (15, page_height - 25, f"(0, {page_height:.0f})"),
        (page_width - 120, page_height - 25, f"({page_width:.0f}, {page_height:.0f})")
    ]

    for x, y, text in corners:
        c.drawString(x, y, text)

    # 中心点
    center_x = page_width / 2
    center_y = page_height / 2
    c.drawString(center_x - 40, center_y, f"中心: ({center_x:.0f}, {center_y:.0f})")

    # 中心十字标记
    c.setStrokeColor(red)
    c.setLineWidth(1)
    c.line(center_x - 10, center_y, center_x + 10, center_y)
    c.line(center_x, center_y - 10, center_x, center_y + 10)


# 兼容性函数
def generate_coordinate_template():
    """生成坐标模板（兼容性函数）"""
    return generate_coordinate_template_with_pdf()


if __name__ == "__main__":
    # 直接运行，使用预定义的模板路径
    generate_coordinate_template_with_pdf()

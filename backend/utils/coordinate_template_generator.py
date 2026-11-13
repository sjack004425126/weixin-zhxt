#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
坐标模板生成器
生成带有点坐标网格的PDF模板，用于精确定位文本位置
生成的PDF文件保存在static目录
"""

import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import blue, red, gray, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime


class CoordinateTemplateGenerator:
    """坐标模板生成器"""
    
    def __init__(self):
        self.page_width, self.page_height = A4
        # 获取项目根目录的static路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        self.output_dir = os.path.join(project_root, "static")

        # 确保输出目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def generate_coordinate_template(self, template_name="coordinate_template", grid_spacing_mm=10):
        """
        生成坐标模板
        
        Args:
            template_name: 模板名称
            grid_spacing_mm: 网格间距（毫米）
        
        Returns:
            dict: 生成结果
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{template_name}_{grid_spacing_mm}mm_{timestamp}.pdf"
            filepath = os.path.join(self.output_dir, filename)
            
            # 创建PDF
            c = canvas.Canvas(filepath, pagesize=A4)
            
            # 绘制网格和坐标
            self._draw_coordinate_grid(c, grid_spacing_mm)
            self._draw_coordinate_labels(c, grid_spacing_mm)
            self._draw_page_info(c, grid_spacing_mm)
            self._draw_reference_points(c)
            
            c.save()
            
            file_size = os.path.getsize(filepath)
            
            return {
                'success': True,
                'message': '坐标模板生成成功',
                'filename': filename,
                'filepath': filepath,
                'file_size': file_size,
                'grid_spacing': f"{grid_spacing_mm}mm"
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'生成失败: {str(e)}'
            }
    
    def generate_multiple_templates(self, template_name="coordinate_template"):
        """
        生成多种网格密度的坐标模板
        
        Args:
            template_name: 模板名称前缀
            
        Returns:
            dict: 生成结果
        """
        grid_sizes = [
            (20, "coarse", "粗网格"),
            (10, "medium", "中等网格"), 
            (5, "fine", "细网格")
        ]
        
        results = []
        
        for grid_mm, suffix, description in grid_sizes:
            name = f"{template_name}_{suffix}"
            result = self.generate_coordinate_template(name, grid_mm)
            result['description'] = description
            results.append(result)
        
        success_count = sum(1 for r in results if r['success'])
        
        return {
            'success': success_count > 0,
            'message': f'生成完成: {success_count}/{len(results)} 成功',
            'results': results,
            'total': len(results),
            'success_count': success_count
        }
    
    def mm_to_points(self, mm):
        """毫米转点"""
        return mm * 2.834645669
    
    def _draw_coordinate_grid(self, c, grid_spacing_mm):
        """绘制坐标网格"""
        grid_spacing = self.mm_to_points(grid_spacing_mm)
        
        # 设置网格线样式
        c.setStrokeColor(gray)
        c.setLineWidth(0.5)
        
        # 绘制垂直线
        x = 0
        while x <= self.page_width:
            c.line(x, 0, x, self.page_height)
            x += grid_spacing
        
        # 绘制水平线
        y = 0
        while y <= self.page_height:
            c.line(0, y, self.page_width, y)
            y += grid_spacing
    
    def _draw_coordinate_labels(self, c, grid_spacing_mm):
        """绘制坐标标注（直接显示点坐标）"""
        grid_spacing = self.mm_to_points(grid_spacing_mm)
        
        # 设置文字样式
        c.setFillColor(blue)
        c.setFont("Helvetica", 8)
        
        # 计算标注间隔，避免文字重叠
        label_interval = max(1, int(30 / grid_spacing))
        
        # X轴标注（底部）- 直接显示点坐标
        x = 0
        count = 0
        while x <= self.page_width:
            if x > 0 and count % label_interval == 0:
                c.drawString(x + 2, 5, f"{x:.0f}pt")
            x += grid_spacing
            count += 1
        
        # Y轴标注（左侧）- 直接显示点坐标
        y = 0
        count = 0
        while y <= self.page_height:
            if y > 0 and count % label_interval == 0:
                c.drawString(5, y + 2, f"{y:.0f}pt")
            y += grid_spacing
            count += 1
    
    def _draw_page_info(self, c, grid_spacing_mm):
        """绘制页面信息"""
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 12)
        
        # 标题
        title = f"PDF坐标模板 - 网格间距: {grid_spacing_mm}mm"
        c.drawString(50, self.page_height - 30, title)
        
        # 页面信息
        c.setFont("Helvetica", 10)
        info_y = self.page_height - 50
        
        info_lines = [
            f"页面尺寸: {self.page_width:.1f} × {self.page_height:.1f} 点",
            f"页面尺寸: {self.page_width/2.834645669:.1f} × {self.page_height/2.834645669:.1f} mm",
            "坐标系: 原点在左下角，X轴向右，Y轴向上",
            "网格标注: 直接显示点坐标，可直接使用",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]
        
        for line in info_lines:
            c.drawString(50, info_y, line)
            info_y -= 15
    
    def _draw_reference_points(self, c):
        """绘制参考点"""
        c.setFillColor(red)
        c.setFont("Helvetica-Bold", 9)
        
        # 四个角的坐标（直接显示点坐标）
        corners = [
            (15, 15, f"(0, 0)"),
            (self.page_width - 80, 15, f"({self.page_width:.0f}, 0)"),
            (15, self.page_height - 25, f"(0, {self.page_height:.0f})"),
            (self.page_width - 120, self.page_height - 25, f"({self.page_width:.0f}, {self.page_height:.0f})")
        ]
        
        for x, y, text in corners:
            c.drawString(x, y, text)
        
        # 页面中心点
        center_x = self.page_width / 2
        center_y = self.page_height / 2
        c.drawString(center_x - 40, center_y, f"中心: ({center_x:.0f}, {center_y:.0f})")
        
        # 绘制中心十字标记
        c.setStrokeColor(red)
        c.setLineWidth(1)
        c.line(center_x - 10, center_y, center_x + 10, center_y)
        c.line(center_x, center_y - 10, center_x, center_y + 10)


def main():
    """主函数 - 生成坐标模板"""
    print("🎯 PDF坐标模板生成器")
    print("=" * 50)
    
    generator = CoordinateTemplateGenerator()
    
    # 生成多种网格密度的模板
    print("正在生成多种网格密度的坐标模板...")
    result = generator.generate_multiple_templates("pdf_coordinate_template")
    
    if result['success']:
        print(f"✅ 生成成功: {result['success_count']}/{result['total']} 个模板")
        print(f"📁 文件保存在: {generator.output_dir}/ 目录")
        print()
        
        for i, template_result in enumerate(result['results'], 1):
            if template_result['success']:
                print(f"{i}. {template_result['description']}")
                print(f"   文件: {template_result['filename']}")
                print(f"   大小: {template_result['file_size']/1024:.1f}KB")
                print(f"   网格: {template_result['grid_spacing']}")
            else:
                print(f"{i}. ❌ {template_result['description']} - {template_result['message']}")
            print()
    else:
        print(f"❌ 生成失败: {result['message']}")
    
    print("=" * 50)
    print("📖 使用说明:")
    print("1. 在PDF查看器中打开生成的模板文件")
    print("2. 找到需要填写文本的位置")
    print("3. 读取该位置的坐标值（网格标注）")
    print("4. 在代码中直接使用这些点坐标")
    print("5. 推荐先用粗网格定位，再用细网格精调")
    print()
    print("🎉 坐标模板生成完成！")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
录取通知书生成工具类
基于PDF模板在固定位置填写学生信息
"""

import os
import base64
import logging
from datetime import datetime
from .pdf_text_generator import PdfTextGenerator

class AdmissionNotice:
    """录取通知书生成工具类"""
    
    def __init__(self):
        """初始化"""
        self.template_path = "static/admission_notice.pdf"
        self.pdf_generator = PdfTextGenerator()
        
        # 录取通知书填写位置配置（第2页）
        self.text_positions = {
            'student_name': {'page': 2, 'x': 90, 'y': 660, 'font_size': 14},
            'major': {'page': 2, 'x': 200, 'y': 597, 'font_size': 12},
            'start_month': {'page': 2, 'x': 390, 'y': 573, 'font_size': 12},
            'start_day': {'page': 2, 'x': 435, 'y': 573, 'font_size': 12},
            'end_month': {'page': 2, 'x': 495, 'y': 573, 'font_size': 12},
            'end_day': {'page': 2, 'x': 87, 'y': 550, 'font_size': 12},
            'issue_year': {'page': 2, 'x': 355, 'y': 480, 'font_size': 12},
            'issue_month': {'page': 2, 'x': 410, 'y': 480, 'font_size': 12},
            'issue_day': {'page': 2, 'x': 450, 'y': 480, 'font_size': 12}
        }
    
    def create_filled_notice(self, student_name, major, start_date, end_date, issue_date,
                             watermark_text=None):
        """
        创建填写好的录取通知书

        Args:
            student_name (str): 学生姓名
            major (str): 录取专业
            start_date (str): 开学日期 (格式: YYYY-MM-DD)
            issue_date (str): 落款日期 (格式: YYYY-MM-DD)
            watermark_text (str): 水印文字，不传则不加水印

        Returns:
            dict: 包含生成结果的字典
            {
                'success': bool,
                'message': str,
                'data': str (Base64编码的PDF数据),
                'filename': str
            }
        """
        try:
            # 验证参数
            is_valid, error_msg = self.validate_student_info(
                student_name, major, start_date, end_date, issue_date
            )
            if not is_valid:
                return {
                    'success': False,
                    'message': error_msg,
                    'data': None,
                    'filename': None
                }
            
            # 验证模板文件
            if not os.path.exists(self.template_path):
                return {
                    'success': False,
                    'message': f'模板文件不存在: {self.template_path}',
                    'data': None,
                    'filename': None
                }
            
            # 准备文本项
            text_items = self._prepare_text_items(
                student_name, major, start_date, end_date, issue_date
            )
            
            # 使用PDF文本生成器生成PDF
            pdf_bytes = self.pdf_generator.add_texts_to_pdf(
                self.template_path, text_items
            )

            if not pdf_bytes:
                return {
                    'success': False,
                    'message': 'PDF生成失败',
                    'data': None,
                    'filename': None
                }

            # 添加水印（如有）
            if watermark_text:
                pdf_bytes = self.pdf_generator.add_watermark_to_pdf(
                    self.template_path, watermark_text, input_pdf_bytes=pdf_bytes
                ) or pdf_bytes  # 水印失败不阻断主流程

            # 转换为Base64
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"录取通知书_{student_name}_{timestamp}.pdf"
            
            return {
                'success': True,
                'message': '录取通知书生成成功',
                'data': pdf_base64,
                'filename': filename
            }
            
        except Exception as e:
            logging.error(f"生成录取通知书异常: {str(e)}")
            return {
                'success': False,
                'message': f'生成失败: {str(e)}',
                'data': None,
                'filename': None
            }
    
    def _prepare_text_items(self, student_name, major, start_date, end_date, issue_date):
        """
        准备要填写的文本项
        
        Args:
            student_name (str): 学生姓名
            major (str): 录取专业
            start_date (str): 开学日期
            end_date (str): 结束日期
            issue_date (str): 落款日期
            
        Returns:
            list: 文本项列表
        """
        # 解析日期
        start_parts = start_date.split('-')
        end_parts = end_date.split('-')
        issue_parts = issue_date.split('-')
        
        text_items = []
        
        # 学生姓名
        text_items.append({
            'text': student_name,
            'page': self.text_positions['student_name']['page'],
            'x': self.text_positions['student_name']['x'],
            'y': self.text_positions['student_name']['y'],
            'font_size': self.text_positions['student_name']['font_size']
        })
        
        # 录取专业
        text_items.append({
            'text': major,
            'page': self.text_positions['major']['page'],
            'x': self.text_positions['major']['x'],
            'y': self.text_positions['major']['y'],
            'font_size': self.text_positions['major']['font_size']
        })
        
        # 开学日期
        text_items.extend([
            {
                'text': start_parts[1],  # 月
                'page': self.text_positions['start_month']['page'],
                'x': self.text_positions['start_month']['x'],
                'y': self.text_positions['start_month']['y'],
                'font_size': self.text_positions['start_month']['font_size']
            },
            {
                'text': start_parts[2],  # 日
                'page': self.text_positions['start_day']['page'],
                'x': self.text_positions['start_day']['x'],
                'y': self.text_positions['start_day']['y'],
                'font_size': self.text_positions['start_day']['font_size']
            }
        ])
        
        # 结束日期
        text_items.extend([
            {
                'text': end_parts[1],  # 月
                'page': self.text_positions['end_month']['page'],
                'x': self.text_positions['end_month']['x'],
                'y': self.text_positions['end_month']['y'],
                'font_size': self.text_positions['end_month']['font_size']
            },
            {
                'text': end_parts[2],  # 日
                'page': self.text_positions['end_day']['page'],
                'x': self.text_positions['end_day']['x'],
                'y': self.text_positions['end_day']['y'],
                'font_size': self.text_positions['end_day']['font_size']
            }
        ])




        # 落款日期
        text_items.extend([
            {
                'text': issue_parts[0],  # 年
                'page': self.text_positions['issue_year']['page'],
                'x': self.text_positions['issue_year']['x'],
                'y': self.text_positions['issue_year']['y'],
                'font_size': self.text_positions['issue_year']['font_size']
            },
            {
                'text': issue_parts[1],  # 月
                'page': self.text_positions['issue_month']['page'],
                'x': self.text_positions['issue_month']['x'],
                'y': self.text_positions['issue_month']['y'],
                'font_size': self.text_positions['issue_month']['font_size']
            },
            {
                'text': issue_parts[2],  # 日
                'page': self.text_positions['issue_day']['page'],
                'x': self.text_positions['issue_day']['x'],
                'y': self.text_positions['issue_day']['y'],
                'font_size': self.text_positions['issue_day']['font_size']
            }
        ])
        
        return text_items
    
    def validate_student_info(self, student_name, major, start_date, end_date, issue_date):
        """
        验证学生信息
        
        Args:
            student_name (str): 学生姓名
            major (str): 录取专业
            start_date (str): 开学日期
            end_date (str): 结束日期
            issue_date (str): 落款日期
            
        Returns:
            tuple: (是否有效, 错误信息)
        """
        try:
            # 检查必填字段
            if not student_name or not student_name.strip():
                return False, "学生姓名不能为空"
            
            if not major or not major.strip():
                return False, "录取专业不能为空"
            
            if not start_date or not start_date.strip():
                return False, "开学日期不能为空"
            
            if not end_date or not end_date.strip():
                return False, "结束日期不能为空"
            
            if not issue_date or not issue_date.strip():
                return False, "落款日期不能为空"
            
            # 验证姓名长度
            if len(student_name.strip()) > 10:
                return False, "学生姓名不能超过10个字符"
            
            # 验证专业长度
            if len(major.strip()) > 20:
                return False, "录取专业不能超过20个字符"
            
            # 验证日期格式
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                issue_dt = datetime.strptime(issue_date, '%Y-%m-%d')
            except ValueError:
                return False, "日期格式错误，请使用YYYY-MM-DD格式"
            
                # # 验证日期逻辑
                # if issue_dt > start_dt:
                #     return False, "落款日期不能晚于开学日期"
                
                # if end_dt < start_dt:
                #     return False, "结束日期不能早于开学日期"
            
            # 验证年份范围（当前年份到未来2年）
            current_year = datetime.now().year
            if start_dt.year < current_year or start_dt.year > current_year + 2:
                return False, f"开学日期年份应在{current_year}-{current_year + 2}范围内"
            
            return True, "验证通过"
            
        except Exception as e:
            logging.error(f"参数验证异常: {str(e)}")
            return False, f"参数验证失败: {str(e)}"
    
    def get_pdf_bytes(self, student_name, major, start_date, end_date, issue_date,
                      watermark_text=None):
        """
        直接返回PDF二进制数据（不进行Base64编码）

        Args:
            student_name (str): 学生姓名
            major (str): 录取专业
            start_date (str): 开学日期
            issue_date (str): 落款日期
            watermark_text (str): 水印文字，不传则不加水印

        Returns:
            bytes: PDF二进制数据，失败返回None
        """
        try:
            # 验证参数
            is_valid, error_msg = self.validate_student_info(
                student_name, major, start_date, end_date, issue_date
            )
            if not is_valid:
                logging.error(f"参数验证失败: {error_msg}")
                return None

            # 验证模板文件
            if not os.path.exists(self.template_path):
                logging.error(f"模板文件不存在: {self.template_path}")
                return None

            # 准备文本项
            text_items = self._prepare_text_items(
                student_name, major, start_date, end_date, issue_date
            )

            # 使用PDF文本生成器生成PDF
            pdf_bytes = self.pdf_generator.add_texts_to_pdf(
                self.template_path, text_items
            )

            if not pdf_bytes:
                return None

            # 添加水印（如有）
            if watermark_text:
                pdf_bytes = self.pdf_generator.add_watermark_to_pdf(
                    self.template_path, watermark_text, input_pdf_bytes=pdf_bytes
                ) or pdf_bytes

            return pdf_bytes

        except Exception as e:
            logging.error(f"生成PDF二进制数据异常: {str(e)}")
            return None

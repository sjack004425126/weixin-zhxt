#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信小程序二维码生成工具类
"""

import requests
import base64
import logging
import urllib.parse

class WxQrCode:
    """微信小程序二维码生成工具类"""
    
    # 微信小程序配置
    WX_CONFIG = {
        'appid': 'wxe8f312724bfb12f0',
        'secret': '0175cc4b75d631412dcc94bcf88e9f70'
    }
    
    # 微信API地址
    WX_API = {
        'token_url': 'https://api.weixin.qq.com/cgi-bin/token',
        'wxacode_url': 'https://api.weixin.qq.com/wxa/getwxacode',
        'wxacode_unlimited_url': 'https://api.weixin.qq.com/wxa/getwxacodeunlimit',
        'qrcode_url': 'https://api.weixin.qq.com/cgi-bin/wxaapp/createwxaqrcode'
    }
    
    @staticmethod
    def get_access_token():
        """
        获取微信小程序access_token
        
        Returns:
            str: access_token，失败返回 None
        """
        try:
            data = {
                'grant_type': 'client_credential',
                'appid': WxQrCode.WX_CONFIG['appid'],
                'secret': WxQrCode.WX_CONFIG['secret']
            }
            
            response = requests.get(WxQrCode.WX_API['token_url'], params=data)
            result = response.json()
            
            if 'access_token' in result:
                return result['access_token']
            else:
                logging.error(f"获取access_token失败: {result}")
                return None
                
        except Exception as e:
            logging.error(f"获取access_token异常: {str(e)}")
            return None
    
    @staticmethod
    def generate_wxacode(path, width=430):
        """
        生成小程序码（适用于需要的码数量较少的业务场景）
        
        Args:
            path (str): 扫码进入的小程序页面路径，必须是已经发布的小程序存在的页面
            width (int): 二维码的宽度，单位为px，最小280px，最大1280px，默认430px
            
        Returns:
            dict: 包含二维码数据的字典
            {
                'success': True/False,
                'data': base64编码的图片数据 或 None,
                'message': 错误信息
            }
        """
        try:
            # 获取access_token
            access_token = WxQrCode.get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'data': None,
                    'message': '获取access_token失败'
                }
            
            # 构建请求URL
            url = f"{WxQrCode.WX_API['wxacode_url']}?access_token={access_token}"
            
            # 请求参数
            data = {
                'path': path,
                'width': width
            }
            
            # 发送POST请求
            response = requests.post(url, json=data)
            
            # 检查响应内容类型
            content_type = response.headers.get('content-type', '')
            
            if 'image' in content_type:
                # 成功返回图片数据
                image_data = response.content
                base64_data = base64.b64encode(image_data).decode('utf-8')
                return {
                    'success': True,
                    'data': base64_data,
                    'message': '生成成功'
                }
            else:
                # 返回错误信息
                try:
                    error_info = response.json()
                    return {
                        'success': False,
                        'data': None,
                        'message': f"生成失败: {error_info.get('errmsg', '未知错误')}"
                    }
                except:
                    return {
                        'success': False,
                        'data': None,
                        'message': f"生成失败: HTTP {response.status_code}"
                    }
                    
        except Exception as e:
            logging.error(f"生成小程序码异常: {str(e)}")
            return {
                'success': False,
                'data': None,
                'message': f'生成异常: {str(e)}'
            }
    
    @staticmethod
    def generate_wxacode_unlimited(scene, page=None, width=430):
        """
        生成小程序码（适用于需要的码数量极多的业务场景）
        
        Args:
            scene (str): 最大32个可见字符，作为参数会传递到小程序页面
            page (str): 小程序要打开的页面路径，可选
            width (int): 二维码宽度，默认430px
            
        Returns:
            dict: 包含二维码数据的字典
        """
        try:
            # 获取access_token
            access_token = WxQrCode.get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'data': None,
                    'message': '获取access_token失败'
                }
            
            # 构建请求URL
            url = f"{WxQrCode.WX_API['wxacode_unlimited_url']}?access_token={access_token}"
            
            # 请求参数
            data = {
                'scene': scene,
                'width': width
            }
            
            if page:
                data['page'] = page
            
            # 发送POST请求
            response = requests.post(url, json=data)
            
            # 检查响应内容类型
            content_type = response.headers.get('content-type', '')
            
            if 'image' in content_type:
                # 成功返回图片数据
                image_data = response.content
                base64_data = base64.b64encode(image_data).decode('utf-8')
                return {
                    'success': True,
                    'data': base64_data,
                    'message': '生成成功'
                }
            else:
                # 返回错误信息
                try:
                    error_info = response.json()
                    return {
                        'success': False,
                        'data': None,
                        'message': f"生成失败: {error_info.get('errmsg', '未知错误')}"
                    }
                except:
                    return {
                        'success': False,
                        'data': None,
                        'message': f"生成失败: HTTP {response.status_code}"
                    }
                    
        except Exception as e:
            logging.error(f"生成小程序码异常: {str(e)}")
            return {
                'success': False,
                'data': None,
                'message': f'生成异常: {str(e)}'
            }
    
    @staticmethod
    def generate_qrcode(path, width=430):
        """
        生成传统二维码（圆形）
        
        Args:
            path (str): 扫码进入的小程序页面路径
            width (int): 二维码宽度，默认430px
            
        Returns:
            dict: 包含二维码数据的字典
        """
        try:
            # 获取access_token
            access_token = WxQrCode.get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'data': None,
                    'message': '获取access_token失败'
                }
            
            # 构建请求URL
            url = f"{WxQrCode.WX_API['qrcode_url']}?access_token={access_token}"
            
            # 请求参数
            data = {
                'path': path,
                'width': width
            }
            
            # 发送POST请求
            response = requests.post(url, json=data)
            
            # 检查响应内容类型
            content_type = response.headers.get('content-type', '')
            
            if 'image' in content_type:
                # 成功返回图片数据
                image_data = response.content
                base64_data = base64.b64encode(image_data).decode('utf-8')
                return {
                    'success': True,
                    'data': base64_data,
                    'message': '生成成功'
                }
            else:
                # 返回错误信息
                try:
                    error_info = response.json()
                    return {
                        'success': False,
                        'data': None,
                        'message': f"生成失败: {error_info.get('errmsg', '未知错误')}"
                    }
                except:
                    return {
                        'success': False,
                        'data': None,
                        'message': f"生成失败: HTTP {response.status_code}"
                    }
                    
        except Exception as e:
            logging.error(f"生成二维码异常: {str(e)}")
            return {
                'success': False,
                'data': None,
                'message': f'生成异常: {str(e)}'
            }
    
    @staticmethod
    def generate_zzbm_qrcode(introducer, width=430):
        """
        生成中职报名推广二维码
        
        Args:
            introducer (str): 推广人姓名
            width (int): 二维码宽度，默认430px
            
        Returns:
            dict: 包含二维码数据的字典
            {
                'success': True/False,
                'data': base64编码的图片数据 或 None,
                'message': 错误信息,
                'introducer': 推广人姓名,
                'scene': 生成的scene参数
            }
        """
        try:
            # 验证推广人姓名
            if not introducer or not introducer.strip():
                return {
                    'success': False,
                    'data': None,
                    'message': '推广人姓名不能为空',
                    'introducer': introducer,
                    'scene': None
                }
            
            # 清理推广人姓名
            introducer = introducer.strip()
            # 检查推广人姓名长度（scene参数最大32个字符）
            if len(introducer) > 30:  # 留2个字符给前缀
                return {
                    'success': False,
                    'data': None,
                    'message': '推广人姓名过长，最多30个字符',
                    'introducer': introducer,
                    'scene': None
                }
            
            # 构建scene参数，使用Base64 URL安全编码，兼容微信接口要求
            import base64
            introducer_bytes = introducer.encode('utf-8')
            introducer_b64 = base64.urlsafe_b64encode(introducer_bytes).decode('ascii').rstrip('=')
            scene = f"uid={introducer_b64}"
            # 目标页面路径
            page = "pages/vocational-zzbm/vocational-zzbm"
            # 生成无限制小程序码
            result = WxQrCode.generate_wxacode_unlimited(scene, page, width)
            
            # 添加额外信息到返回结果
            result['introducer'] = introducer
            result['scene'] = scene
            
            return result
            
        except Exception as e:
            logging.error(f"生成中职报名二维码异常: {str(e)}")
            return {
                'success': False,
                'data': None,
                'message': f'生成异常: {str(e)}',
                'introducer': introducer,
                'scene': None
            }

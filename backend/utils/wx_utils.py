import requests
import httpx
import io
import base64
import logging
import asyncio
from typing import Optional, Dict, Any

# 微信 access_token 缓存配置
WX_TOKEN_CACHE_KEY = "zhpt:wx:access_token"
WX_TOKEN_EXPIRE = 7000  # 微信token有效期7200秒，提前200秒刷新


class WxUtils:
    # 微信小程序配置
    WX_CONFIG = {
        'appid': 'wxe8f312724bfb12f0',
        'secret': '0175cc4b75d631412dcc94bcf88e9f70'
    }

    # 微信API地址
    WX_API = {
        'login_url': 'https://api.weixin.qq.com/sns/jscode2session',
        'token_url': 'https://api.weixin.qq.com/cgi-bin/token',
        'wxacode_url': 'https://api.weixin.qq.com/wxa/getwxacode',
        'wxacode_unlimited_url': 'https://api.weixin.qq.com/wxa/getwxacodeunlimit',
        'qrcode_url': 'https://api.weixin.qq.com/cgi-bin/wxaapp/createwxaqrcode',
        'phone_url': 'https://api.weixin.qq.com/wxa/business/getuserphonenumber'
    }

    @staticmethod
    def get_openid_and_session_key(code):
        """
        通过code获取openid和session_key
        
        Args:
            code: 小程序登录时获取的 code
            
        Returns:
            dict: 包含 openid 和 session_key 的字典，失败返回 None
            {
                'openid': 'xxx',
                'session_key': 'xxx'
            }
        """
        try:
            # 请求微信登录API
            data = {
                'appid': WxUtils.WX_CONFIG['appid'],
                'secret': WxUtils.WX_CONFIG['secret'],
                'js_code': code,
                'grant_type': 'authorization_code'
            }
            response = requests.get(WxUtils.WX_API['login_url'], params=data)
            result = response.json()
            print(f"获取结果是: {result}")
            # 检查微信登录是否成功
            if 'openid' in result and 'session_key' in result:
                return {
                    'openid': result['openid'],
                    'session_key': result['session_key']
                }
            else:
                print("微信登录失败:", result)
                return None
                
        except Exception as e:
            print("获取openid异常:", str(e))
            return None

    @staticmethod
    async def get_openid_and_session_key_async(code: str) -> Optional[Dict[str, str]]:
        """
        异步获取openid和session_key
        
        Args:
            code: 小程序登录时获取的 code
            
        Returns:
            dict: 包含 openid 和 session_key 的字典，失败返回 None
        """
        try:
            data = {
                'appid': WxUtils.WX_CONFIG['appid'],
                'secret': WxUtils.WX_CONFIG['secret'],
                'js_code': code,
                'grant_type': 'authorization_code'
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(WxUtils.WX_API['login_url'], params=data)
                result = response.json()
            
            logging.debug(f"获取openid结果: {result}")
            
            if 'openid' in result and 'session_key' in result:
                return {
                    'openid': result['openid'],
                    'session_key': result['session_key']
                }
            else:
                logging.warning(f"微信登录失败: {result}")
                return None
                
        except Exception as e:
            logging.error(f"获取openid异常: {str(e)}")
            return None

    @staticmethod
    def get_access_token(force_refresh: bool = False):
        """
        获取微信小程序access_token（带Redis缓存）
        优先从缓存获取，缓存失效时请求微信API并更新缓存

        Args:
            force_refresh: 是否强制刷新token，忽略缓存

        Returns:
            str: access_token，失败返回 None
        """
        try:
            # 如果不是强制刷新，尝试从Redis缓存获取
            if not force_refresh:
                from init.redis_manager import redis_manager
                cached_token = redis_manager.get(WX_TOKEN_CACHE_KEY)
                if cached_token:
                    logging.debug("使用缓存的access_token")
                    return cached_token

            # 缓存未命中或强制刷新，请求微信API
            data = {
                'grant_type': 'client_credential',
                'appid': WxUtils.WX_CONFIG['appid'],
                'secret': WxUtils.WX_CONFIG['secret']
            }

            response = requests.get(WxUtils.WX_API['token_url'], params=data, timeout=10)
            result = response.json()

            if 'access_token' in result:
                token = result['access_token']
                # 缓存到Redis
                from init.redis_manager import redis_manager
                redis_manager.set(WX_TOKEN_CACHE_KEY, token, ex=WX_TOKEN_EXPIRE)
                logging.info("获取并缓存新的access_token")
                return token
            else:
                logging.error(f"获取access_token失败: {result}")
                return None

        except Exception as e:
            logging.error(f"获取access_token异常: {str(e)}")
            return None

    @staticmethod
    async def get_access_token_async(force_refresh: bool = False) -> Optional[str]:
        """
        异步获取微信小程序access_token（带Redis缓存）

        Args:
            force_refresh: 是否强制刷新token，忽略缓存

        Returns:
            str: access_token，失败返回 None
        """
        try:
            # 如果不是强制刷新，尝试从Redis缓存获取
            if not force_refresh:
                from init.redis_manager import redis_manager
                cached_token = redis_manager.get(WX_TOKEN_CACHE_KEY)
                if cached_token:
                    logging.debug("使用缓存的access_token")
                    return cached_token

            # 缓存未命中或强制刷新，异步请求微信API
            data = {
                'grant_type': 'client_credential',
                'appid': WxUtils.WX_CONFIG['appid'],
                'secret': WxUtils.WX_CONFIG['secret']
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(WxUtils.WX_API['token_url'], params=data)
                result = response.json()

            if 'access_token' in result:
                token = result['access_token']
                # 缓存到Redis
                from init.redis_manager import redis_manager
                redis_manager.set(WX_TOKEN_CACHE_KEY, token, ex=WX_TOKEN_EXPIRE)
                logging.info("获取并缓存新的access_token")
                return token
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
            # 获取access_token（已带缓存）
            access_token = WxUtils.get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'data': None,
                    'message': '获取access_token失败'
                }

            # 构建请求URL
            url = f"{WxUtils.WX_API['wxacode_url']}?access_token={access_token}"

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
            # 获取access_token（已带缓存）
            access_token = WxUtils.get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'data': None,
                    'message': '获取access_token失败'
                }

            # 构建请求URL
            url = f"{WxUtils.WX_API['wxacode_unlimited_url']}?access_token={access_token}"

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
            # 获取access_token（已带缓存）
            access_token = WxUtils.get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'data': None,
                    'message': '获取access_token失败'
                }

            # 构建请求URL
            url = f"{WxUtils.WX_API['qrcode_url']}?access_token={access_token}"

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
    def get_phone_number(code, retry: bool = True):
        """
        通过code获取用户手机号
        
        Args:
            code: 小程序getPhoneNumber返回的code
            retry: 是否在token失效时重试
            
        Returns:
            dict: 包含手机号信息的字典，失败返回 None
            {
                'phone_info': {
                    'phoneNumber': 'xxx',
                    'purePhoneNumber': 'xxx',
                    'countryCode': 'xxx'
                }
            }
        """
        try:
            # 获取access_token（已带缓存）
            access_token = WxUtils.get_access_token()
            if not access_token:
                logging.error("获取access_token失败")
                return None

            # 构建请求URL
            url = f"{WxUtils.WX_API['phone_url']}?access_token={access_token}"

            # 发送POST请求
            response = requests.post(url, json={'code': code}, timeout=10)
            result = response.json()

            logging.info(f"获取手机号结果: {result}")

            if result.get('errcode') == 0:
                return {'phone_info': result.get('phone_info')}
            elif result.get('errcode') == 40001 and retry:
                # access_token失效，强制刷新并重试
                logging.warning("access_token失效，清除缓存并重试")
                from init.redis_manager import redis_manager
                redis_manager.delete(WX_TOKEN_CACHE_KEY)
                # 强制刷新token
                access_token = WxUtils.get_access_token(force_refresh=True)
                if not access_token:
                    logging.error("刷新access_token失败")
                    return None
                # 重试请求
                url = f"{WxUtils.WX_API['phone_url']}?access_token={access_token}"
                response = requests.post(url, json={'code': code}, timeout=10)
                result = response.json()
                logging.info(f"重试获取手机号结果: {result}")
                if result.get('errcode') == 0:
                    return {'phone_info': result.get('phone_info')}
                else:
                    logging.error(f"重试后仍然失败: {result}")
                    return None
            else:
                logging.error(f"获取手机号失败: {result}")
                return None

        except Exception as e:
            logging.error(f"获取手机号异常: {str(e)}")
            return None

    @staticmethod
    async def get_phone_number_async(code: str, retry: bool = True) -> Optional[Dict[str, Any]]:
        """
        异步获取用户手机号（推荐在高并发场景使用）
        
        Args:
            code: 小程序getPhoneNumber返回的code
            retry: 是否在token失效时重试
            
        Returns:
            dict: 包含手机号信息的字典，失败返回 None
        """
        try:
            # 异步获取access_token（已带缓存）
            access_token = await WxUtils.get_access_token_async()
            if not access_token:
                logging.error("获取access_token失败")
                return None

            # 构建请求URL
            url = f"{WxUtils.WX_API['phone_url']}?access_token={access_token}"

            # 异步发送POST请求
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={'code': code})
                result = response.json()

            logging.info(f"获取手机号结果: {result}")

            if result.get('errcode') == 0:
                return {'phone_info': result.get('phone_info')}
            elif result.get('errcode') == 40001 and retry:
                # access_token失效，清除缓存并重试
                logging.warning("access_token失效，清除缓存并重试")
                from init.redis_manager import redis_manager
                redis_manager.delete(WX_TOKEN_CACHE_KEY)
                # 强制刷新token并重试
                return await WxUtils.get_phone_number_async(code, retry=False)
            else:
                logging.error(f"获取手机号失败: {result}")
                return None

        except Exception as e:
            logging.error(f"获取手机号异常: {str(e)}")
            return None
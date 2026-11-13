import os
import json
import time
import random
import base64
from datetime import datetime
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from Crypto.Signature import PKCS1_v1_5
import requests
import logging
from init.config import get_config

class WxPayUtil:
    """
    微信支付工具类

    查询订单返回格式说明：
    - success: 只有当HTTP状态码为200且trade_state为SUCCESS时才为True，其他情况都为False
    - req_code: HTTP状态码 (200, 400, 401, 403, 404, 429, 500等)
    - req_des: 请求状态描述
    - trade_state: 交易状态 (SUCCESS/REFUND/NOTPAY/CLOSED/REVOKED/USERPAYING/PAYERROR)
    - trade_state_desc: 交易状态中文描述

    创建支付订单返回格式说明：
    - success: 只有当HTTP状态码为200且成功获取prepay_id时才为True
    - req_code: HTTP状态码 (200, 400, 401, 403, 429, 500等)
    - req_des: 请求状态描述
    - prepay_id: 预支付交易会话标识 (成功时返回)
    - pay_params: 小程序调起支付参数 (成功时返回)
    - error_code: 错误码 (失败时返回)
    - error_desc: 错误描述 (失败时返回)

    支持的错误码：
    - APPID_MCHID_NOT_MATCH: AppID和mch_id不匹配
    - INVALID_REQUEST: 无效请求
    - MCH_NOT_EXISTS: 商户号不存在
    - PARAM_ERROR: 参数错误
    - SIGN_ERROR: 签名错误
    - NO_AUTH: 商户无权限
    - OUT_TRADE_NO_USED: 商户订单号重复
    - FREQUENCY_LIMITED: 频率超限
    - SYSTEM_ERROR: 系统错误
    """

    def __init__(self):
        """初始化微信支付工具类"""
        try:
            # 获取配置对象
            config = get_config('development')
            wechat_config = config.wechat

            self.app_id = wechat_config.APP_ID
            self.mch_id = wechat_config.MCH_ID
            self.serial_no = wechat_config.SERIAL_NO

            # 获取私钥文件的绝对路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 私钥文件路径（需要根据实际情况调整）
            self.private_key_path = os.path.join(current_dir, 'apiclient_key.pem')

            # 验证私钥文件是否存在
            if not os.path.exists(self.private_key_path):
                logging.warning(f"私钥文件不存在: {self.private_key_path}")
                # 不抛出异常，允许继续运行，但记录警告

            self.notify_url = wechat_config.NOTIFY_URL
            self.notify_url_template = wechat_config.NOTIFY_URL_TEMPLATE
            # 微信支付API URL
            self.pay_url = wechat_config.PAY_URL

            logging.info("微信支付工具类初始化成功")

        except Exception as e:
            logging.error(f"微信支付工具类初始化失败: {str(e)}")


    def out_trade_no(self):
        """生成订单号"""
        # 获取当前时间
        now = datetime.now()  # 修正 datetime 导入
        # 格式化日期时间字符串为 yyyymmddhhiiss
        formatted_datetime = now.strftime("%Y%m%d%H%M%S")
        # 生成一个0到9999之间的随机数
        random_number = random.randint(0, 9999)
        # 将日期时间字符串和随机数拼接
        return formatted_datetime + str(random_number)

    def _build_pay_params(self, prepay_id):
        """构造小程序调起支付的参数"""
        timestamp = str(int(time.time()))
        nonce_str = self._generate_nonce_str()
        package = f'prepay_id={prepay_id}'
        
        message = f'{self.app_id}\n{timestamp}\n{nonce_str}\n{package}\n'
        pay_sign = self._generate_signature(message)
        
        return {
            'timeStamp': timestamp,
            'nonceStr': nonce_str,
            'package': package,
            'signType': 'RSA',
            'paySign': pay_sign
        }

    def get_pay_params_by_prepay_id(self, prepay_id: str) -> dict:
        """
        通过预支付ID获取支付参数（用于老订单再次支付）
        :param prepay_id: 微信返回的预支付交易会话标识
        :return: 支付参数
        """
        try:
            pay_params = self._build_pay_params(prepay_id)
            return {
                'success': True,
                'pay_params': pay_params
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'生成支付参数失败: {str(e)}',
                'data': None
            }

    def _generate_nonce_str(self, length=32):
        """生成随机字符串"""
        chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return ''.join(random.choice(chars) for _ in range(length))

    def _build_sign_message(self, method, url_path, timestamp, nonce_str, body):
        """构建签名信息"""
        body_str = json.dumps(body) if body else ''
        return f'{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body_str}\n'

    def _generate_signature(self, message):
        """生成签名"""
        try:
            # 读取私钥文件内容
            with open(self.private_key_path, 'r') as f:
                private_key_data = f.read().strip()
            
            # 处理私钥格式
            if '-----BEGIN' not in private_key_data:
                # 如果是纯密钥内容，添加头尾标记
                lines = []
                # 每64个字符一行
                for i in range(0, len(private_key_data), 64):
                    lines.append(private_key_data[i:i+64])
                
                private_key_data = '-----BEGIN PRIVATE KEY-----\n' + \
                                 '\n'.join(lines) + \
                                 '\n-----END PRIVATE KEY-----'
                        
            # 导入私钥
            private_key = RSA.import_key(private_key_data)
            
            # 生成签名
            h = SHA256.new(message.encode('utf-8'))
            signer = PKCS1_v1_5.new(private_key)
            signature = signer.sign(h)
            
            return base64.b64encode(signature).decode('utf-8')
            
        except Exception as e:
            # print("\n--- 签名生成错误 ---")
            # print("错误类型:", type(e).__name__)
            # print("错误信息:", str(e))
            # print("私钥路径:", self.private_key_path)
            print("私钥内容前100个字符:", private_key_data[:100] if 'private_key_data' in locals() else 'Not loaded')
            raise

    def _build_authorization_header(self, nonce_str, timestamp, signature):
        """构建认证头"""
        return ('WECHATPAY2-SHA256-RSA2048 ' + 
                f'mchid="{self.mch_id}",'
                f'nonce_str="{nonce_str}",'
                f'signature="{signature}",'
                f'timestamp="{timestamp}",'
                f'serial_no="{self.serial_no}"')

    def query_order(self, out_trade_no):

        """
        查询微信支付订单
        :param out_trade_no: 商户订单号
        :return: 订单信息
        """
        try:
            # 准备请求参数
            timestamp = str(int(time.time()))
            nonce_str = self._generate_nonce_str()
            
            # 构建请求URL和路径
            url_path = f'/v3/pay/transactions/out-trade-no/{out_trade_no}'
            query_string = f'mchid={self.mch_id}'
            url = f'https://api.mch.weixin.qq.com{url_path}?{query_string}'
            
            # 构建签名信息
            message = (
                'GET\n'
                f'{url_path}?{query_string}\n'
                f'{timestamp}\n'
                f'{nonce_str}\n'
                '\n'
            )
            
            
            signature = self._generate_signature(message)
            
            # 构造请求头
            headers = {
                'Accept': 'application/json',
                'Authorization': self._build_authorization_header(nonce_str, timestamp, signature)
            }
            
            # 发送请求
            response = requests.get(url, headers=headers)
            wx_result = response.json()
            # HTTP状态码描述映射
            status_desc_map = {
                400: '参数错误',
                401: '验证不通过',
                403: '业务规则限制',
                404: '订单不存在',
                429: '频率超限',
                500: '系统异常'
            }
            # 交易状态描述映射
            trade_state_desc_map = {
                'SUCCESS': '支付成功',
                'REFUND': '转入退款',
                'NOTPAY': '未支付',
                'CLOSED': '已关闭',
                'REVOKED': '已撤销',
                'USERPAYING': '用户支付中',
                'PAYERROR': '支付失败',
                'UNKNOWN': '未知错误'
            }


            trade_state = wx_result.get('trade_state', 'UNKNOWN')
            if response.status_code == 200:
                if trade_state == 'SUCCESS':
                    return {
                        'success': True,  # 只有HTTP状态码200且交易状态为SUCCESS时才为true
                        'req_code': True,  # HTTP状态码
                        'req_des': '请求成功',  # 请求状态描述
                        'trade_state': trade_state,  # 交易状态
                        'trade_state_desc': trade_state_desc_map.get(trade_state, "未知错误"),
                        'transaction_id': wx_result.get('transaction_id', ''),
                        'out_trade_no': wx_result.get('out_trade_no', ''),   #微信端的订单号
                        'success_time':wx_result.get('success_time', ''),
                        'data': wx_result
                    }
                else:
                    return {
                        'success': False,  # 只有HTTP状态码200且交易状态为SUCCESS时才为true 
                        'req_code': True,  # HTTP状态码
                        'req_des': '请求成功',  # 请求状态描述
                        'trade_state': trade_state,  # 交易状态
                        'trade_state_desc': trade_state_desc_map.get(trade_state,"未知错误"),
                        'transaction_id': '',
                        'out_trade_no': '',
                        'success_time':'',
                        'data': wx_result
                    }
            else:
                # 请求成功，返回统一格式
                return {
                    'success': False,  # 只有HTTP状态码200且交易状态为SUCCESS时才为true
                    'req_code': False,  # HTTP状态码
                    'req_des': status_desc_map.get(response.status_code, f'HTTP错误{response.status_code}'),  # 请求状态描述
                    'trade_state': '',  # 交易状态
                    'trade_state_desc': '',
                    'transaction_id': '',
                    'out_trade_no': '',
                    'success_time':'',
                    'data': None
                }
        except Exception as e:
            return {
                'success': False,
                'req_code': False,  # 异常情况，无HTTP状态码
                'req_des': '系统异常',  # 请求状态：系统异常
                'trade_state': 'SYSTEM_ERROR',  # 交易状态：系统错误
                'trade_state_desc': '系统异常',
                'transaction_id': '',
                'out_trade_no': '',
                'success_time':'',
                'data': None
            }
        

    def create_pay_info(self, openid, out_trade_no, total_fee, description, business_type: str = None):
        """
        创建支付参数
        :param openid: 用户openid
        :param out_trade_no: 订单号
        :param total_fee: 支付金额(分)
        :param description: 商品描述
        :param business_type: 业务类型，用于回调时区分不同的支付业务 (如: vocational_tuition-职业教育学费, degree_english-学位英语等)
        :return: 支付参数
        """
        try:
            # 根据business_type动态构建回调URL
            if business_type:
                # 使用NOTIFY_URL_TEMPLATE生成带业务类型标识的回调URL
                notify_url = self.notify_url_template.format(table_name=business_type)
            else:
                notify_url = self.notify_url

            # 准备请求参数
            timestamp = str(int(time.time()))
            nonce_str = self._generate_nonce_str()
            print("notify_url:",notify_url)
            body = {
                "appid": self.app_id,
                "mchid": self.mch_id,
                "description": description,
                "out_trade_no": out_trade_no,
                "notify_url": notify_url,
                "amount": {
                    "total": total_fee,
                    "currency": "CNY"
                },
                "payer": {
                    "openid": openid
                }
            }
            
            # 生成签名字符串
            message = self._build_sign_message('POST', '/v3/pay/transactions/jsapi',timestamp, nonce_str, body)
            # 生成签名
            signature = self._generate_signature(message)
            
            # 构造请求头，要把生成的签名放进请求头里面去。
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': self._build_authorization_header(nonce_str, timestamp, signature)
            }
            
            # 发送请求
            response = requests.post(
                self.pay_url,
                data=json.dumps(body),
                headers=headers
            )
            # 请求成功返回的结果 {"prepay_id" : "wx201410272009395522657a690389285100"}}
            # 请求失败返回的结果 {'code': 'INVALID_REQUEST', 'message': '201 商户订单号重复'}
            wx_result = response.json()
            # 创建支付订单错误码映射
            error_code_desc_map = {
                'APPID_MCHID_NOT_MATCH': 'AppID和mch_id不匹配',
                'INVALID_REQUEST': '无效请求',
                'MCH_NOT_EXISTS': '商户号不存在',
                'PARAM_ERROR': '参数错误',
                'SIGN_ERROR': '签名错误',
                'NO_AUTH': '商户无权限',
                'OUT_TRADE_NO_USED': '商户订单号重复',
                'FREQUENCY_LIMITED': '频率超限',
                'SYSTEM_ERROR': '系统错误',
                'UNKNOWN_ERROR': '未知错误'
            }

            # HTTP状态码描述映射
            status_desc_map = {
                200: '请求成功',
                400: '参数错误',
                401: '签名错误',
                403: '商户无权限',
                429: '频率超限',
                500: '系统错误'
            }
            print("创建支付订单返回的结果：",wx_result)
            # 处理响应
            if response.status_code == 200:
                
                if 'prepay_id' in wx_result:
                    # 成功获取prepay_id
                    pay_params = self._build_pay_params(wx_result['prepay_id'])
                    return {
                        'success': True,
                        'req_code': True,
                        'req_des': '请求成功',
                        'prepay_id': wx_result['prepay_id'],
                        'pay_params': pay_params
                    }
                else:
                    # 请求成功但没有prepay_id，可能是业务错误
                    error_code = wx_result.get('code', 'UNKNOWN_ERROR')
                    error_message = error_code_desc_map.get(error_code, '未知错误')

                    return {
                        'success': False,
                        'req_code': True,
                        'req_des': '请求成功但业务失败',
                        'error_code': error_code,
                        'error_desc': error_message
                    }
            else:
                # HTTP请求失败
                error_code = wx_result.get('code', 'UNKNOWN_ERROR')
                if error_code == 'INVALID_REQUEST':
                    error_message = wx_result.get('message', '未知错误')
                else:
                    error_message = error_code_desc_map.get(error_code, '未知错误')
                return {
                    'success': False,
                    'req_code': False,
                    'req_des': status_desc_map.get(response.status_code, f'HTTP错误{response.status_code}'),
                    'error_code': error_code,
                    'error_desc': error_message,
                    'data': None
                }
        except Exception as e:
            return {
                'success': False,
                'req_code': False,
                'req_des': '系统异常',
                'error_code': 'SYSTEM_ERROR',
                'error_desc': '系统异常',
                'msg': f'创建支付订单异常: {str(e)}',
                'data': None
            }

    def close_order(self, out_trade_no: str) -> dict:
        """
        关闭订单
        :param out_trade_no: 商户订单号
        :return: 关闭结果
        """
        try:
            timestamp = str(int(time.time()))
            nonce_str = self._generate_nonce_str()

            # 关单请求不需要body，但要生成签名
            message = self._build_sign_message('POST', f'/v3/pay/transactions/out-trade-no/{out_trade_no}/close', timestamp, nonce_str, None)
            signature = self._generate_signature(message)

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': self._build_authorization_header(nonce_str, timestamp, signature)
            }

            response = requests.post(
                f'{self.pay_url}/v3/pay/transactions/out-trade-no/{out_trade_no}/close',
                data=json.dumps({}),
                headers=headers
            )

            if response.status_code == 204:
                return {
                    'success': True,
                    'req_code': True,
                    'req_des': '关单成功'
                }
            else:
                wx_result = response.json()
                error_code = wx_result.get('code', 'UNKNOWN_ERROR')
                error_message = wx_result.get('message', '关单失败')
                return {
                    'success': False,
                    'req_code': False,
                    'req_des': '关单失败',
                    'error_code': error_code,
                    'error_desc': error_message
                }
        except Exception as e:
            return {
                'success': False,
                'req_code': False,
                'req_des': '系统异常',
                'error_code': 'SYSTEM_ERROR',
                'error_desc': f'关单异常: {str(e)}'
            }

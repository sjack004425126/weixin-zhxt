import requests
import os
import json
import time
import uuid
from datetime import datetime
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate


# 微信支付转账工具类，封装微信支付V3 API的转账相关功能
class WxPayTransfer:

    # 初始化微信支付转账工具类，加载配置
    def __init__(self):

        self.mch_id = "1575333221"
        self.private_key_path = 'apiclient_key_private_shsf.pem'
        self.private_key_Serial_no = '181059BB98CA99418912F5A9FCE27A829799C5FB'
        self.appid = 'wxe8f312724bfb12f0'      #是在商户号里面绑定的黔东南开大的小程序appid。
        self.api_base_url = 'https://api.mch.weixin.qq.com'
        self.transfer_scene_id = '1011'

        # 获取微信支付平台证书公钥，即可用于支付，也可用于加密user_name
        # 微信支付平台证书公钥路径，用于加密user_name
        self.wx_public_key_path = 'wechatpay_4446B03EC42569E2E4C21A43079CC2688EDFD6E2.pem'
        self.Wechatpay_Serial_no = '4446B03EC42569E2E4C21A43079CC2688EDFD6E2'


    def _generate_authorization(self, method, url_path, body=None):
        """生成微信支付API认证信息
        
        Args:
            method: HTTP方法，如GET、POST等
            url_path: API路径，如/v3/fund-app/mch-transfer/transfer-bills
            body: 请求体，可选
            
        Returns:
            str: 认证信息字符串
        """
        # 加载商户私钥
        with open(f"{os.path.dirname(__file__)}/{self.private_key_path}", 'rb') as f:
            private_key = load_pem_private_key(f.read(), password=None)
        
        timestamp = str(int(time.time()))
        nonce_str = str(uuid.uuid4()).replace('-', '')
        
        if body:
            body_str = json.dumps(body)
        else:
            body_str = ''
        
        message = f'{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body_str}\n'
        
        # 使用私钥签名
        signature = private_key.sign(
            message.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        signature_base64 = base64.b64encode(signature).decode('utf-8')
        
        # 构造认证信息
        authorization = f'WECHATPAY2-SHA256-RSA2048 mchid="{self.mch_id}",nonce_str="{nonce_str}",timestamp="{timestamp}",serial_no="{self.private_key_Serial_no}",signature="{signature_base64}"'
        
        return authorization
    

    def _rsa_encrypt_oaep(self, message: str) -> str:
        """
        使用RSA/ECB/OAEPWithSHA-1AndMGF1Padding方式加密信息
        :param message: 待加密字符串
        :param certificate_pem: 证书内容（PEM格式字符串）
        :return: base64编码的加密结果
        """
        try:
            with open(f"{os.path.dirname(__file__)}/{self.wx_public_key_path}", "r", encoding="utf-8") as f:
                cert_pem = f.read()
            cert = load_pem_x509_certificate(cert_pem.encode('utf-8'))
            public_key = cert.public_key()
            cipherdata = public_key.encrypt(
                message.encode('utf-8'),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA1()),
                    algorithm=hashes.SHA1(),
                    label=None
                )
            )
            return base64.b64encode(cipherdata).decode('utf-8')
        except ValueError as e:
            print("ValueError:", e)
            raise ValueError("无效的证书") from e
        except Exception as e:
            print("Exception:", type(e), e)
            raise Exception(f"加密异常: {type(e).__name__}: {e}") from e

    
    def _make_request(self, method, url_path, body=None):
        """发送HTTP请求到微信支付API
        
        Args:
            method: HTTP方法，如GET、POST等
            url_path: API路径，如/v3/fund-app/mch-transfer/transfer-bills
            body: 请求体，可选
            
        Returns:
            dict: 微信支付API的响应结果
        """
        url = f'{self.api_base_url}{url_path}'
        authorization = self._generate_authorization(method, url_path, body)


        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': authorization,
            'Wechatpay-Serial': self.Wechatpay_Serial_no
        }
        
        if method == 'GET':
            response = requests.get(url, headers=headers)
        else:
            response = requests.post(url, headers=headers, json=body)
        
        return response.json()
    



    def transfer(self, openid, user_name, transfer_amount, transfer_remark, out_bill_no=None, 
                notify_url=None, user_recv_perception=None, 
                transfer_scene_report_infos=None):
        """发起转账
        
        Args:
            openid: 用户openid
            user_name: 用户真实姓名（将自动加密）
            transfer_amount: 转账金额，单位分
            transfer_remark: 转账备注
            out_bill_no: 商户转账单号，不传则自动生成
            notify_url: 回调通知地址，不传则使用配置中的默认地址
            user_recv_perception: 用户收款感知，如"现金奖励"
            transfer_scene_report_infos: 转账场景上报信息，如活动名称、奖励说明等
            
        Returns:
            dict: 转账结果
        """
        url_path = '/v3/fund-app/mch-transfer/transfer-bills'
        # 如果没有提供商户转账单号，则自动生成

        
        # 如果没有提供回调通知地址，则使用配置中的默认地址
        if not notify_url:
            notify_url = 'https://m.qdndd.com.cn/wxpay/transfer/notify'
        
        # 加密用户姓名
        encrypted_user_name = self._rsa_encrypt_oaep(user_name)
        
        body = {
            'appid': self.appid,
            'out_bill_no': out_bill_no,
            'transfer_scene_id': self.transfer_scene_id,
            'openid': openid,
            'transfer_amount': transfer_amount,
            'transfer_remark': transfer_remark,
            #'notify_url': notify_url,
            'user_recv_perception':'商家赔付',
            'transfer_scene_report_infos': [
                {
                    "info_type" :   "赔付原因",
                    "info_content" : "商品质量问题退款"
                }
            ]
        }
        
        
        # 如果提供了用户姓名，则添加到请求体中,并且转账金额大于0.3元，否则不能加姓名，否则报错
        if encrypted_user_name and transfer_amount>30:
            body['user_name'] = encrypted_user_name
        
        # 添加可选参数
        if user_recv_perception:
            body['user_recv_perception'] = user_recv_perception
        return self._make_request('POST', url_path, body)
    


    def query_transfer_status(self, out_bill_no):
        """查询转账状态
        
        Args:
            out_bill_no: 商户转账单号
            
        Returns:
            dict: 转账状态查询结果
        """
        url_path = f'/v3/fund-app/mch-transfer/transfer-bills/out-bill-no/{out_bill_no}'
        
        return self._make_request('GET', url_path)
    
    def query_transfer_bill(self, out_bill_no):
        """查询转账账单
        
        Args:
            out_bill_no: 商户转账单号
            
        Returns:
            dict: 转账账单查询结果
        """
        url_path = f'/v3/fund-app/mch-transfer/transfer-bills/out-bill-no/{out_bill_no}/bill'
        
        return self._make_request('GET', url_path)
"""
MAS短信平台回调接口配置
用于配置短信平台的回调参数和验证
"""

# 短信平台配置
SMS_PLATFORM_CONFIG = {
    # 回调接口地址（需要根据实际部署情况修改）
    'callback_url': 'http://your-domain.com/admin/sms/callback',
    'batch_callback_url': 'http://your-domain.com/admin/sms/callback/batch',
    
    # 短信平台账户信息
    'account_id': 'your_account_id',
    'api_key': 'your_api_key',
    'secret_key': 'your_secret_key',
    
    # 回调验证
    'enable_signature_verify': True,  # 是否启用签名验证
    'signature_algorithm': 'md5',  # 签名算法
    
    # 超时设置
    'callback_timeout': 30,  # 回调超时时间（秒）
    'retry_times': 3,  # 重试次数
    'retry_interval': 5,  # 重试间隔（秒）
}

# 回调参数映射
CALLBACK_PARAM_MAPPING = {
    # 标准参数名 -> 可能的别名
    'cpSubID': ['cp_sub_id', 'subid', 'sub_id'],
    'status': ['status_code', 'result_code', 'code'],
    'statusDesc': ['status_desc', 'status_description', 'desc'],
    'mobile': ['phone', 'xs_dh', 'phone_number'],
    'msgContent': ['msg_content', 'content', 'message'],
    'msgCount': ['msg_count', 'count', 'sms_count'],
    'submitTime': ['submit_time', 'submit_at'],
    'reportTime': ['report_time', 'report_at', 'callback_time'],
}

# 状态码映射（用于不同平台的状态码转换）
STATUS_CODE_MAPPING = {
    # 标准状态码 -> 平台状态码
    0: [0, '0', 'success', 'SUCCESS'],  # 成功
    'MX:1315': ['1315', 'MX:1315'],  # 号段错误
    'MX:0003': ['0003', 'MX:0003'],  # 单个号码当天下发条数超过上限
    'MX:0004': ['0004', 'MX:0004'],  # 短信内容包含敏感词
    'MX:0005': ['0005', 'MX:0005'],  # 模板无法匹配
    'MX:0008': ['0008', 'MX:0008'],  # 签名无法匹配通道
    'MX:0013': ['0013', 'MX:0013'],  # 黑名单
    'MX:0014': ['0014', 'MX:0014'],  # 省份屏蔽
    'MX:0020': ['0020', 'MX:0020'],  # 单个号码相同内容超过上限
    'MX:0021': ['0021', 'MX:0021'],  # 单个号码当天下发条数超过上限(同个平台)
    'MN00001': ['00001', 'MN00001'],  # 空号
    'DB00107': ['00107', 'DB00107'],  # 业务代码错误
    'DB00108': ['00108', 'DB00108'],  # 欠费或投诉关停
    'DB00140': ['00140', 'DB00140'],  # 号码不在白名单中
    'DB00143': ['00143', 'DB00143'],  # 提交超限
    'DB:9066': ['9066', 'DB:9066'],  # 黑名单
    'UNDELIV': ['UNDELIV', 'UNDELIV'],  # 手机端问题
}


def get_callback_param(data: dict, param_name: str, default=None):
    """
    从回调数据中获取参数，支持多个别名
    
    Args:
        data: 回调数据字典
        param_name: 参数名
        default: 默认值
    
    Returns:
        参数值或默认值
    """
    # 先尝试标准参数名
    if param_name in data:
        return data[param_name]
    
    # 再尝试别名
    aliases = CALLBACK_PARAM_MAPPING.get(param_name, [])
    for alias in aliases:
        if alias in data:
            return data[alias]
    
    return default


def normalize_status_code(status_code):
    """
    规范化状态码，将平台状态码转换为标准状态码
    
    Args:
        status_code: 平台返回的状态码
    
    Returns:
        标准状态码
    """
    # 如果已经是标准状态码，直接返回
    if status_code in STATUS_CODE_MAPPING:
        return status_code
    
    # 查找对应的标准状态码
    for standard_code, platform_codes in STATUS_CODE_MAPPING.items():
        if status_code in platform_codes:
            return standard_code
    
    # 如果找不到，返回原值
    return status_code


def verify_callback_signature(data: dict, signature: str, secret_key: str) -> bool:
    """
    验证回调签名
    
    Args:
        data: 回调数据
        signature: 回调签名
        secret_key: 密钥
    
    Returns:
        bool: 签名是否有效
    """
    import hashlib
    
    # 构建签名字符串（需要根据平台文档调整）
    sign_str = '&'.join([f"{k}={v}" for k, v in sorted(data.items())])
    sign_str = f"{sign_str}&key={secret_key}"
    
    # 计算签名
    calculated_signature = hashlib.md5(sign_str.encode()).hexdigest()
    
    return calculated_signature.lower() == signature.lower()


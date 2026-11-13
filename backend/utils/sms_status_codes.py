"""
短信发送状态码映射表
用于记录和解析短信发送的各种状态
"""

# 短信发送状态码映射
SMS_STATUS_CODES = {
    "0": "成功",
    "MX:1315": "号段错误",
    "MX:0003": "单个号码当天下发条数超过上限(长短信算1条)",
    "MX:0004": "短信内容包含敏感词",
    "MX:0005": "模板无法匹配",
    "MX:0008": "签名无法匹配通道",
    "MX:0013": "黑名单",
    "MX:0014": "省份屏蔽",
    "MX:0020": "单个号码相同内容，当天下发条数超过上限",
    "MX:0021": "单个号码当天下发条数超过上限(同个平台)",
    "MN00001": "空号",
    "DB00107": "业务代码错误或者产品未建立",
    "DB00108": "欠费或投诉关停",
    "DB00140": "号码不在白名单中",
    "DB00143": "提交超限",
    "DB:9066": "黑名单",
    "UNDELIV": "手机端问题",
}

# 按状态分类
SUCCESS_STATUS = 0
ERROR_STATUSES = {
    "0": "成功",
    "MX:1315": "号段错误",
    "MX:0003": "单个号码当天下发条数超过上限(长短信算1条)",
    "MX:0004": "短信内容包含敏感词",
    "MX:0005": "模板无法匹配",
    "MX:0008": "签名无法匹配通道",
    "MX:0013": "黑名单",
    "MX:0014": "省份屏蔽",
    "MX:0020": "单个号码相同内容，当天下发条数超过上限",
    "MX:0021": "单个号码当天下发条数超过上限(同个平台)",
    "MN00001": "空号",
    "DB00107": "业务代码错误或者产品未建立",
    "DB00108": "欠费或投诉关停",
    "DB00140": "号码不在白名单中",
    "DB00143": "提交超限",
    "DB:9066": "黑名单",
    "UNDELIV": "手机端问题",
}


def get_status_description(status_code):
    """
    根据状态码获取状态描述
    
    Args:
        status_code: 状态码 (0 表示成功，其他为错误码)
    
    Returns:
        str: 状态描述
    """
    if status_code in SMS_STATUS_CODES:
        return SMS_STATUS_CODES[status_code]
    return f"未知状态: {status_code}"


def is_success(status_code):
    """
    判断是否发送成功
    
    Args:
        status_code: 状态码
    
    Returns:
        bool: True 表示成功，False 表示失败
    """
    return status_code == SUCCESS_STATUS


def is_error(status_code):
    """
    判断是否发送失败
    
    Args:
        status_code: 状态码
    
    Returns:
        bool: True 表示失败，False 表示成功
    """
    return status_code in ERROR_STATUSES


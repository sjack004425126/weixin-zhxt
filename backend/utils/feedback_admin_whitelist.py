"""校园反馈管理员白名单(写死配置)
仅列表中的手机号在小程序内可见"校园反馈管理"入口并可调用管理端接口。
新增/修改后需重启后端生效。
"""

FEEDBACK_ADMIN_WHITELIST = [
    {"phone": "15885828255", "name": "杨帆", "role": "分管校长"},
    {"phone": "18785112572", "name": "龙安发", "role": "后勤总负责人"},
    {"phone": "15286608119", "name": "杨昌坤", "role": "后勤总负责人"},
    {"phone": "15685905915", "name": "王正坊", "role": "后勤总负责人"},
    {"phone": "13885576813", "name": "粟多铭", "role": "维修组"},
    {"phone": "19082738316", "name": "吴师傅", "role": "维修组"},
    {"phone": "18984619084", "name": "石开华", "role": "开发者"},
    {"phone": "15121438850", "name": "杨仁伟", "role": "开发者"},
]


def is_feedback_admin(phone: str) -> bool:
    if not phone:
        return False
    phone = str(phone).strip()
    return any(item["phone"] == phone for item in FEEDBACK_ADMIN_WHITELIST)


def get_admin_info(phone: str):
    if not phone:
        return None
    phone = str(phone).strip()
    for item in FEEDBACK_ADMIN_WHITELIST:
        if item["phone"] == phone:
            return item
    return None

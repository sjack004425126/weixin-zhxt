"""
腾讯云短信模板注册表（统一管理模板 ID 与模板变量）

腾讯云短信必须使用「已审核通过的模板」，不能像旧 MAS 平台那样直接下发自由文本。
审核越来越严，模板数量越少越好，因此本模块的设计目标是：

    **一个模板形状 = 一套变量结构，多个业务场景可共用同一个模板 ID**

核心设计
--------
1. 每个业务场景在 `TEMPLATE_SPECS` 里声明：
   - `env_key`    : 环境变量名（用于配置模板 ID）
   - `default_id` : 默认模板 ID（未配置环境变量时使用）
   - `params`     : **该模板接受的变量名列表，顺序即腾讯云的模板变量顺序**
   - `values`     : 变量含义说明（仅文档用）
   - `status`     : `approved` 已审核可用 / `pending` 待申请

2. 调用方**只声明业务数据**（values 字典），不关心模板要几个变量、什么顺序。
   工具按 `params` 声明自动截取并排序。

   例：`student_leave` 与 `student_stay` 结构完全相同，
       申请一个带变量的通用模板后，两者指向同一个 ID 即可，无需改任何调用点。

3. `params` 与 `default_id` 可以独立演进：
   换模板时若变量数量/顺序变了，只改注册表一处，业务代码不动。

环境变量
--------
    SMS_TPL_VERIFY              验证码模板
    SMS_TPL_QUERY_CODE          查询码通知模板
    SMS_TPL_STUDENT_LEAVE       请假结果通知（发给学生）
    SMS_TPL_STUDENT_LEAVE_TEACHER 请假提交提醒（发给班主任）
    SMS_TPL_STUDENT_STAY        留宿结果通知（发给学生）
    SMS_TPL_STUDENT_STAY_TEACHER 留宿提交提醒（发给班主任）
    SMS_TPL_FEEDBACK_DONE       反馈办结通知
    SMS_TPL_NOTIFY              通用通知（教师自定义）
    SMS_TPL_CUSTOM              兼容旧字段名，等同 SMS_TPL_NOTIFY
"""
import os
import logging

logger = logging.getLogger(__name__)

# ==================== 场景注册表 ====================
#
# params 里的变量名 → 取值来源（调用方 values 字典的 key）
#
#   code            验证码
#   expire_minutes  有效时间（分钟）
#   name            收件人姓名
#   query_code      查询码
#   biz_name        业务名称（如「成人教育预报名」）
#   apply_type      申请类型（如「请假」「留宿」）
#   status          处理结果（如「已通过」「已拒绝」）
#   period          时间段
#   title           标题
#   result          处理结果/备注
#   content         通知正文
#
TEMPLATE_SPECS = {
    # ---------------- 验证码 ----------------
    'verify': {
        'env_key': 'SMS_TPL_VERIFY',
        'default_id': '1022934870',
        'params': ['code', 'expire_minutes'],
        'values': {'code': '6位数字验证码', 'expire_minutes': '有效分钟数'},
        'title': '验证码通知',
        'desc': '登录、绑定、解绑等所有需要验证码的场景统一使用此模板。2026-11-11 起切创蓝云智模板 1022934870。',
        'status': 'approved',
    },

    # ---------------- 查询码通知 ----------------
    'query_code': {
        'env_key': 'SMS_TPL_QUERY_CODE',
        'default_id': '',
        'params': ['name', 'query_code', 'biz_name'],
        'values': {
            'name': '收件人姓名',
            'query_code': '查询码',
            'biz_name': '业务名称（成人教育预报名/3+4报名/毕业生就业调查等）',
        },
        'title': '报名查询码通知',
        'desc': '各类报名、调查提交成功或管理员刷新查询码后的通知。'
                'biz_name 用变量区分业务，无需每个业务单独申请模板。',
        'status': 'pending',
    },

    # ---------------- 请假 ----------------
    'student_leave': {
        'env_key': 'SMS_TPL_STUDENT_LEAVE',
        'default_id': '2757281',
        # 当前已审核模板 2757281 为「无变量」模板
        'params': [],
        # 计划中的通用模板结构（申请通用模板获批后，把 params 改成这个即可，
        # 与 student_stay 指向同一个模板 ID，业务代码无需改动）
        'future_params': ['name', 'apply_type', 'status'],
        'values': {},
        'title': '请假审批结果通知（发给学生）',
        'desc': '请假审批通过/拒绝后通知学生本人。'
                '当前用无变量模板 2757281（正文固定）。'
                '建议申请「申请结果通知」带变量模板，'
                '与 student_stay 指向同一个模板 ID。',
        'status': 'approved',
    },
    'student_leave_teacher': {
        'env_key': 'SMS_TPL_STUDENT_LEAVE_TEACHER',
        'default_id': '2757283',
        # 当前已审核模板 2757283 为「无变量」模板
        'params': [],
        'future_params': ['name', 'student_id', 'apply_type', 'period'],
        'values': {},
        'title': '请假提交提醒（发给班主任）',
        'desc': '学生提交请假申请后提醒班主任及时审核。'
                '当前用无变量模板 2757283（正文固定）。'
                '建议申请「审核提醒」带变量模板，'
                '与 student_stay_teacher 指向同一个模板 ID。',
        'status': 'approved',
    },

    # ---------------- 留宿 ----------------
    'student_stay': {
        'env_key': 'SMS_TPL_STUDENT_STAY',
        'default_id': '',
        'params': ['name', 'apply_type', 'status'],
        'future_params': ['name', 'apply_type', 'status'],
        'values': {
            'name': '收件人姓名',
            'apply_type': '申请类型（请假/留宿）',
            'status': '处理结果（已通过/已拒绝）',
        },
        'title': '申请审批结果通知（发给学生）',
        'desc': '请假/留宿审批通过或拒绝后通知学生本人。'
                '变量结构与 student_leave 完全一致，'
                '两者指向同一个「申请结果通知」模板 ID 即可。',
        'status': 'pending',
    },
    'student_stay_teacher': {
        'env_key': 'SMS_TPL_STUDENT_STAY_TEACHER',
        'default_id': '',
        'params': ['name', 'student_id', 'apply_type', 'period'],
        'future_params': ['name', 'student_id', 'apply_type', 'period'],
        'values': {
            'name': '学生姓名',
            'student_id': '学号',
            'apply_type': '申请类型（请假/留宿）',
            'period': '时间段',
        },
        'title': '申请提交审核提醒（发给班主任）',
        'desc': '请假/留宿申请提交后提醒班主任及时审核。'
                '变量结构与 student_leave_teacher 完全一致，'
                '两者指向同一个「审核提醒」模板 ID 即可。',
        'status': 'pending',
    },

    # ---------------- 反馈 ----------------
    'feedback_done': {
        'env_key': 'SMS_TPL_FEEDBACK_DONE',
        'default_id': '',
        'params': ['title', 'result'],
        'values': {'title': '反馈标题', 'result': '处理结果（建议截断）'},
        'title': '反馈办结通知',
        'desc': '用户反馈工单办结后通知反馈人。',
        'status': 'pending',
    },

    # ---------------- 通用通知 ----------------
    'notify': {
        'env_key': 'SMS_TPL_NOTIFY',
        'default_id': '',
        'params': ['content'],
        'values': {'content': '通知正文（教师自定义内容）'},
        'title': '通用通知',
        'desc': '教师向学生发送自定义通知。'
                '注意：含自由正文的模板审核最严，正文需符合通知类规范，'
                '建议限制长度并避免营销类措辞。',
        'status': 'pending',
    },
}

# 兼容旧场景名（旧代码用 'custom'）
SCENARIO_ALIASES = {
    'custom': 'notify',
}

# 旧环境变量名兼容（SMS_TPL_CUSTOM → SMS_TPL_NOTIFY）
_ENV_FALLBACK = {
    'SMS_TPL_NOTIFY': 'SMS_TPL_CUSTOM',
}


def _spec(scenario: str):
    """取场景配置，兼容别名"""
    if not scenario:
        return None
    sc = SCENARIO_ALIASES.get(scenario, scenario)
    return TEMPLATE_SPECS.get(sc)


def list_scenarios():
    """列出所有场景（供文档/管理页使用）

    Returns:
        list: [{key, title, env_key, default_id, params, status, desc}]
    """
    return [
        {
            'key': key,
            'title': spec['title'],
            'env_key': spec['env_key'],
            'default_id': spec['default_id'],
            'current_id': get_template_id(key),
            'params': _resolve_params_spec(key),
            'planned_params': spec.get('future_params') or spec['params'],
            'values': spec['values'],
            'status': spec['status'],
            'desc': spec['desc'],
        }
        for key, spec in TEMPLATE_SPECS.items()
    ]


def get_template_id(scenario: str) -> str:
    """取场景对应的腾讯云模板 ID

    Args:
        scenario: 业务场景

    Returns:
        str: 模板 ID；未配置时返回空串
    """
    spec = _spec(scenario)
    if not spec:
        return ''
    tpl_id = (os.getenv(spec['env_key']) or '').strip()
    if tpl_id:
        return tpl_id
    # 兼容旧环境变量名
    fallback_key = _ENV_FALLBACK.get(spec['env_key'])
    if fallback_key:
        tpl_id = (os.getenv(fallback_key) or '').strip()
        if tpl_id:
            return tpl_id
    return (spec.get('default_id') or '').strip()


def _resolve_params_spec(scenario: str) -> list:
    """决定该场景实际生效的模板变量列表

    规则：
    - 模板 ID 等于「已审核的无变量模板」→ 用 `params`（空列表）
    - 模板 ID 是后来申请/替换的 → 用 `future_params`（若已声明）

    这样切换模板时**只需改环境变量里的模板 ID**，无需改代码，
    变量数量/顺序会按注册表自动切换。

    Args:
        scenario: 业务场景

    Returns:
        list: 变量名列表
    """
    spec = _spec(scenario)
    if not spec:
        return []
    params = spec.get('params') or []
    future = spec.get('future_params')
    if not future:
        return params

    current_id = get_template_id(scenario)
    default_id = (spec.get('default_id') or '').strip()
    # 仍在用默认的无变量模板 → 用当前 params
    # 换成别的模板 ID → 认为新模板是带变量的通用模板
    if not current_id or current_id == default_id:
        return params
    return future


def build_params(scenario: str, values: dict = None) -> list:
    """按模板声明的变量顺序构造 template_param_set

    Args:
        scenario: 业务场景
        values: 业务数据字典（key 为变量名）

    Returns:
        list: 模板变量列表

    Raises:
        KeyError: 模板需要变量但 values 中缺失时抛出
    """
    spec = _spec(scenario)
    if not spec:
        return []
    values = values or {}
    params = []
    for name in _resolve_params_spec(scenario):
        if name not in values or values[name] is None:
            raise KeyError(
                f"场景 {scenario} 缺少模板变量 '{name}'"
                f"（模板 {spec['title']} 需要: {_resolve_params_spec(scenario)}）"
            )
        params.append(str(values[name]))
    return params


def resolve_template(scenario: str, values: dict = None):
    """解析出 (template_id, template_param_set, error)

    Args:
        scenario: 业务场景
        values: 业务数据字典

    Returns:
        (template_id, template_param_set, error)
        - template_id: 腾讯云模板 ID，空串表示未配置
        - template_param_set: 模板变量列表
        - error: 非空表示该场景无法发送（模板未配置），此时不应调用网关
    """
    spec = _spec(scenario)
    if not spec:
        return '', [], f'未知短信场景: {scenario}'

    template_id = get_template_id(scenario)
    if not template_id:
        logger.error(
            f"场景 {scenario}（{spec['title']}）未配置腾讯云模板ID，无法发送。"
            f"请在腾讯云后台申请该模板，并设置环境变量 {spec['env_key']}=<模板ID>"
        )
        return '', [], (
            f"场景「{spec['title']}」未配置短信模板（环境变量 {spec['env_key']}），"
            f'请管理员先在腾讯云后台申请并配置该模板'
        )

    try:
        params = build_params(scenario, values)
    except KeyError as e:
        return '', [], str(e)

    return template_id, params, ''

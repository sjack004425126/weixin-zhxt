import requests
import json
import os
import re
from datetime import datetime, timedelta
import logging

from utils.sms_callback_tencent import (
    SMS_GATEWAY_URL,
    SMS_DEFAULT_SIGN_NAME,
    SMS_SOURCE,
    SMS_VERIFY_EXPIRE_MINUTES,
)

logger = logging.getLogger(__name__)

# 腾讯通道模板 ID（与创蓝 utils/sms_templates.py 注册表解耦）。
# 说明：sms_templates.py 的 verify 默认已切到创蓝 1022934870，
# 腾讯保留通道必须用自己的 2726397，不能共用注册表，否则会误发创蓝模板。
TENCENT_VERIFY_TEMPLATE_ID = os.getenv(
    'SMS_TENCENT_TPL_VERIFY',
    os.getenv('SMS_TENCENT_VERIFY_TEMPLATE_ID', '2726397'),
)


class SMSTencentTool:
    """短信发送工具类（腾讯云，走管理员封装网关 sms_interface）

    与创蓝版 utils/sms.py 的 SMSTool 结构一致，仅通道不同：
    - 网关：utils/sms_callback_tencent.SMS_GATEWAY_URL（102 的 sms_interface）
    - 报文：template_id / template_param_set / session_context（无 product_type/report/callback_url）
    - 回调：腾讯侧不再处理，仅本地留档（cpSubID 存 SerialNo 备查）
    """

    def __init__(self, api_url: str = None):
        # 保留旧字段，避免其它模块引用报错
        self.user_id = "569"
        self.cp_key = "0722DD9239C6AF5DAB921F70AA64BDA3"
        self.api_url = api_url or SMS_GATEWAY_URL
        self.log_file = "logs/sms_requests.log"
        self.sign_name = SMS_DEFAULT_SIGN_NAME
        self.source = SMS_SOURCE

    # ==================== 基础工具 ====================

    def validate_mobile(self, mobile):
        """验证手机号码格式

        Args:
            mobile (str): 手机号码，可以是单个号码或逗号分隔的多个号码

        Returns:
            tuple: (bool, str) - (是否有效, 错误信息)
        """
        # 分割手机号码
        mobiles = mobile.split(',')
        # 验证每个号码
        for m in mobiles:
            m = m.strip()
            if not m:
                continue
            if not re.match(r'^1[3-9]\d{9}$', m):
                return False, f"无效的手机号码格式: {m}"
        return True, ""

    def generate_cp_sub_id(self):
        """生成唯一的任务编号 cpSubID：时间年月日时分秒 + 随机数

        Returns:
            str: 任务编号
        """
        import random
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join([str(random.randint(0, 9)) for _ in range(4)])
        return f"{timestamp}{random_suffix}"

    def log_sms_request(self, cp_sub_id, mobile, content, response_text, status="pending"):
        """记录短信请求到文本文件

        Args:
            cp_sub_id (str): 任务编号
            mobile (str): 手机号码
            content (str): 短信内容
            response_text (str): API响应
            status (str): 状态 (pending/success/failed)
        """
        try:
            from utils.log_setup import safe_append_line, get_log_dir

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "cpSubID": cp_sub_id,
                "mobile": mobile,
                "content": content,
                "response": response_text,
                "status": status
            }

            safe_append_line(
                os.path.join(get_log_dir(), "sms_requests.log"),
                json.dumps(log_entry, ensure_ascii=False) + "\n"
            )
            logger.info(f"短信请求已记录: cpSubID={cp_sub_id}, 状态={status}")
        except Exception as e:
            logger.error(f"记录短信请求失败: {str(e)}")

    # ==================== 网关调用 ====================

    @staticmethod
    def _extract_serial_no(data):
        """从网关返回的腾讯云响应里提取 SerialNo（= 回调里的 sid）

        Args:
            data: 网关返回的 data 字段

        Returns:
            str: SerialNo，解析不到返回空串
        """
        if not isinstance(data, dict):
            return ''
        candidates = [data]
        resp = data.get('Response')
        if isinstance(resp, dict):
            candidates.insert(0, resp)
        for c in candidates:
            if not isinstance(c, dict):
                continue
            status_set = c.get('SendStatusSet')
            if isinstance(status_set, list) and status_set:
                first = status_set[0]
                if isinstance(first, dict):
                    return str(first.get('SerialNo') or '')
            if c.get('SerialNo'):
                return str(c.get('SerialNo'))
        return ''

    def _call_gateway(self, mobiles, template_id, template_param_set,
                      session_context=None, userid=None, username=None):
        """调用短信网关发送（腾讯云 sms_interface）

        Args:
            mobiles: 手机号列表
            template_id: 腾讯云模板 ID
            template_param_set: 模板变量列表
            session_context: 上下文（原样回传，便于对账）
            userid: 接收方 ID（学生学号 / 教师用户名）
            username: 接收方姓名

        Returns:
            dict: 网关原始响应
        """
        payload = {
            'phone_number_set': list(mobiles),
            'template_id': template_id or None,
            'sign_name': self.sign_name,
            'template_param_set': list(template_param_set or []),
            'source': self.source,
        }
        if session_context:
            payload['session_context'] = session_context
        if userid:
            payload['userid'] = str(userid)
        if username:
            payload['username'] = str(username)

        logger.info(f"调用短信网关(腾讯): phones={mobiles}, template={template_id}, params={template_param_set}")
        response = requests.post(self.api_url, json=payload, timeout=15)
        try:
            result = response.json()
        except Exception:
            result = {'success': False, 'msg': f'网关返回非JSON: {response.text[:200]}'}
        return result

    # ==================== 发送入口 ====================

    def save_sms_log(self, cp_sub_id, xs_dh, content, response_text, xs_id=None, xs_xm=None,
                     lx=5, t_id=0, t_xm='系统', status_desc=None, sent_at=None):
        """将短信发送记录保存到sms_log数据库表（腾讯通道，回调不再处理）

        网关（172.16.100.102 腾讯 sms_interface）自己会往 sms_log 写一条 lx=7 的记录，
        其 cpSubID 存的是腾讯云 SerialNo。这里复用网关那条记录做本地留档，
        腾讯回调不再处理，仅备查。

        匹配策略：
        1. 已知 SerialNo 时按 cpSubID 精确匹配
        2. 否则按「手机号 + 最近一次未回调的 lx=7 记录 + 时间窗口」匹配
        3. 都匹配不到才新建一条（此时 cpSubID 退化为本地生成的 ID）

        Args:
            cp_sub_id (str): 任务编号（腾讯云 SerialNo，优先使用网关返回值）
            xs_dh (str): 收件方手机号码
            content (str): 短信内容
            response_text (str): API响应文本
            xs_id (str): 收件方学生ID
            xs_xm (str): 收件方学生姓名
            lx (int): 日志类型，默认5(系统)，3=开放学生短信
            t_id (int): 教师ID，默认0
            t_xm (str): 教师姓名，默认'系统'
            status_desc (str): 发送状态描述
            sent_at (datetime): 本次发送时间（用于匹配网关写入的记录）
        """
        try:
            from init.dependencies import get_db_sync
            from models.models import SMSLog
            db = get_db_sync()
            try:
                sent_at = sent_at or datetime.now()
                record = None

                # 1) 已知 SerialNo：按 cpSubID 精确匹配
                if cp_sub_id:
                    record = db.query(SMSLog).filter_by(cpSubID=cp_sub_id).first()

                # 2) 按手机号 + 时间窗口匹配网关写入的那条 lx=7 记录
                if record is None:
                    phone = str(xs_dh or '').strip()
                    if phone:
                        # 网关存的是 +86 前缀格式，兼容两种
                        phone_variants = {phone, f'+86{phone}', phone.lstrip('+')}
                        candidates = (
                            db.query(SMSLog)
                            .filter(
                                SMSLog.lx == 7,
                                SMSLog.xs_dh.in_(phone_variants),
                                SMSLog.callback_status.is_(None),
                                SMSLog.fssj >= sent_at - timedelta(seconds=120),
                                SMSLog.fssj <= sent_at + timedelta(seconds=30),
                            )
                            .order_by(SMSLog.id.desc())
                            .first()
                        )
                        if candidates:
                            record = candidates
                            # 回填 SerialNo，保证备查能按 sid 命中
                            if not record.cpSubID:
                                record.cpSubID = cp_sub_id
                            cp_sub_id = record.cpSubID

                if record:
                    # 复用网关的记录：补齐业务字段，保留网关写的 send_status/nr
                    record.lx = lx
                    record.t_id = t_id
                    record.t_xm = t_xm
                    record.fssj = record.fssj or sent_at
                    record.nr = content
                    record.xs_id = xs_id
                    record.xs_xm = xs_xm
                    record.xs_dh = xs_dh
                    record.num = 1
                    if status_desc:
                        record.status_desc = status_desc
                else:
                    record = SMSLog(
                        lx=lx,
                        t_id=t_id,
                        t_xm=t_xm,
                        fssj=sent_at,
                        nr=content,
                        xs_id=xs_id,
                        xs_xm=xs_xm,
                        xs_dh=xs_dh,
                        num=1,
                        cpSubID=cp_sub_id,
                        send_status='-1',
                        status_desc=status_desc,
                    )
                    db.add(record)
                db.commit()
                resolved_cp_sub_id = record.cpSubID
                logger.info(f"短信记录已保存到数据库: id={record.id}, cpSubID={resolved_cp_sub_id}")
            except Exception as e:
                db.rollback()
                resolved_cp_sub_id = cp_sub_id
                logger.error(f"保存短信记录到数据库失败: {str(e)}")
            finally:
                db.close()
            return resolved_cp_sub_id
        except Exception as e:
            logger.error(f"获取数据库连接失败: {str(e)}")
            return cp_sub_id

    def send_sms(self, xs_dh, content, xs_id=None, xs_xm=None, lx=5, t_id=0, t_xm='系统',
                 template_id=None, template_param_set=None, scenario=None,
                 userid=None, username=None, values=None):
        """通用短信发送方法（带 cpSubID，腾讯通道）

        Args:
            xs_dh (str): xs_dh手机号码
            content (str): 短信内容（仅用于日志留档，不作为下发内容）
            xs_id (str): 收件方学生ID（作为 userid 传给网关）
            xs_xm (str): 收件方学生姓名（作为 username 传给网关）
            lx (int): 日志类型，默认5(系统)，3=开放学生短信
            t_id (int): 教师ID，默认0
            t_xm (str): 教师姓名，默认'系统'
            template_id (str): 指定腾讯云模板 ID（优先于 scenario，推荐显式传入）
            template_param_set (list): 指定模板变量（优先于 scenario 推导）
            scenario (str): 业务场景，由注册表推导模板与变量（注意 verify 已切创蓝，
                腾讯 verify 请走 send_verify_sms 或显式传 template_id=2726397）
            values (dict): 业务数据字典（配合 scenario 使用）
            userid (str): 覆盖传给网关的 userid（学生=学号，教师=用户名）
            username (str): 覆盖传给网关的 username

        Returns:
            dict: {
                "success": bool,
                "msg": str,
                "data": {
                    "cpSubID": str,  # 任务编号（腾讯云 SerialNo）
                    "response": str  # API响应
                }
            }
        """
        try:
            # 验证手机号码格式
            is_valid, error_msg = self.validate_mobile(xs_dh)
            if not is_valid:
                return {"success": False, "msg": error_msg, "data": None}

            # 解析模板：显式 template_id 优先，否则按 scenario 从注册表推导
            if template_id is None:
                from utils.sms_templates import resolve_template as _resolve
                # verify 场景注册表已切创蓝，腾讯通道不走注册表，强制用腾讯模板
                if scenario == 'verify':
                    params = []
                    if isinstance(values, dict):
                        if 'code' in values:
                            params.append(str(values.get('code')))
                        if 'expire_minutes' in values:
                            params.append(str(values.get('expire_minutes')))
                    template_id, tpl_error = TENCENT_VERIFY_TEMPLATE_ID, ''
                    if not params:
                        tpl_error = '腾讯 verify 场景缺少模板变量'
                    if tpl_error:
                        return {"success": False, "msg": tpl_error, "data": None}
                else:
                    template_id, params, tpl_error = _resolve(
                        scenario=scenario, values=values
                    )
                    if tpl_error:
                        # 模板未配置 / 变量缺失：直接失败，不把错误内容发给用户
                        return {"success": False, "msg": tpl_error, "data": None}
            else:
                params = template_param_set if template_param_set is not None else []
            if template_param_set is not None:
                params = template_param_set

            # 预生成 cpSubID，作为 session_context 便于对账
            local_cp_sub_id = self.generate_cp_sub_id()
            sent_at = datetime.now()

            result = self._call_gateway(
                mobiles=xs_dh.split(','),
                template_id=template_id,
                template_param_set=params,
                session_context=local_cp_sub_id,
                userid=(userid if userid is not None else xs_id),
                username=(username if username is not None else xs_xm),
            )

            success = bool(result.get('success'))
            msg = result.get('msg') or ('发送成功' if success else '发送失败')
            data = result.get('data') or {}
            serial_no = self._extract_serial_no(data)

            # 腾讯云 SerialNo 存 cpSubID 备查（腾讯回调不再处理）
            cp_sub_id = serial_no or local_cp_sub_id

            response_text = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
            # 网关已写库时，这里会把网关那条的 SerialNo 回填/复用
            cp_sub_id = self.save_sms_log(
                cp_sub_id, xs_dh, content, response_text,
                xs_id=xs_id, xs_xm=xs_xm, lx=lx, t_id=t_id, t_xm=t_xm,
                status_desc=(response_text[:600] if success else None),
                sent_at=sent_at,
            ) or cp_sub_id
            self.log_sms_request(cp_sub_id, xs_dh, content, response_text,
                                 status='success' if success else 'failed')

            if success:
                return {
                    "success": True,
                    "msg": msg,
                    "data": {
                        "cpSubID": cp_sub_id,
                        "response": response_text
                    }
                }
            else:
                return {
                    "success": False,
                    "msg": f"发送失败: {msg}",
                    "data": {
                        "cpSubID": cp_sub_id,
                        "response": response_text
                    }
                }

        except Exception as e:
            logger.error(f"发送短信异常(腾讯): {str(e)}", exc_info=True)
            return {"success": False, "msg": f"发送异常: {str(e)}", "data": None}

    def send_by_scenario(self, scenario, mobile, values=None, xs_id=None, xs_xm=None,
                         lx=5, t_id=0, t_xm='系统', userid=None, username=None):
        """按业务场景发送短信（腾讯通道）

        调用方只提供业务数据，模板 ID 与变量顺序由 `utils/sms_templates.py`
        的注册表决定（verify 场景除外，强制用腾讯模板，见 send_sms 说明）。

        Args:
            scenario (str): 业务场景键（见 TEMPLATE_SPECS）
            mobile (str): 手机号码
            values (dict): 业务数据字典，key 为注册表声明的变量名
            xs_id (str): 收件方学生ID（作为 userid 传给网关）
            xs_xm (str): 收件方学生姓名（作为 username 传给网关）
            lx (int): 日志类型
            t_id (int): 教师ID
            t_xm (str): 教师姓名
            userid (str): 覆盖传给网关的 userid
            username (str): 覆盖传给网关的 username

        Returns:
            dict: {"success": bool, "msg": str, "data": {...} | None}
        """
        try:
            from utils.sms_templates import (
                resolve_template as _resolve,
                get_template_id as _get_tpl_id,
                _resolve_params_spec as _resolve_params,
                TEMPLATE_SPECS as _SPECS,
            )
            if scenario == 'verify':
                template_id, params, tpl_error = TENCENT_VERIFY_TEMPLATE_ID, [], ''
                _values = values or {}
                if 'code' in _values:
                    params.append(str(_values.get('code')))
                if 'expire_minutes' in _values:
                    params.append(str(_values.get('expire_minutes')))
                if not params:
                    tpl_error = '腾讯 verify 场景缺少模板变量'
                if tpl_error:
                    return {"success": False, "msg": tpl_error, "data": None}
            else:
                template_id, params, tpl_error = _resolve(
                    scenario=scenario, values=values
                )
                if tpl_error:
                    return {"success": False, "msg": tpl_error, "data": None}

            # 留档用的正文摘要（不是下发内容）
            content = self._build_log_content(scenario, values)

            return self.send_sms(
                xs_dh=mobile,
                content=content,
                xs_id=xs_id,
                xs_xm=xs_xm,
                lx=lx,
                t_id=t_id,
                t_xm=t_xm,
                template_id=template_id,
                template_param_set=params,
                userid=userid,
                username=username,
            )
        except Exception as e:
            logger.error(f"按场景发送短信异常(腾讯): scenario={scenario}, error={str(e)}", exc_info=True)
            return {"success": False, "msg": f"发送异常: {str(e)}", "data": None}

    @staticmethod
    def _build_log_content(scenario: str, values: dict = None) -> str:
        """构造日志留档用的正文摘要（真实下发内容由模板决定，此处仅供查询）"""
        from utils.sms_templates import (
            get_template_id as _get_tpl_id,
            _resolve_params_spec as _resolve_params,
            TEMPLATE_SPECS as _SPECS,
        )
        if scenario == 'verify':
            _values = values or {}
            parts = []
            if _values.get('code') is not None:
                parts.append(f"code={_values.get('code')}")
            if _values.get('expire_minutes') is not None:
                parts.append(f"expire_minutes={_values.get('expire_minutes')}")
            if parts:
                return f'模板[{TENCENT_VERIFY_TEMPLATE_ID}] 参数:{",".join(parts)}'
            return f'模板[{TENCENT_VERIFY_TEMPLATE_ID}]'
        spec = _SPECS.get(scenario)
        if not spec:
            return ''
        values = values or {}
        tpl_id = _get_tpl_id(scenario)
        # 无变量模板也记录业务值，便于事后按内容检索（如当前模板是固定文案）
        names = _resolve_params(scenario) or spec.get('future_params') or []
        parts = []
        for name in names:
            if name in values and values[name] is not None:
                parts.append(f'{name}={values[name]}')
        if not parts:
            return f'模板[{tpl_id}]'
        return f'模板[{tpl_id}] 参数:{",".join(parts)}'

    def send_verify_sms(self, mobile, code, expire_minutes=None):
        """发送验证码短信（腾讯通道）

        模板变量：验证码 + 有效时间（分钟），模板固定为腾讯 2726397。

        Args:
            mobile (str): 手机号码
            code (str): 验证码
            expire_minutes (int): 有效时间（分钟）

        Returns:
            dict: {"success": bool, "msg": str, "data": None}
        """
        minutes = expire_minutes or SMS_VERIFY_EXPIRE_MINUTES
        try:
            is_valid, error_msg = self.validate_mobile(mobile)
            if not is_valid:
                return {"success": False, "msg": error_msg, "data": None}

            result = self.send_sms(
                xs_dh=mobile,
                content=f'模板[{TENCENT_VERIFY_TEMPLATE_ID}] 参数:code={code},expire_minutes={minutes}',
                template_id=TENCENT_VERIFY_TEMPLATE_ID,
                template_param_set=[str(code), str(minutes)],
            )
            if result.get('success'):
                return {"success": True, "msg": result.get('msg'), "data": None}
            return {"success": False, "msg": result.get('msg'), "data": None}
        except Exception as e:
            logger.error(f"发送验证码短信异常(腾讯): {str(e)}", exc_info=True)
            return {"success": False, "msg": f"发送异常: {str(e)}", "data": None}

    def send_login_sms(self, mobile, code, expire_minutes=None):
        """发送登录验证码短信（与 send_verify_sms 同实现，保留兼容）"""
        return self.send_verify_sms(mobile, code, expire_minutes=expire_minutes)

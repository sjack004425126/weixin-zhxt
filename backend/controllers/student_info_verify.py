"""新生信息核对接口

提供：
- GET  /student_info_verify/info       获取当前学生可核对的个人信息 + 核对状态
- POST /student_info_verify/submit    提交核对结果

核对逻辑：
- status = 0: 字段有错误，学生提交了修正数据
- status = 1: 学生原始数据无误，对应的数据可以为空
- 有记录: 学生已经核对过信息
- 无记录: 学生没有核对过信息
- 已核对过: 不能再次修改
"""

from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.auth import verify_token_and_get_payload
from init.dependencies import DatabaseDep
from models.models import Student, OaXsXxhd, Class

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/student_info_verify", tags=["新生信息核对"])


# ============================================================
# 身份证号码格式校验（与前端 utils/util.js 的 isValidIdCard 保持一致）
# ============================================================
_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_CODES = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']


def _is_valid_id_card_date(date_str: str) -> bool:
    """校验身份证中的出生日期段 YYYYMMDD 是否为真实日期"""
    try:
        year = int(date_str[0:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
    except (ValueError, IndexError):
        return False

    if not year or not month or not day:
        return False
    if month < 1 or month > 12 or day < 1 or day > 31:
        return False

    import datetime as _dt
    try:
        d = _dt.date(year, month, day)
    except ValueError:
        return False
    return d.year == year and d.month == month and d.day == day


def is_valid_id_card(id_card: Optional[str]) -> bool:
    """校验身份证号码格式（15 位或 18 位，含出生日期与校验码）

    前端已有同样的校验，这里做后端兜底，防止绕过前端直接调接口写入脏数据。
    """
    if id_card is None:
        return False
    v = str(id_card).strip()
    if not v:
        return False

    # 18 位：前 17 位数字 + 第 18 位数字或 X
    if re.fullmatch(r"\d{17}[\dXx]", v):
        if not _is_valid_id_card_date(v[6:14]):
            return False
        total = sum(int(v[i]) * _ID_WEIGHTS[i] for i in range(17))
        return v[17].upper() == _ID_CHECK_CODES[total % 11]

    # 15 位：15 位纯数字，出生日期为 YYMMDD，按 19xx 解析
    if re.fullmatch(r"\d{15}", v):
        return _is_valid_id_card_date("19" + v[6:12])

    return False


# 允许用户核对/修改的字段白名单
VERIFY_FIELDS = ["xs_xm", "xs_xb", "xs_sfzh", "xs_mz"]

# 字段中文标签（前端展示/审查时使用）
FIELD_LABELS: Dict[str, str] = {
    "xs_xm": "姓名",
    "xs_xb": "性别",
    "xs_sfzh": "身份证号",
    "xs_mz": "民族",
}

# 分组定义（对应参考 UI 的分组标题）
FIELD_GROUPS: List[Dict[str, Any]] = [
    {
        "key": "basic",
        "name": "基本信息",
        "fields": [
            {"key": "xs_xm", "label": "姓名", "editable": True, "required": True},
            {"key": "xs_xb", "label": "性别", "editable": True, "required": True},
            {"key": "xs_sfzh", "label": "身份证号", "editable": True, "required": True},
            {"key": "xs_mz", "label": "民族", "editable": True, "required": True},
        ],
    },
]

# 民族选项列表（供前端下拉选择）
NATION_OPTIONS = [
    "汉族", "蒙古族", "回族", "藏族", "维吾尔族", "苗族", "彝族", "壮族", "布依族", "朝鲜族",
    "满族", "侗族", "瑶族", "白族", "土家族", "哈尼族", "哈萨克族", "傣族", "黎族", "傈僳族",
    "佤族", "畲族", "高山族", "拉祜族", "水族", "东乡族", "纳西族", "景颇族", "科尔克孜族", "土族",
    "达斡尔族", "仫佬族", "羌族", "布朗族", "撒拉族", "毛南族", "仡佬族", "锡伯族", "阿昌族", "普米族",
    "塔吉克族", "怒族", "乌孜别克族", "俄罗斯族", "鄂温克族", "德昂族", "保安族", "裕固族", "京族", "塔塔尔族",
    "独龙族", "鄂伦春族", "赫哲族", "门巴族", "珞巴族", "基诺族", "其他"
]


# 性别映射（数据库存储0/1，转换为显示值）
GENDER_MAP = {
    "0": "女",
    "1": "男",
    "女": "女",
    "男": "男",
    0: "女",
    1: "男"
}

# 性别转换（显示值转存储值）
GENDER_TO_DB = {
    "女": "0",
    "男": "1",
    "0": "0",
    "1": "1",
    0: "0",
    1: "1"
}

def _map_gender(value: Any) -> str:
    """将性别值转换为显示值"""
    if value is None:
        return ""
    return GENDER_MAP.get(str(value), str(value))

def _gender_to_db(value: str) -> str:
    """将性别显示值转换为数据库存储值"""
    if value is None:
        return ""
    return GENDER_TO_DB.get(str(value), str(value))


def _get_student_from_payload(payload: Dict[str, Any], db: Session) -> Student:
    """根据 token payload 定位 oa_xs 学生记录"""
    xs_id = payload.get("xs_id")
    xs_xh = payload.get("xs_xh")

    student: Optional[Student] = None
    if xs_id is not None:
        student = db.query(Student).filter(Student.xs_id == xs_id).first()
    if student is None and xs_xh:
        student = db.query(Student).filter(Student.xs_xh == xs_xh).first()

    if student is None:
        raise HTTPException(status_code=404, detail="未找到学生信息")
    return student


def _get_verify_record(db: Session, xs_xh: str) -> Optional[OaXsXxhd]:
    """根据学号查询核对记录"""
    return db.query(OaXsXxhd).filter(OaXsXxhd.xs_xh == xs_xh).first()


def _build_group_rows(
    original: Dict[str, Any],
    record: Optional[OaXsXxhd] = None,
) -> List[Dict[str, Any]]:
    """构建分组行数据（对应参考 UI 的分组 + 行结构）

    核对状态直接读 oa_xs_xxhd 记录：
    - 无记录 -> 未核对，值取学生表当前值
    - 有记录 -> 按 *_status 判定：0-有误已修正 1-无误
    """
    rows: List[Dict[str, Any]] = []
    for group in FIELD_GROUPS:
        g_rows: List[Dict[str, Any]] = []
        for cfg in group["fields"]:
            key = cfg["key"]
            label = cfg.get("label") or FIELD_LABELS.get(key, key)
            editable = bool(cfg.get("editable", False))
            required = bool(cfg.get("required", False))

            orig = original.get(key)
            orig = "" if orig is None else str(orig)

            # 核对状态来自 oa_xs_xxhd 记录
            status_value = getattr(record, f"{key}_status", None) if record else None
            if status_value is None:
                # 无核对记录 -> 未核对
                orig_text = orig
                value = orig
                modified = False
            elif status_value == 0:
                # 有误已修正 -> 值为记录中的修正值
                rec_value = getattr(record, key, None)
                if rec_value is None or rec_value == "":
                    orig_text = orig
                    value = orig
                else:
                    orig_text = orig
                    value = _map_gender(rec_value) if key == "xs_xb" else str(rec_value)
                modified = value != orig_text
            else:
                # 无误 -> 值为学生表当前值
                orig_text = orig
                value = orig
                modified = False

            g_rows.append({
                "key": key,
                "label": label,
                "value": value,
                "original": orig_text,
                "originalText": orig_text,
                "displayText": value,
                "editable": editable,
                "required": required,
                "readonly": not editable,
                "modified": modified,
            })
        rows.append({
            "key": group["key"],
            "name": group["name"],
            "rows": g_rows,
        })
    return rows


def _get_name_options(db: Session, student: Student) -> List[Dict[str, str]]:
    """获取姓名下拉选项

    来源：本班（xs_bj_id 相同）的全部学生，按学号排序。
    学生的原始姓名一定在列表中（若不在则补上）。
    """
    options: List[Dict[str, str]] = []
    try:
        rows = (
            db.query(Student.xs_xm, Student.xs_xh)
            .filter(Student.xs_bj_id == student.xs_bj_id)
            .order_by(Student.xs_xh)
            .all()
        )
        seen = set()
        for xm, xh in rows:
            name = (xm or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            options.append({"name": name, "value": name, "xh": xh or ""})
    except Exception as e:
        logger.warning(f"获取姓名下拉选项失败: {e}")

    # 保证学生自己的原始姓名在选项中
    own_name = (student.xs_xm or "").strip()
    if own_name and own_name not in {o["name"] for o in options}:
        options.insert(0, {"name": own_name, "value": own_name, "xh": student.xs_xh or ""})

    return options


@router.get("/info")
def get_verify_info(
    payload: Dict[str, Any] = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """获取学生基本信息 + 核对状态
    
    - 有核对记录: 已核对过，不能再次修改
    - 无核对记录: 待核对，可以修改
    """
    student = _get_student_from_payload(payload, db)
    xs_xh = student.xs_xh

    # 获取原始数据
    original = {f: getattr(student, f, None) for f in VERIFY_FIELDS}
    # 性别转换为显示值
    original["xs_xb"] = _map_gender(original.get("xs_xb"))

    # 姓名/性别/民族下拉选项
    name_options = _get_name_options(db, student)
    gender_options = [{"text": "男", "value": "1"}, {"text": "女", "value": "0"}]
    nation_options = [{"text": n, "value": n} for n in NATION_OPTIONS]

    # 查询核对记录
    record = _get_verify_record(db, xs_xh)

    # 查询班级层次和专业
    commitment_info: Dict[str, str] = {"level": "", "major": ""}
    bj: Optional[Class] = None
    if student.xs_bj_id:
        bj = db.query(Class).filter(Class.bj_id == student.xs_bj_id).first()
        if bj:
            commitment_info["level"] = bj.bj_cc or ""
            commitment_info["major"] = bj.bj_zy or ""

    if record:
        # 已有核对记录 - 已核对过，不能再次修改
        status = "verified"
        submitted_at = record.addtime.strftime("%Y-%m-%d %H:%M:%S") if record.addtime else ""

        return {
            "success": True,
            "msg": "ok",
            "data": {
                "student_no": student.xs_xh,
                "student_name": student.xs_xm,
                "original": original,
                "field_labels": FIELD_LABELS,
                "groups": _build_group_rows(original, record),
                "name_options": name_options,      # 姓名下拉选项（本班学生）
                "gender_options": gender_options,  # 性别下拉选项
                "nation_options": nation_options,  # 民族下拉选项
                "status": status,  # verified 表示已核对
                "submitted_at": submitted_at,
                "can_edit": False,
                "commitment_info": commitment_info,
            },
        }
    else:
        # 无核对记录 - 待核对
        return {
            "success": True,
            "msg": "ok",
            "data": {
                "student_no": student.xs_xh,
                "student_name": student.xs_xm,
                "original": original,
                "field_labels": FIELD_LABELS,
                "groups": _build_group_rows(original, None),
                "gender_options": gender_options,  # 性别下拉选项
                "nation_options": nation_options,  # 民族下拉选项
                "status": "pending",
                "submitted_at": "",
                "can_edit": True,
                "commitment_info": commitment_info,
            },
        }


class VerifySubmitItem(BaseModel):
    field: str = Field(..., description="字段名，必须在白名单内")
    value: Optional[str] = Field(None, description="修改后的值")


class VerifySubmitRequest(BaseModel):
    changes: List[VerifySubmitItem] = Field(default_factory=list, description="修改项列表；为空表示确认无误")
    commitment_agreed: bool = Field(False, description="是否已阅读并同意学习承诺书")


@router.post("/submit")
def submit_verify_info(
    body: VerifySubmitRequest,
    payload: Dict[str, Any] = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """提交核对结果

    - changes 为空 -> 所有字段确认无误（status=1）
    - changes 非空 -> 对应字段标记为有误（status=0），并提交修正数据
    - commitment_agreed=True -> 记录已同意学习承诺书（xs_cns_status=1）
    - 已核对过的学生不能再次提交
    """
    student = _get_student_from_payload(payload, db)
    xs_xh = student.xs_xh

    # 检查是否已核对过
    existing_record = _get_verify_record(db, xs_xh)
    if existing_record:
        raise HTTPException(status_code=400, detail="您已完成信息核对，不能再次修改")

    # 必须已阅读并同意学习承诺书
    if not body.commitment_agreed:
        raise HTTPException(status_code=400, detail="请先阅读并勾选同意学习承诺书")

    # 当前真实值（提交时的 original）
    original = {f: getattr(student, f, None) for f in VERIFY_FIELDS}
    # 性别用显示值比较，避免 "男" vs "1" 造成误判
    original["xs_xb"] = _map_gender(original.get("xs_xb"))

    # 过滤白名单并去重
    filtered_changes: Dict[str, str] = {}
    for item in body.changes or []:
        if not isinstance(item.field, str):
            continue
        if item.field not in VERIFY_FIELDS:
            raise HTTPException(status_code=400, detail=f"字段 {item.field} 不在允许核对的范围内")
        value = item.value if item.value is not None else ""
        # 身份证号格式校验（后端兜底，防止绕过前端写入脏数据）
        if item.field == "xs_sfzh" and value and not is_valid_id_card(value):
            raise HTTPException(status_code=400, detail="身份证号格式不正确，请核对后重新提交")
        filtered_changes[item.field] = value

    # 构建核对记录（性别需要转换存储值）
    verify_record = OaXsXxhd(
        xs_xh=xs_xh,
        xs_xm=student.xs_xm,
        xs_xb=_gender_to_db(student.xs_xb) if student.xs_xb else student.xs_xb,
        xs_mz=student.xs_mz,
        xs_sfzh=student.xs_sfzh,
        xs_bj_id=student.xs_bj_id,
        addtime=datetime.now(),
        xs_cns_status=1,  # 已同意学习承诺书
    )

    # 处理每个字段的核对状态
    for field in VERIFY_FIELDS:
        status_field = f"{field}_status"
        new_value = filtered_changes.get(field)
        old_value = original.get(field)
        old_str = "" if old_value is None else str(old_value)

        if new_value is not None and new_value != "" and new_value != old_str:
            # 有修改，标记为0（有误已修正）
            setattr(verify_record, status_field, 0)
            # 性别字段需要转换存储值
            if field == "xs_xb":
                setattr(verify_record, field, _gender_to_db(new_value))
            else:
                setattr(verify_record, field, new_value)
        else:
            # 无修改，标记为1（无误）
            setattr(verify_record, status_field, 1)

    try:
        db.add(verify_record)
        
        # 如果有修正数据，同步更新 oa_xs 表
        for field, new_value in filtered_changes.items():
            old_value = original.get(field)
            old_str = "" if old_value is None else str(old_value)
            if new_value and new_value != old_str:
                # 性别字段需要转换存储值
                if field == "xs_xb":
                    setattr(student, field, _gender_to_db(new_value))
                else:
                    setattr(student, field, new_value)
                logger.info(f"信息核对修正: {student.xs_xh}.{field}: {old_str} -> {new_value}")

        db.commit()
        db.refresh(verify_record)
        
        submitted_at = verify_record.addtime.strftime("%Y-%m-%d %H:%M:%S") if verify_record.addtime else ""
        
        # 统计修正的字段数
        modified_count = sum(
            1 for f in VERIFY_FIELDS 
            if getattr(verify_record, f"{f}_status", None) == 0
        )
        
        logger.info(f"新生信息核对完成: xs_xh={xs_xh}, modified_count={modified_count}")
        
        return {
            "success": True,
            "msg": "提交成功",
            "data": {
                "submitted_at": submitted_at,
                "modified_count": modified_count,
            },
        }
    except Exception as e:
        db.rollback()
        logger.exception("提交核对信息失败")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")

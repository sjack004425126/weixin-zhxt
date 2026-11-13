#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
海康威视人脸同步服务（zhpt-new 与 headphoto 统一实现）

功能总览
--------
1. 照片 → 海康：sync_photo_to_hikvision / sync_photo_from_minio / batch_sync
2. 按学生主键同步：sync_by_student_id（前端列表入口，避免传身份证号）
3. 人员注册：sync_students_to_hikvision（组织编码动态查询 + 硬编码兜底）
4. 门禁：grant_access_permission（请假审批通过后下发权限）
5. 返校状态：query_return_status（按 jobNo 匹配学号）
6. 反向拉图：fetch_photo_from_hikvision（海康 → MinIO，配合 client.fetch_photo_for_id_card）

跨项目适配
----------
两个项目的 DB / MinIO 入口路径不同，本文件通过下列适配器抹平差异，
保证两边**代码内容完全一致**：
    - models : app.models.models（headphoto） / models.models（zhpt-new）
    - session: app.core.database.SessionLocal（headphoto） / init.dependencies.get_db_sync（zhpt-new）
    - minio  : app.core.minio_client.gateway（headphoto） / utils.minio_client.gateway（zhpt-new）
"""
import base64
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 跨项目适配层
# ============================================================
def _load_models():
    """返回 (ZzXs, OaXs) 模型类。"""
    try:
        from app.models.models import OaXs, ZzXs  # headphoto
    except ImportError:
        from models.models import Student as OaXs  # zhpt-new: oa_xs
        from models.models import ZzXs
    return ZzXs, OaXs


def _load_leave_model():
    """返回请销假模型（ZzXsQxj）；headphoto 无此模型时返回 None。"""
    try:
        from app.models.models import ZzXsQxj  # type: ignore
        return ZzXsQxj
    except ImportError:
        pass
    try:
        from models.models import ZzXsQxj  # zhpt-new
        return ZzXsQxj
    except ImportError:
        return None


def _session_factory():
    """返回可调用对象 -> Session。"""
    try:
        from app.core.database import SessionLocal  # headphoto
        return SessionLocal
    except ImportError:
        from init.dependencies import get_db_sync  # zhpt-new
        return get_db_sync


def _minio_gateway():
    """返回 MinIO 网关单例。"""
    try:
        from app.core.minio_client import gateway  # headphoto
        return gateway
    except ImportError:
        from utils.minio_client import gateway  # zhpt-new
        return gateway


def _minio_service():
    """返回 minio_service 模块（提供 split_bucket_key / BUCKET_* / _headphoto_key）。"""
    try:
        import app.services.minio_service as ms  # headphoto
    except ImportError:
        import services.minio_service as ms  # zhpt-new
    return ms


def _is_success(result: Dict[str, Any]) -> bool:
    """统一判断业务成功。

    service 层内部返回 ``{"success": True}``；client 层返回 ``{"code": "0"}``。
    """
    if not isinstance(result, dict):
        return False
    if result.get("success") is True:
        return True
    return str(result.get("code")) == "0"


class HikvisionSyncService:
    """海康威视人脸同步服务"""

    def __init__(self):
        # 延迟 import，避免模块加载期就要求 DB / MinIO 可用
        try:
            from app.services.hikvision_client import get_hikvision_client  # headphoto
        except ImportError:
            from services.hikvision_client import get_hikvision_client  # zhpt-new
        self.client = get_hikvision_client()
        self._org_code_cache: Dict[str, str] = {}

    # ============================================================
    # 组织编码
    # ============================================================
    async def get_org_index_code_by_name(self, org_name: str) -> Optional[str]:
        """根据组织名称（如 "2025秋"）查询组织编码，带缓存。"""
        if org_name in self._org_code_cache:
            return self._org_code_cache[org_name]

        try:
            result = await self.client.query_org_list_v2(org_name)
            if result.get("code") == "0":
                list_data = result.get("data", {}).get("list", [])
                if list_data:
                    org_index_code = list_data[0].get("orgIndexCode")
                    if org_index_code:
                        self._org_code_cache[org_name] = org_index_code
                        logger.info(f"找到组织编码: {org_name} -> {org_index_code}")
                        return org_index_code
            logger.warning(f"未找到组织: {org_name}")
            return None
        except Exception as e:
            logger.error(f"查询组织编码异常: {e}")
            return None

    def clear_org_cache(self) -> None:
        """清空组织编码缓存"""
        self._org_code_cache.clear()
        logger.info("组织编码缓存已清空")

    # ============================================================
    # 照片 → 海康
    # ============================================================
    async def sync_photo_to_hikvision(
        self,
        id_card: str,
        photo_data: Any,
        face_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """同步照片到海康威视平台。

        流程：search → 找到人员则 add/update face；找不到则返回失败提示（不自动注册）。

        Args:
            id_card:    身份证号
            photo_data: 照片数据（bytes 或 base64 字符串，统一处理）
            face_id:    人脸ID（如已存在则更新，否则新增）
        """
        if isinstance(photo_data, str):
            photo_data = base64.b64decode(photo_data)
        face_data = base64.b64encode(photo_data).decode("utf-8")

        try:
            if face_id:
                logger.info(f"更新人脸: id_card={id_card}, face_id={face_id}")
                result = await self.client.update_face(face_id, face_data)
            else:
                logger.info(f"根据身份证号查找人员: {id_card}")
                person_result = await self.client.search_person_by_id_card(id_card)

                if _is_success(person_result) and person_result.get("data"):
                    person_data = person_result["data"]
                    person_id = person_data.get("personId")
                    existing_face_id = person_data.get("personPhotoIndexCode")
                    logger.info(f"找到人员: person_id={person_id}, existing_face_id={existing_face_id}")

                    if existing_face_id:
                        logger.info(f"人员已有人脸，更新: person_id={person_id}, face_id={existing_face_id}")
                        result = await self.client.update_face(existing_face_id, face_data)
                    elif person_id:
                        logger.info(f"人员无人脸，新增: person_id={person_id}")
                        result = await self.client.add_face(person_id, face_data)
                    else:
                        result = {"code": "-1", "msg": f"未找到身份证号对应的人员: {id_card}"}
                elif "未找到" in (person_result.get("msg") or "") or person_result.get("code") == "-1":
                    # 人员不在海康平台 → 直接跳过，不自动注册
                    msg = f"人员在海康平台未注册（请先去海康平台添加该学生），id_card={id_card}"
                    logger.warning(f"人员在海康平台未注册: {id_card}，跳过同步")
                    return {"success": False, "message": msg}
                else:
                    result = {"code": "-1", "msg": f"查询人员失败: {person_result.get('msg', '未知错误')}"}

            if _is_success(result):
                logger.info(f"同步成功: id_card={id_card}, data={result.get('data')}")
                return {
                    "success": True,
                    "message": "同步成功",
                    "data": {
                        "id_card": id_card,
                        "face_id": result.get("data", {}).get("faceId"),
                        "face_url": result.get("data", {}).get("faceUrl"),
                    },
                }

            msg = result.get("msg") or result.get("message") or "同步失败"
            logger.warning(f"同步失败: id_card={id_card}, msg={msg}")
            return {"success": False, "message": msg}

        except Exception as e:
            logger.error(f"同步异常: id_card={id_card}, error={e}")
            return {"success": False, "message": f"同步异常: {e}"}

    async def sync_photo_from_minio(
        self,
        id_card: str,
        minio_path: str,
        face_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从 MinIO 获取照片并同步到海康威视。

        Args:
            id_card:    身份证号
            minio_path: MinIO 路径，支持两种格式：
                1. **DB 路径** ``<bucket>/<key>``，如
                   ``guizhou-zhpt-prod-private/headphoto/vocational/<sfzh>.jpg``
                   —— 走 ``split_bucket_key`` 正确解析（含 zhxt 教师头像桶）。
                2. **裸 key** ``headphoto/vocational/<sfzh>.jpg`` 或 ``<sfzh>.jpg``
                   —— 默认拼上私有桶前缀。
            face_id:    人脸ID
        """
        try:
            ms = _minio_service()
            gateway = _minio_gateway()
            client = gateway.client
            if client is None:
                return {"success": False, "message": "MinIO 客户端不可用"}

            p = (minio_path or "").lstrip("/")
            # 格式 1：DB 路径（含桶名前缀）
            if "/" in p and p.split("/", 1)[0] in {
                ms.BUCKET_PRIVATE,
                ms.BUCKET_ZHXT,
                getattr(ms, "BUCKET_PUBLIC", ms.BUCKET_PRIVATE),
            }:
                bucket, key = ms.split_bucket_key(p)
            else:
                # 格式 2：裸 key；默认走私有桶
                bucket = ms.BUCKET_PRIVATE
                key = p

            logger.info(f"从 MinIO 拉取照片: bucket={bucket}, key={key}")
            response = client.get_object(bucket, key)
            try:
                photo_data = response.read()
            finally:
                try:
                    response.close()
                    response.release_conn()
                except Exception:
                    pass

            if not photo_data:
                return {"success": False, "message": f"MinIO 中照片为空: {key}"}

            return await self.sync_photo_to_hikvision(id_card, photo_data, face_id)

        except Exception as e:
            logger.error(f"从 MinIO 同步失败: id_card={id_card}, minio_path={minio_path}, error={e}")
            return {"success": False, "message": f"从 MinIO 同步失败: {e}"}

    async def batch_sync(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量同步照片。

        Args:
            items: 每项包含 id_card, photo_data 或 minio_path, 可选 face_id
        """
        results = {"total": len(items), "success": 0, "failed": 0, "details": []}

        for item in items:
            id_card = item.get("id_card")
            photo_data = item.get("photo_data")
            minio_path = item.get("minio_path")
            face_id = item.get("face_id")

            if photo_data:
                result = await self.sync_photo_to_hikvision(id_card, photo_data, face_id)
            elif minio_path:
                result = await self.sync_photo_from_minio(id_card, minio_path, face_id)
            else:
                result = {"code": "-1", "msg": "缺少照片数据"}

            if _is_success(result):
                results["success"] += 1
            else:
                results["failed"] += 1

            results["details"].append({"id_card": id_card, "result": result})

        return results

    async def sync_by_student_id(
        self,
        student_id: int,
        student_type: str = "zz",
        face_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按学生主键同步照片到海康威视（前端列表入口，避免传身份证号/路径）。

        流程：
            1. 按 student_id + student_type 查学生（拿真实 sfzh）
            2. 按 student_type 选 headphoto 子目录（zz→vocational, oa→open）
            3. 拼 DB 路径 ``<bucket>/headphoto/<subdir>/<sfzh>.jpg``
            4. 委托 ``sync_photo_from_minio`` 拉照片 + 同步到海康
        """
        ZzXs, OaXs = _load_models()
        db = _session_factory()()
        try:
            if student_type == "zz":
                row = db.query(ZzXs).filter(ZzXs.id == student_id).first()
                sfzh = row.sfzh if row else None
            else:
                row = db.query(OaXs).filter(OaXs.xs_id == student_id).first()
                sfzh = row.xs_sfzh if row else None

            if not row:
                return {"success": False, "message": f"未找到学生: type={student_type}, id={student_id}"}
            if not sfzh:
                return {"success": False, "message": f"学生缺少身份证号: id={student_id}"}

            ms = _minio_service()
            subdir = ms.user_type_to_headphoto_subdir(student_type)
            key = ms._headphoto_key(sfzh, subdir)
            db_path = f"{ms.BUCKET_PRIVATE}/{key}"
            logger.info(f"sync_by_student_id: type={student_type}, id={student_id}, sfzh={sfzh}, path={db_path}")
            return await self.sync_photo_from_minio(sfzh, db_path, face_id)
        except Exception as e:
            logger.error(f"sync_by_student_id 异常: type={student_type}, id={student_id}, error={e}")
            return {"success": False, "message": f"同步异常: {e}"}
        finally:
            try:
                db.close()
            except Exception:
                pass

    # ============================================================
    # 人员注册到海康
    # ============================================================
    async def sync_students_to_hikvision(self, students: List[Any]) -> Dict[str, Any]:
        """批量注册人员到海康威视平台（ZzXs 模型实例）。

        组织编码：优先按 ``<年度>春`` / ``<年度>秋`` 动态查询，
        查不到时回退到内置的年级 → 组织编码映射表。

        海康批量接口单次上限 1000 人，自动分批。
        """
        # 内置兜底映射（动态查询失败时使用）
        ORG_INDEX_CODE_FALLBACK = {
            "23": "188f380023554591955ef4bef2c33c2a",
            "24": "3cfbe2586a874ffca70efd4dcca72858",
            "25": "c9635b6a2afc4b8a813ba19588e045d3",
        }
        GENDER_MAP = {"男": 1, "女": 2}
        BATCH_SIZE = 1000

        persons_data: List[Dict[str, Any]] = []
        errors: List[str] = []
        failed_count = 0

        for student in students:
            try:
                year = str(student.nd)
                semester = str(getattr(student, "xqdm", "") or "")

                org_index_code = None
                if semester in ("03", "09"):
                    season = "春" if semester == "03" else "秋"
                    org_index_code = await self.get_org_index_code_by_name(f"{year}{season}")
                if not org_index_code:
                    org_index_code = ORG_INDEX_CODE_FALLBACK.get(year)

                if not org_index_code:
                    errors.append(f"{getattr(student, 'xh', 'unknown')}: 未找到{year}的组织编码")
                    failed_count += 1
                    continue

                person_data = {
                    "personId": student.xh,
                    "personName": student.xm,
                    "orgIndexCode": org_index_code,
                    "gender": GENDER_MAP.get(student.xb, 1),
                    "certificateType": "111",
                    "certificateNo": student.sfzh,
                    "jobNo": student.xh,
                    "personType": "2",
                }
                if getattr(student, "xsdh", None):
                    person_data["phoneNo"] = student.xsdh

                persons_data.append(person_data)
            except Exception as e:
                errors.append(f"{getattr(student, 'xh', 'unknown')}: {e}")
                failed_count += 1

        if not persons_data:
            return {
                "success": False,
                "message": "没有有效的学生数据需要同步",
                "success_count": 0,
                "failed_count": len(students),
                "errors": errors,
            }

        success_count = 0
        batch_results: List[Dict[str, Any]] = []
        total_batches = (len(persons_data) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_idx in range(total_batches):
            start = batch_idx * BATCH_SIZE
            batch = persons_data[start:start + BATCH_SIZE]
            try:
                result = await self.client.batch_add_persons(batch)
                if result.get("code") == "0":
                    success_count += len(batch)
                    batch_results.append({"batch": batch_idx + 1, "success": len(batch), "failed": 0})
                else:
                    err = result.get("msg", "批量添加人员失败")
                    failed_count += len(batch)
                    errors.append(f"批量操作失败(第{batch_idx + 1}批): {err}")
                    batch_results.append({"batch": batch_idx + 1, "success": 0, "failed": len(batch), "error": err})
            except Exception as e:
                failed_count += len(batch)
                errors.append(f"批量操作异常(第{batch_idx + 1}批): {e}")
                batch_results.append({"batch": batch_idx + 1, "success": 0, "failed": len(batch), "error": str(e)})

        return {
            "success": failed_count == 0,
            "message": f"同步完成：成功{success_count}人，失败{failed_count}人（分{total_batches}批）",
            "success_count": success_count,
            "failed_count": failed_count,
            "total_batches": total_batches,
            "batch_results": batch_results,
            "errors": errors[:50],
        }

    # ============================================================
    # 门禁
    # ============================================================
    async def grant_access_permission(self, student_no: str) -> Dict[str, Any]:
        """为学生下发门禁权限（请假审批通过时调用）。

        时间范围取该学生**最近一条请销假记录**的请假起止时间。
        """
        ZzXs, _ = _load_models()
        LeaveModel = _load_leave_model()

        try:
            db = _session_factory()()
            try:
                student = db.query(ZzXs).filter(ZzXs.xh == student_no).first()
                if not student:
                    logger.warning(f"未找到学号为 {student_no} 的学生")
                    return {
                        "success": False,
                        "message": f"未找到学号为 {student_no} 的学生",
                        "student_no": student_no,
                    }

                # 学生是否已在海康平台注册
                person_search = await self.client.search_person_by_id_card(student.sfzh)
                if person_search.get("code") != "0" or not person_search.get("data"):
                    logger.warning(f"学生 {student.xm}({student.xh}) 未在海康平台注册，无法下发门禁权限")
                    return {
                        "success": False,
                        "message": f"学生 {student.xm}({student.xh}) 未在海康平台注册，无法下发门禁权限",
                        "student_no": student_no,
                        "student_name": student.xm,
                    }

                person_id = person_search["data"]["personId"]

                if LeaveModel is None:
                    logger.warning("当前项目未配置请销假模型，无法计算门禁权限时间范围")
                    return {
                        "success": False,
                        "message": "当前环境缺少请销假数据，无法下发门禁权限",
                        "student_no": student_no,
                        "student_name": student.xm,
                    }

                leave_record = (
                    db.query(LeaveModel)
                    .filter(LeaveModel.xh == student_no)
                    .order_by(LeaveModel.qjsqsj.desc())
                    .first()
                )
                if not leave_record:
                    logger.warning(f"未找到学生 {student.xm}({student.xh}) 的有效请假记录")
                    return {
                        "success": False,
                        "message": f"未找到学生 {student.xm}({student.xh}) 的有效请假记录",
                        "student_no": student_no,
                        "student_name": student.xm,
                    }

                start_time = (
                    leave_record.qjkssj.strftime("%Y-%m-%d %H:%M:%S") if leave_record.qjkssj else None
                )
                end_time = (
                    leave_record.qjjssj.strftime("%Y-%m-%d %H:%M:%S") if leave_record.qjjssj else None
                )
                if not start_time or not end_time:
                    logger.warning(f"学生 {student.xm}({student.xh}) 的请假时间不完整")
                    return {
                        "success": False,
                        "message": f"学生 {student.xm}({student.xh}) 的请假时间不完整",
                        "student_no": student_no,
                        "student_name": student.xm,
                    }

                logger.info(
                    f"为学生 {student.xm}({student.xh}) 下发门禁权限，时间段：{start_time} - {end_time}"
                )

                response = await self.client.grant_access_permission(
                    scene_id_list=[1],
                    device_id_list=[
                        "bba434994d2a4218b7b81f9a3bbf552d",
                        "cab02002a6cb465e91284e746af34971",
                    ],
                    person_id_list=[student_no],
                    start_time=start_time,
                    end_time=end_time,
                )

                if response.get("success"):
                    hik_data = response.get("data", {})
                    hik_raw = hik_data.get("data", []) if isinstance(hik_data, dict) else []
                    hik_task_id = hik_raw[0] if isinstance(hik_raw, list) and hik_raw else None
                    logger.info(
                        f"为学生 {student.xm}({student.xh}) 下发门禁权限成功, task_id={hik_task_id}"
                    )
                    return {
                        "success": True,
                        "message": f"学生 {student.xm}({student.xh}) 门禁权限下发成功",
                        "student_no": student_no,
                        "student_name": student.xm,
                        "person_id": person_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "hik_task_id": hik_task_id,
                    }

                logger.warning(
                    f"为学生 {student.xm}({student.xh}) 下发门禁权限失败: {response.get('message')}"
                )
                return {
                    "success": False,
                    "message": response.get("message", "门禁权限下发失败"),
                    "student_no": student_no,
                    "student_name": student.xm,
                }
            finally:
                db.close()

        except Exception as e:
            logger.error(f"为学生 {student_no} 下发门禁权限失败: {e}")
            return {
                "success": False,
                "message": f"为学生 {student_no} 下发门禁权限失败: {e}",
                "student_no": student_no,
            }

    async def query_return_status(self, student_no: str) -> Dict[str, Any]:
        """查询学生返校状态（上一周内的门禁记录）。

        以姓名模糊查询门禁事件，再用返回记录里的 jobNo 与学号比对确认身份。
        """
        ZzXs, _ = _load_models()
        try:
            db = _session_factory()()
            try:
                student = db.query(ZzXs).filter(ZzXs.xh == student_no).first()
            finally:
                db.close()

            if not student:
                logger.warning(f"未找到学号为 {student_no} 的学生")
                return {
                    "success": False,
                    "message": f"未找到学号为 {student_no} 的学生",
                    "return_status": "未知",
                }

            person_search = await self.client.search_person_by_id_card(student.sfzh)
            if person_search.get("code") != "0" or not person_search.get("data"):
                logger.warning(f"学生 {student.xm}({student.xh}) 未在海康平台注册，无法查询返校状态")
                return {
                    "success": False,
                    "message": f"学生 {student.xm}({student.xh}) 未在海康平台注册，无法查询返校状态",
                    "return_status": "未注册",
                }

            person_id = person_search["data"]["personId"]

            # 查询范围：上一周的周一 00:00:00 ~ 上周周日 23:59:59
            now = datetime.now()
            this_monday = (now - timedelta(days=now.weekday())).date()
            last_monday = this_monday - timedelta(days=7)
            last_sunday = last_monday + timedelta(days=6)
            start_time = datetime(
                last_monday.year, last_monday.month, last_monday.day, 0, 0, 0
            ).strftime("%Y-%m-%d %H:%M:%S")
            end_time = datetime(
                last_sunday.year, last_sunday.month, last_sunday.day, 23, 59, 59
            ).strftime("%Y-%m-%d %H:%M:%S")

            logger.info(
                f"为学生 {student.xm}({student.xh}) 查询返校状态，时间范围：{start_time} - {end_time}"
            )

            event_result = await self.client.query_access_events(
                person_name=student.xm,
                start_time=start_time,
                end_time=end_time,
                page_no=1,
                page_size=50,
                door_index_codes=[
                    "61e225df81204a34b5933eebe89649fb",
                    "6d3166d19da84887a8333cfcf973a23f",
                ],
            )

            if not event_result.get("success"):
                return {
                    "success": False,
                    "message": f"为学生 {student.xm}({student.xh}) 查询返校状态失败: {event_result.get('message')}",
                    "return_status": "查询失败",
                }

            events = event_result.get("data", {}).get("data", {}).get("list", []) or []

            matched_event = None
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                jobno = ev.get("jobNo")
                if jobno and str(jobno).strip() == str(student.xh):
                    matched_event = ev
                    break

            if matched_event:
                return {
                    "success": True,
                    "message": f"学生 {student.xm}({student.xh}) 已返校",
                    "return_status": "已返校",
                    "last_event_time": matched_event.get("eventTime", ""),
                    "person_id": person_id,
                }

            logger.info(
                f"门禁查询结果存在但未找到学号匹配的记录: student={student.xh}, returned_count={len(events)}"
            )
            return {
                "success": True,
                "message": f"学生 {student.xm}({student.xh}) 未返校（未找到匹配学号的门禁记录）",
                "return_status": "未返校",
                "person_id": person_id,
            }

        except Exception as e:
            logger.error(f"为学生 {student_no} 查询返校状态失败: {e}")
            return {
                "success": False,
                "message": f"为学生 {student_no} 查询返校状态失败: {e}",
                "return_status": "查询异常",
            }

    # ============================================================
    # 反向拉图：海康 → MinIO
    # ============================================================
    async def fetch_photo_from_hikvision(self, sfzh: str) -> Optional[bytes]:
        """从海康平台拉取某身份证号对应的照片二进制（不走 MinIO）。

        内部使用 client.fetch_photo_for_id_card 的三级兜底策略。
        """
        try:
            return await self.client.fetch_photo_for_id_card(sfzh)
        except Exception as e:
            logger.error(f"从海康拉取照片失败: sfzh={sfzh}, error={e}")
            return None


# 全局服务实例
_sync_service: Optional[HikvisionSyncService] = None


def get_hikvision_sync_service() -> HikvisionSyncService:
    """获取海康威视同步服务单例"""
    global _sync_service
    if _sync_service is None:
        _sync_service = HikvisionSyncService()
    return _sync_service

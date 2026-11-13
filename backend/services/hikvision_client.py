#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
海康威视开放平台 API 客户端（AK/SK 签名）

本文件是 zhpt-new 与 headphoto 两个项目的**统一实现**，内容完全一致：
- 签名算法：HMAC-SHA256（海康 Artemis 标准签名串）
- 人员管理：add/update/delete face、person 单条/批量增改、查询
- 反向拉图：extract_person_picture（302 重定向）/ fetch_photo_for_id_card（三级兜底）
- 门禁：grant_access_permission（权限下发）、query_access_events（通行事件）

配置来源：环境变量 HIKVISION_HOST / HIKVISION_APP_KEY / HIKVISION_APP_SECRET
（启动时自动加载 backend/.env，两个项目都支持）
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# 默认海康平台地址（内网）
DEFAULT_HIKVISION_HOST = "https://192.168.1.152:443"


def _load_dotenv_quiet() -> None:
    """静默加载 backend/.env。

    - headphoto 用 pydantic-settings 读 .env，值不会进 os.environ，
      所以这里必须自己 load 一次，两边才能共用同一份取值逻辑。
    - override=False：进程里已显式注入的环境变量优先，便于运维覆盖。
    - 向上逐级找 .env，兼容两种目录布局：
        zhpt-new : backend/services/hikvision_client.py → backend/.env
        headphoto: backend/app/services/hikvision_client.py → backend/.env
    """
    try:
        from dotenv import load_dotenv  # python-dotenv
    except ImportError:
        return

    for parent in Path(__file__).resolve().parents:
        env_path = parent / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            logger.debug(f"已加载环境变量文件: {env_path}")
            return
    logger.debug("未找到 .env 文件，海康配置将完全依赖进程环境变量")


_load_dotenv_quiet()


class HikvisionClient:
    """海康威视 API 客户端"""

    def __init__(
        self,
        host: Optional[str] = None,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Args:
            host: 平台地址，如 https://192.168.1.152:443
            app_key: 应用 Key
            app_secret: 应用 Secret
            timeout: 请求超时时间（秒）
        """
        self.host = (host or os.getenv("HIKVISION_HOST") or DEFAULT_HIKVISION_HOST).strip()
        self.app_key = (app_key or os.getenv("HIKVISION_APP_KEY") or "").strip()
        self.app_secret = (app_secret or os.getenv("HIKVISION_APP_SECRET") or "").strip()
        self.timeout = timeout

        # 确保 host 以 http(s) 开头
        if not self.host.startswith("http"):
            self.host = f"https://{self.host}"

        # 移除末尾斜杠
        self.host = self.host.rstrip("/")

        logger.info(f"海康威视客户端初始化: host={self.host}, app_key={self.app_key or '(未配置)'}")

    # ==========================================================
    # 签名与请求
    # ==========================================================
    def _generate_signature(self, path: str, headers: Dict[str, str]) -> str:
        """生成 AK/SK 签名。

        海康签名算法（官方 Python 示例）：
        签名字符串格式：
            POST\\n*/*\\napplication/json\\nx-ca-key:{appKey}
            \\nx-ca-nonce:{nonce}\\nx-ca-timestamp:{timestamp}\\n{path}
        """
        sign_str = (
            "POST\n*/*\napplication/json"
            + "\nx-ca-key:" + headers["x-ca-key"]
            + "\nx-ca-nonce:" + headers["x-ca-nonce"]
            + "\nx-ca-timestamp:" + headers["x-ca-timestamp"]
            + "\n" + path
        )

        logger.debug(f"签名字符串: {repr(sign_str)}")

        signature = hmac.new(
            self.app_secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        return base64.b64encode(signature).decode("utf-8")

    def _build_headers(self, path: str) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "x-ca-key": self.app_key,
            "x-ca-nonce": str(uuid.uuid4()),
            "x-ca-timestamp": str(int(time.time() * 1000)),
        }

        signature = self._generate_signature(path, headers)
        headers["x-ca-signature"] = signature
        headers["x-ca-signature-headers"] = "x-ca-key,x-ca-nonce,x-ca-timestamp"

        return headers

    async def request(
        self,
        path: str,
        data: Optional[Any] = None,
        method: str = "POST",
    ) -> Any:
        """发送 API 请求。

        Args:
            path: API 路径，如 /artemis/api/resource/v1/face/single/update
            data: 请求体（dict 或 list）
            method: 请求方法

        Returns:
            API 响应（dict）
        """
        body = json.dumps(data, ensure_ascii=False) if data is not None else None
        headers = self._build_headers(path)
        url = f"{self.host}{path}"

        safe_headers = {k: (v if k != "x-ca-signature" else "***") for k, v in headers.items()}
        logger.info(f"海康API请求: {method} {url}\n  Headers: {safe_headers}\n  Body: {body}")

        async with httpx.AsyncClient(verify=False, timeout=self.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
            )

            logger.info(f"海康API响应状态: {response.status_code}")

            result = response.json()
            logger.debug(f"响应数据: {result}")

            return result

    # ==========================================================
    # 反向拉图：海康 → 本地
    # ==========================================================
    async def extract_person_picture(
        self,
        server_index_code: str,
        pic_uri: str,
    ) -> Optional[bytes]:
        """提取人员图片（"下载人脸图"接口）。

        接口：POST /artemis/api/resource/v1/person/picture
        入参：{"serverIndexCode": "...", "picUri": "/pic?..."}
        返回：**HTTP 302 重定向**，`Location` 头指向带签名的图片 URL（有时效）。

        本方法先取 302 的 Location，再单独 GET 下载图片；
        若最终响应是 JSON（说明失败），返回 None。
        """
        path = "/artemis/api/resource/v1/person/picture"
        body = json.dumps({
            "serverIndexCode": server_index_code,
            "picUri": pic_uri,
        })
        headers = self._build_headers(path)
        url = f"{self.host}{path}"

        safe_headers = {k: v for k, v in headers.items() if k != "x-ca-signature"}
        logger.info(
            f"extract_person_picture 请求:\n  URL: {url}\n"
            f"  Headers: {safe_headers}\n  Body: {body}"
        )

        async with httpx.AsyncClient(
            verify=False, timeout=self.timeout, follow_redirects=False
        ) as client_step1:
            resp_step1 = await client_step1.post(url, headers=headers, content=body)

        logger.info(
            f"extract_person_picture Step1 响应: status={resp_step1.status_code}, "
            f"headers={ {k: v for k, v in resp_step1.headers.items()} }"
        )

        if resp_step1.status_code == 302:
            location = resp_step1.headers.get("Location") or resp_step1.headers.get("location")
            logger.info(f"  -> Location: {location}")

            if not location:
                return None

            img_url = location if location.startswith("http") else f"{self.host}{location}"
            logger.info(f"  -> 下载图片 URL: {img_url[:150]}")

            async with httpx.AsyncClient(
                verify=False, timeout=self.timeout, follow_redirects=True
            ) as client_img:
                img_resp = await client_img.get(img_url)

            logger.info(
                f"  -> 图片响应: status={img_resp.status_code}, "
                f"content-type={img_resp.headers.get('Content-Type', '')}, "
                f"bytes={len(img_resp.content)}"
            )
            if img_resp.status_code == 200 and img_resp.content:
                ctype = img_resp.headers.get("Content-Type", "")
                if "image" in ctype.lower():
                    return img_resp.content
                logger.warning(f"  -> 非图片内容: {img_resp.content[:200]!r}")
                return None
            return None

        if resp_step1.status_code == 200:
            ctype = resp_step1.headers.get("Content-Type", "")
            logger.info(
                f"  -> 直接返回图片: content-type={ctype}, bytes={len(resp_step1.content)}"
            )
            if "image" in ctype.lower():
                return resp_step1.content
            logger.warning(f"  -> 直接返回非图片: {resp_step1.content[:200]!r}")
            return None

        logger.warning(
            f"extract_person_picture Step1 失败: status={resp_step1.status_code}, "
            f"body={resp_step1.content[:300]!r}"
        )
        return None

    async def fetch_photo_for_id_card(self, sfzh: str) -> Optional[bytes]:
        """根据身份证号从海康威视平台拉取照片二进制（jpg/png）。

        策略（按优先级逐级尝试）：
            1) extract_person_picture(serverIndexCode, picUri) —— "提取人员图片"接口
               POST /artemis/api/resource/v1/person/picture，服务端 302 重定向到
               带签名的图片地址，本方法自动 follow。（推荐，官方接口）
            2) get_face_by_id 返回的 faceData（base64 内联，免一次 HTTP）
            3) personList.personPhoto[].faceUrl（部分版本含完整 URL）

        返回 None 表示未找到人员 / 未上传照片 / 接口失败。
        """
        path = "/artemis/api/resource/v2/person/advance/personList"
        data = {"pageNo": 1, "pageSize": 10, "certificateNo": sfzh}
        result = await self.request(path, data)

        code = result.get("code")
        if str(code) != "0":
            logger.warning(f"海康查询失败: code={code}, msg={result.get('msg')}, sfzh={sfzh}")
            return None

        persons = result.get("data", {}).get("list", [])
        if not persons:
            logger.info(f"海康平台未找到身份证号 {sfzh} 对应的人员")
            return None

        person = persons[0]
        person_name = person.get("personName")
        person_id = person.get("personId")
        pp = person.get("personPhoto")
        logger.info(f"海康平台人员: personName={person_name}, personId={person_id}, sfzh={sfzh}")

        face_id = pic_uri = server_index_code = face_url_from_pp = None
        if isinstance(pp, list) and pp:
            p0 = pp[0]
            face_id = p0.get("personPhotoIndexCode")
            pic_uri = p0.get("picUri")
            server_index_code = p0.get("serverIndexCode")
            face_url_from_pp = p0.get("faceUrl")
        elif isinstance(pp, dict):
            face_id = pp.get("personPhotoIndexCode")
            pic_uri = pp.get("picUri")
            server_index_code = pp.get("serverIndexCode")
            face_url_from_pp = pp.get("faceUrl")

        if not face_id and not pic_uri and not face_url_from_pp:
            logger.info(f"该学生在海康平台未上传照片: sfzh={sfzh}")
            return None

        # 策略 1：extract_person_picture（官方推荐）
        if pic_uri and server_index_code:
            try:
                img = await self.extract_person_picture(server_index_code, pic_uri)
                if img:
                    logger.info(f"通过 extract_person_picture 拿到图片: {len(img)} bytes, sfzh={sfzh}")
                    return img
                logger.info(f"extract_person_picture 返回空，继续尝试: sfzh={sfzh}")
            except Exception as e:
                logger.warning(f"extract_person_picture 异常: {e}, sfzh={sfzh}")

        # 策略 2：get_face_by_id 的 faceData / faceUrl
        if face_id:
            try:
                face_resp = await self.get_face_by_id(face_id)
                if str(face_resp.get("code")) == "0":
                    face_data = face_resp.get("data", {}) or {}
                    face_b64 = face_data.get("faceData")
                    face_url = face_data.get("faceUrl")
                    if face_b64:
                        img = base64.b64decode(face_b64)
                        logger.info(f"通过 faceData 解码图片: {len(img)} bytes, sfzh={sfzh}")
                        return img
                    if face_url:
                        full_url = face_url if face_url.startswith("http") else f"{self.host}{face_url}"
                        async with httpx.AsyncClient(
                            verify=False, timeout=30, follow_redirects=True
                        ) as cli:
                            r = await cli.get(full_url)
                        if (
                            r.status_code == 200
                            and r.content
                            and "image" in r.headers.get("Content-Type", "").lower()
                        ):
                            logger.info(f"通过 get_face.faceUrl 下载图片: {len(r.content)} bytes, sfzh={sfzh}")
                            return r.content
                else:
                    logger.info(
                        f"get_face_by_id 失败: code={face_resp.get('code')}, "
                        f"msg={face_resp.get('msg')}, sfzh={sfzh}"
                    )
            except Exception as e:
                logger.warning(f"get_face_by_id 异常: {e}, sfzh={sfzh}")

        # 策略 3：personList.faceUrl
        if face_url_from_pp:
            full_url = face_url_from_pp if face_url_from_pp.startswith("http") else f"{self.host}{face_url_from_pp}"
            try:
                async with httpx.AsyncClient(
                    verify=False, timeout=30, follow_redirects=True
                ) as cli:
                    r = await cli.get(full_url)
                if (
                    r.status_code == 200
                    and r.content
                    and "image" in r.headers.get("Content-Type", "").lower()
                ):
                    logger.info(f"通过 personList.faceUrl 下载图片: {len(r.content)} bytes, sfzh={sfzh}")
                    return r.content
            except Exception as e:
                logger.warning(f"personList.faceUrl 异常: {e}, sfzh={sfzh}")

        logger.warning(f"所有下载方式均失败: sfzh={sfzh}")
        return None

    # ==========================================================
    # 人脸管理
    # ==========================================================
    async def update_face(self, face_id: str, face_data: str) -> Dict[str, Any]:
        """修改人脸。

        Args:
            face_id: 人脸ID
            face_data: 人脸图片 base64 编码
        """
        path = "/artemis/api/resource/v1/face/single/update"
        data = {"faceId": face_id, "faceData": face_data}
        logger.info(f"修改人脸: face_id={face_id}")
        logger.debug(f"人脸数据长度: {len(face_data) if face_data else 0}")
        result = await self.request(path, data)
        logger.info(f"修改人脸响应: code={result.get('code')}, msg={result.get('msg')}")
        return result

    async def add_face(self, person_id: str, face_data: str) -> Dict[str, Any]:
        """添加人脸。

        注意：需要在海康平台的 API 订阅中配置 tagId 参数。

        Args:
            person_id: 人员ID
            face_data: 人脸图片 base64 编码
        """
        path = "/artemis/api/resource/v1/face/single/add"
        data = {"personId": person_id, "faceData": face_data}
        logger.info(f"添加人脸: person_id={person_id}")
        logger.debug(f"人脸数据长度: {len(face_data) if face_data else 0}")
        result = await self.request(path, data)
        logger.info(f"添加人脸响应: code={result.get('code')}, msg={result.get('msg')}")
        return result

    async def delete_face(self, face_id: str) -> Dict[str, Any]:
        """删除人脸。"""
        path = "/artemis/api/resource/v1/face/single/delete"
        data = {"faceId": face_id}
        return await self.request(path, data)

    async def get_face_by_id(self, face_id: str) -> Dict[str, Any]:
        """根据 faceId 获取人脸图片信息。

        POST /artemis/api/resource/v1/face/single/get
        入参：{"faceId": "xxx"}
        成功返回 data 中包含 faceId / faceData（base64）/ faceUrl 等字段。
        """
        path = "/artemis/api/resource/v1/face/single/get"
        data = {"faceId": face_id}
        result = await self.request(path, data)
        logger.info(
            f"get_face_by_id 返回: face_id={face_id}, "
            f"code={result.get('code')}, "
            f"has_faceData={bool(result.get('data', {}).get('faceData'))}"
        )
        return result

    # ==========================================================
    # 人员管理
    # ==========================================================
    async def get_person_list(
        self,
        page_no: int = 1,
        page_size: int = 100,
        org_index_codes: Optional[list] = None,
    ) -> Dict[str, Any]:
        """获取人员列表。"""
        path = "/artemis/api/resource/v2/person/personList"
        data = {"pageNo": page_no, "pageSize": page_size}
        if org_index_codes:
            data["orgIndexCodes"] = org_index_codes
        return await self.request(path, data)

    async def search_person_by_id_card(self, id_card: str) -> Dict[str, Any]:
        """根据身份证号搜索人员（查询人员列表 v2 接口）。

        返回统一格式：{"code": "0"/"-1", "msg": ..., "data": {
            "personId", "personName", "personPhotoIndexCode"}}
        """
        path = "/artemis/api/resource/v2/person/advance/personList"
        data = {"pageNo": 1, "pageSize": 10, "certificateNo": id_card}
        result = await self.request(path, data)

        logger.info(
            f"查询人员列表v2结果: code={result.get('code')}, "
            f"total={result.get('data', {}).get('total', 0)}"
        )

        try:
            if result.get("code") == "0" and result.get("data", {}).get("list"):
                person = result["data"]["list"][0]
                person_photo = person.get("personPhoto")
                face_id = None

                # personPhoto 可能是数组或对象
                if isinstance(person_photo, list) and len(person_photo) > 0:
                    face_id = person_photo[0].get("personPhotoIndexCode")
                elif isinstance(person_photo, dict):
                    face_id = person_photo.get("personPhotoIndexCode")

                logger.info(
                    f"找到人员: personId={person.get('personId')}, "
                    f"personName={person.get('personName')}, faceId={face_id}"
                )

                return {
                    "code": "0",
                    "msg": "success",
                    "data": {
                        "personId": person.get("personId"),
                        "personName": person.get("personName"),
                        "personPhotoIndexCode": face_id,
                    },
                }
            if result.get("code") == "0":
                return {"code": "-1", "msg": f"未找到身份证号对应的人员: {id_card}"}
            return {"code": "-1", "msg": result.get("msg", "查询人员失败")}
        except Exception as e:
            logger.error(f"解析人员数据异常: {e}, result={result}")
            return {"code": "-1", "msg": f"解析人员数据异常: {str(e)}"}

    async def search_persons_by_ids(self, person_ids: str) -> Dict[str, Any]:
        """根据人员ID列表搜索人员。

        Args:
            person_ids: 人员ID列表，逗号分隔的字符串（如 "2025001,2025002"）
        """
        path = "/artemis/api/resource/v2/person/advance/personList"
        data = {"pageNo": 1, "pageSize": 1000, "personIds": person_ids}
        logger.info(f"查询人员列表v2: personIds={person_ids}")
        result = await self.request(path, data)

        logger.info(f"查询人员列表v2响应: code={result.get('code')}, msg={result.get('msg')}")

        try:
            if result.get("code") == "0":
                list_data = result.get("data", {}).get("list", [])
                persons = []
                for person in list_data:
                    person_photo = person.get("personPhoto")
                    face_id = None

                    if isinstance(person_photo, list) and len(person_photo) > 0:
                        face_id = person_photo[0].get("personPhotoIndexCode")
                    elif isinstance(person_photo, dict):
                        face_id = person_photo.get("personPhotoIndexCode")

                    persons.append({
                        "personId": person.get("personId"),
                        "personName": person.get("personName"),
                        "orgIndexCode": person.get("orgIndexCode"),
                        "gender": person.get("gender"),
                        "phoneNo": person.get("phoneNo"),
                        "certificateNo": person.get("certificateNo"),
                        "personType": person.get("personType"),
                        "faceId": face_id,
                        "personPhoto": person_photo,
                    })

                logger.info(f"找到 {len(persons)} 个匹配的人员")
                return {"code": "0", "msg": "success", "data": {"total": len(persons), "list": persons}}

            logger.error(f"查询人员列表失败: {result.get('msg')}")
            return {"code": "-1", "msg": result.get("msg", "查询人员列表失败")}
        except Exception as e:
            logger.error(f"解析人员列表数据异常: {e}, result={result}")
            return {"code": "-1", "msg": f"解析人员列表数据异常: {str(e)}"}

    async def add_person_single(self, person_data: Dict[str, Any]) -> Dict[str, Any]:
        """单条添加人员（v2 接口）。

        POST /artemis/api/resource/v2/person/single/add
        常见字段：
            personId        str   人员编号（学号）
            personName      str   姓名
            orgIndexCode    str   组织编号
            gender          int   性别 1-男 2-女
            phoneNo         str   手机号
            certificateType str   证件类型（111=居民身份证）
            certificateNo   str   证件号
            jobNo           str   工号/学号
            personType      str   人员类型（2=学生）
        """
        path = "/artemis/api/resource/v2/person/single/add"

        # 校验必需字段
        if not person_data.get("personId"):
            raise ValueError("人员ID(personId)不能为空")
        if not person_data.get("personName"):
            raise ValueError("人员姓名(personName)不能为空")
        if not person_data.get("orgIndexCode"):
            raise ValueError("组织编码(orgIndexCode)不能为空")
        if not person_data.get("certificateNo"):
            raise ValueError("证件号(certificateNo)不能为空")

        data = {
            "personId": person_data["personId"],
            "personName": person_data["personName"],
            "orgIndexCode": person_data["orgIndexCode"],
            "gender": person_data.get("gender", 1),
            "certificateType": person_data.get("certificateType", "111"),
            "certificateNo": person_data["certificateNo"],
        }

        for opt in ("phoneNo", "jobNo", "personType", "personPhoto"):
            if person_data.get(opt):
                data[opt] = person_data[opt]

        logger.info(f"单个添加人员: personId={data['personId']}, personName={data['personName']}")
        logger.debug(f"单个添加人员数据: {data}")

        result = await self.request(path, data)
        logger.info(f"单个添加人员响应: code={result.get('code')}, msg={result.get('msg')}")
        return result

    async def batch_add_persons(self, persons_data: list) -> Dict[str, Any]:
        """批量添加人员。

        POST /artemis/api/resource/v1/person/batch/add
        海康批量接口单次上限 1000 人，调用方需自行分批。

        每条 persons_data 需包含：
            personId / personName / orgIndexCode / certificateNo
        可选：gender / certificateType / phoneNo / jobNo / personType / personPhoto
        """
        path = "/artemis/api/resource/v1/person/batch/add"

        data = []
        for person in persons_data:
            if not person.get("personId"):
                raise ValueError("人员ID(personId)不能为空")
            if not person.get("personName"):
                raise ValueError("人员姓名(personName)不能为空")
            if not person.get("orgIndexCode"):
                raise ValueError("组织编码(orgIndexCode)不能为空")
            if not person.get("certificateNo"):
                raise ValueError("证件号(certificateNo)不能为空")

            person_data = {
                "personId": person["personId"],
                "personName": person["personName"],
                "orgIndexCode": person["orgIndexCode"],
                "gender": person.get("gender", 1),
                "certificateType": person.get("certificateType", "111"),
                "certificateNo": person["certificateNo"],
            }

            for opt in ("phoneNo", "jobNo", "personType", "personPhoto"):
                if person.get(opt):
                    person_data[opt] = person[opt]

            data.append(person_data)

        logger.info(f"批量添加人员: {len(data)} 人")
        logger.debug(f"批量添加人员数据: {data}")

        result = await self.request(path, data)
        logger.info(f"批量添加人员响应: code={result.get('code')}, msg={result.get('msg')}")
        return result

    async def update_person(self, person_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新人员信息。

        POST /artemis/api/resource/v2/person/single/update
        必填：personId、orgIndexCode
        """
        path = "/artemis/api/resource/v2/person/single/update"
        result = await self.request(path, person_data)
        logger.info(f"update_person 返回: code={result.get('code')}, msg={result.get('msg')}")
        return result

    async def query_org_list_v2(
        self,
        org_name: str,
        page_no: int = 1,
        page_size: int = 1000,
    ) -> Dict[str, Any]:
        """查询组织列表 v2。

        POST /artemis/api/resource/v2/org/advance/orgList
        入参：{"orgName": "2025秋", "pageNo": 1, "pageSize": 1000}
        """
        path = "/artemis/api/resource/v2/org/advance/orgList"
        data = {"orgName": org_name or "", "pageNo": page_no, "pageSize": page_size}
        logger.info(f"查询组织列表v2: orgName={org_name}, pageNo={page_no}, pageSize={page_size}")
        result = await self.request(path, data, method="POST")
        logger.info(f"查询组织列表v2响应: code={result.get('code')}, msg={result.get('msg')}")
        return result

    async def get_default_org_index_code(self) -> str:
        """获取根组织编号（用于人员注册时绑定组织）。

        结果缓存到 ``self._default_org_index_code``，避免重复调用。
        """
        if hasattr(self, "_default_org_index_code"):
            return self._default_org_index_code

        path = "/artemis/api/resource/v2/org/advance/orgList"
        result = await self.request(path, {"pageNo": 1, "pageSize": 10})
        org_list = result.get("data", {}).get("list", [])
        if org_list:
            self._default_org_index_code = org_list[0].get("orgIndexCode", "root000000")
        else:
            self._default_org_index_code = "root000000"
        logger.info(f"默认组织编号: {self._default_org_index_code}")
        return self._default_org_index_code

    # ==========================================================
    # 门禁
    # ==========================================================
    async def grant_access_permission(
        self,
        scene_id_list: List[int],
        device_id_list: List[str],
        person_id_list: List[str],
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        """下发门禁权限。

        POST /artemis/api/v1/privilege/issue

        Args:
            scene_id_list: 场景ID列表
            device_id_list: 设备ID列表（门禁点）
            person_id_list: 人员ID列表（学号）
            start_time: 权限开始时间
            end_time: 权限结束时间

        Returns:
            {"success": bool, "message": str, "data": 原始响应}
        """
        try:
            permission_data = {
                "sceneIdList": scene_id_list,
                "deviceIdList": device_id_list,
                "personIdList": person_id_list,
                "startTime": start_time,
                "endTime": end_time,
            }

            logger.info(f"下发门禁权限: {permission_data}")

            result = await self.request("/artemis/api/v1/privilege/issue", data=permission_data, method="POST")

            if str(result.get("code")) == "0":
                logger.info("门禁权限下发成功")
                return {"success": True, "message": "门禁权限下发成功", "data": result}

            logger.warning(f"门禁权限下发失败: {result}")
            return {
                "success": False,
                "message": f"门禁权限下发失败: {result.get('msg', '未知错误')}",
                "data": result,
            }
        except Exception as e:
            logger.error(f"门禁权限下发异常: {str(e)}")
            return {"success": False, "message": f"门禁权限下发异常: {str(e)}"}

    async def query_access_events(
        self,
        person_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page_no: int = 1,
        page_size: int = 20,
        door_index_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """查询门禁事件（返校状态查询）。

        POST /artemis/api/acs/v2/door/events

        Args:
            person_name: 人员姓名（模糊）
            start_time: 开始时间（"YYYY-MM-DD HH:MM:SS" 或 ISO8601）
            end_time: 结束时间
            page_no: 页码
            page_size: 每页数量
            door_index_codes: 门禁点编码列表

        Returns:
            {"success": bool, "message": str, "data": 原始响应}
        """
        try:
            # 统一转成海康要求的 ISO8601（北京时间）
            if start_time and not start_time.endswith("+08:00"):
                start_time = (
                    start_time.replace(" ", "T") + "+08:00"
                    if "T" not in start_time
                    else start_time + "+08:00"
                )

            if end_time and not end_time.endswith("+08:00"):
                end_time = (
                    end_time.replace(" ", "T") + "+08:00"
                    if "T" not in end_time
                    else end_time + "+08:00"
                )

            query_data = {
                "pageNo": page_no,
                "pageSize": page_size,
                "startTime": start_time,
                "endTime": end_time,
                "receiveStartTime": start_time,
                "receiveEndTime": end_time,
                "eventTypes": [196893],  # 196893 = 人脸识别成功事件
            }

            if door_index_codes:
                query_data["doorIndexCodes"] = door_index_codes

            if person_name:
                query_data["personName"] = person_name

            logger.info(f"查询门禁事件: {query_data}")

            result = await self.request("/artemis/api/acs/v2/door/events", data=query_data, method="POST")

            if str(result.get("code")) == "0":
                logger.info(f"门禁事件查询成功，人员姓名: {person_name}")
                return {"success": True, "message": "门禁事件查询成功", "data": result}

            logger.warning(f"门禁事件查询失败: {result}")
            return {
                "success": False,
                "message": f"门禁事件查询失败: {result.get('msg', '未知错误')}",
                "data": result,
            }
        except Exception as e:
            logger.error(f"查询门禁事件异常: {str(e)}")
            return {"success": False, "message": f"查询门禁事件异常: {str(e)}", "data": None}


# 全局客户端实例
_hikvision_client: Optional[HikvisionClient] = None


def get_hikvision_client() -> HikvisionClient:
    """获取海康威视客户端单例"""
    global _hikvision_client
    if _hikvision_client is None:
        _hikvision_client = HikvisionClient()
    return _hikvision_client

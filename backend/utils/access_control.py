"""
门禁系统API工具类
用于查询门禁进出记录
使用海康威视综合安防管理平台API
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from services.hikvision_client import get_hikvision_client

logger = logging.getLogger(__name__)

# 中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))


class AccessControlAPI:
    """门禁系统API客户端（基于海康威视平台）"""
    
    def __init__(self):
        """初始化门禁API客户端"""
        self.client = get_hikvision_client()
    
    def _format_iso8601_time(self, dt: datetime) -> str:
        """
        格式化时间为ISO8601格式（北京时间）
        
        如果传入的datetime没有时区信息，视为北京时间直接标记+08:00；
        如果已有时区信息，转换为北京时间后格式化。
        """
        if dt.tzinfo is None:
            # 无时区信息，视为北京时间，直接标记
            return dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        else:
            dt = dt.astimezone(CST)
            return dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    
    async def check_return_record(
        self, 
        student_id: str,
        person_name: str,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> Dict[str, Any]:
        """
        查询学生在指定时间段内是否有回校记录（门禁事件）
        使用姓名查询,通过jobNo与学号比对确认身份
        
        Args:
            student_id: 学生学号
            person_name: 学生姓名
            start_time: 开始时间（请假开始时间）
            end_time: 结束时间（当前时间），默认为当前时间
            
        Returns:
            {
                'has_return': bool,  # 是否有回校记录
                'return_time': str,  # 最近一次回校时间
                'total_records': int  # 总记录数
            }
        """
        try:
            import json
            
            if end_time is None:
                end_time = datetime.now()
            
            if start_time is None:
                # 默认查询最近7天
                start_time = end_time - timedelta(days=7)
            
            # 格式化时间为ISO8601格式
            start_time_str = self._format_iso8601_time(start_time)
            end_time_str = self._format_iso8601_time(end_time)
            
            logger.info(f"查询门禁记录: 学号={student_id}, 姓名={person_name}, {start_time_str} ~ {end_time_str}")
            
            # 构建请求参数 - 使用门禁事件查询接口
            params = {
                "pageNo": 1,
                "pageSize": 100,
                "doorIndexCodes": [
                    "61e225df81204a34b5933eebe89649fb",
                    "6d3166d19da84887a8333cfcf973a23f"
                ],
                "startTime": start_time_str,
                "endTime": end_time_str,
                "personName": person_name,
                "sort": "personName",
                "order": "desc"
            }
            
            # 调用海康威视门禁事件查询API
            path = "/artemis/api/acs/v1/door/events"
            
            # 打印请求数据
            logger.info(f"[调试] 请求URL: {path}")
            logger.info(f"[调试] 请求Body: {json.dumps(params, ensure_ascii=False, indent=2)}")
            
            result = await self.client.request(path, params)
            
            # 打印响应数据
            logger.info(f"[调试] 响应: {json.dumps(result, ensure_ascii=False)}")
            
            # 解析返回结果
            if result.get('code') == '0':
                data = result.get('data', {})
                records = data.get('list', [])
                total = data.get('total', 0)
                
                logger.info(f"查询到 {total} 条门禁记录")
                
                # 验证所有进出记录，只要匹配到任何一条进门记录就算成功
                matched_records = []
                for record in records:
                    # jobNo在personDetail中
                    person_detail = record.get('personDetail', {})
                    job_no = person_detail.get('jobNo') if person_detail else record.get('jobNo')
                    in_out_type = record.get('inAndOutType')
                    
                    # 验证每一条记录：jobNo与学号匹配，且是进门记录(inAndOutType=1)
                    if job_no == student_id and in_out_type == 1:
                        matched_records.append(record)
                        logger.info(f"匹配成功: 学号={job_no}, 时间={record.get('eventTime')}, 门禁点={record.get('doorName')}")
                
                logger.info(f"匹配学号 {student_id} 的进门记录: {len(matched_records)} 条")
                
                # 只要有任何一条匹配成功就返回成功
                if matched_records:
                    # 取最新的一条记录（已按时间倒序排列）
                    latest_record = matched_records[0]
                    event_time = latest_record.get('eventTime')
                    door_name = latest_record.get('doorName', '未知门禁点')
                    
                    logger.info(f"检测到回校记录: {event_time}, 门禁点: {door_name}")
                    return {
                        'has_return': True,
                        'return_time': event_time,
                        'total_records': len(matched_records),
                        'door_name': door_name,
                        'message': f"检测到回校记录，时间: {event_time}，门禁点: {door_name}"
                    }
                else:
                    # 所有记录都不匹配才返回失败
                    logger.warning(f"所有 {total} 条记录验证完毕，未检测到匹配学号的进门记录")
                    return {
                        'has_return': False,
                        'return_time': None,
                        'total_records': 0,
                        'message': '未检测到回校记录，无法销假'
                    }
            else:
                error_msg = result.get('msg', '未知错误')
                logger.error(f"门禁API返回错误: code={result.get('code')}, msg={error_msg}")
                return {
                    'has_return': False,
                    'return_time': None,
                    'total_records': 0,
                    'message': f"查询门禁记录失败: {error_msg}"
                }
            
        except Exception as e:
            logger.error(f"查询门禁记录异常: {str(e)}", exc_info=True)
            return {
                'has_return': False,
                'return_time': None,
                'total_records': 0,
                'message': f'查询门禁记录异常: {str(e)}'
            }


# 创建全局实例
access_control_api = AccessControlAPI()

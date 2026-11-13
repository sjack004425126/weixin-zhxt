"""
Redis工具类
提供分布式锁、缓存管理、消息队列等功能
"""

import asyncio
import json
import time
import uuid
from typing import Optional, Any, Dict
import logging

logger = logging.getLogger(__name__)

class RedisLock:
    """Redis分布式锁"""
    
    def __init__(self, redis_client, key: str, timeout: int = 10, retry_delay: float = 0.1):
        """
        初始化Redis分布式锁
        
        Args:
            redis_client: Redis客户端
            key: 锁的键名
            timeout: 锁的超时时间（秒）
            retry_delay: 获取锁失败时的重试延迟（秒）
        """
        self.redis_client = redis_client
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.identifier = str(uuid.uuid4())
        self.acquired = False
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.release()
    
    def acquire_sync(self, max_retries: int = 10) -> bool:
        """
        同步获取锁

        Args:
            max_retries: 最大重试次数

        Returns:
            bool: 是否成功获取锁
        """
        import time

        retries = 0
        while retries < max_retries:
            # 尝试设置锁，如果键不存在则设置成功
            result = self.redis_client.set(
                self.key,
                self.identifier,
                nx=True,  # 只在键不存在时设置
                ex=self.timeout  # 设置过期时间
            )

            if result:
                self.acquired = True
                logger.debug(f"成功获取锁: {self.key}")
                return True

            retries += 1
            if retries < max_retries:
                time.sleep(self.retry_delay)

        logger.warning(f"获取锁失败，超过最大重试次数: {self.key}")
        return False

    async def acquire(self, max_retries: int = 10) -> bool:
        """
        异步获取锁

        Args:
            max_retries: 最大重试次数

        Returns:
            bool: 是否成功获取锁
        """
        retries = 0
        while retries < max_retries:
            # 尝试设置锁，如果键不存在则设置成功
            result = self.redis_client.set(
                self.key,
                self.identifier,
                nx=True,  # 只在键不存在时设置
                ex=self.timeout  # 设置过期时间
            )

            if result:
                self.acquired = True
                logger.debug(f"成功获取锁: {self.key}")
                return True

            retries += 1
            if retries < max_retries:
                await asyncio.sleep(self.retry_delay)

        logger.warning(f"获取锁失败，超过最大重试次数: {self.key}")
        return False
    
    def release_sync(self) -> bool:
        """
        同步释放锁

        Returns:
            bool: 是否成功释放锁
        """
        if not self.acquired:
            return True

        # 使用Lua脚本确保只有锁的持有者才能释放锁
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            result = self.redis_client.eval(lua_script, 1, self.key, self.identifier)
            if result:
                self.acquired = False
                logger.debug(f"成功释放锁: {self.key}")
                return True
            else:
                logger.warning(f"释放锁失败，锁可能已被其他进程持有: {self.key}")
                return False
        except Exception as e:
            logger.error(f"释放锁时发生异常: {self.key}, 错误: {str(e)}")
            return False

    async def release(self) -> bool:
        """
        异步释放锁

        Returns:
            bool: 是否成功释放锁
        """
        return self.release_sync()

class CourseCache:
    """课程缓存管理"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.cache_prefix = "course_cache"
        self.default_ttl = 300  # 5分钟缓存
    
    def _get_cache_key(self, course_id: int) -> str:
        """获取缓存键名"""
        return f"{self.cache_prefix}:{course_id}"
    
    def get_course_info(self, course_id: int) -> Optional[Dict]:
        """
        获取课程信息缓存
        
        Args:
            course_id: 课程ID
            
        Returns:
            Dict: 课程信息，如果缓存不存在返回None
        """
        try:
            cache_key = self._get_cache_key(course_id)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                if isinstance(cached_data, bytes):
                    cached_data = cached_data.decode()
                return json.loads(cached_data)
            
            return None
        except Exception as e:
            logger.error(f"获取课程缓存失败: {course_id}, 错误: {str(e)}")
            return None
    
    def set_course_info(self, course_id: int, course_data: Dict, ttl: int = None) -> bool:
        """
        设置课程信息缓存
        
        Args:
            course_id: 课程ID
            course_data: 课程数据
            ttl: 缓存过期时间（秒）
            
        Returns:
            bool: 是否设置成功
        """
        try:
            cache_key = self._get_cache_key(course_id)
            ttl = ttl or self.default_ttl
            
            result = self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(course_data, ensure_ascii=False)
            )
            
            logger.debug(f"设置课程缓存: {course_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"设置课程缓存失败: {course_id}, 错误: {str(e)}")
            return False
    
    def update_current_students(self, course_id: int, current_students: int) -> bool:
        """
        更新课程当前选课人数缓存
        
        Args:
            course_id: 课程ID
            current_students: 当前选课人数
            
        Returns:
            bool: 是否更新成功
        """
        try:
            cache_key = self._get_cache_key(course_id)
            cached_data = self.get_course_info(course_id)
            
            if cached_data:
                cached_data['current_students'] = current_students
                return self.set_course_info(course_id, cached_data)
            
            return False
        except Exception as e:
            logger.error(f"更新课程人数缓存失败: {course_id}, 错误: {str(e)}")
            return False
    
    def delete_course_cache(self, course_id: int) -> bool:
        """
        删除课程缓存
        
        Args:
            course_id: 课程ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            cache_key = self._get_cache_key(course_id)
            result = self.redis_client.delete(cache_key)
            logger.debug(f"删除课程缓存: {course_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"删除课程缓存失败: {course_id}, 错误: {str(e)}")
            return False

class CourseSelectionQueue:
    """选课队列管理"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.queue_prefix = "course_selection_queue"
        self.processing_prefix = "course_selection_processing"
    
    def _get_queue_key(self, course_id: int) -> str:
        """获取队列键名"""
        return f"{self.queue_prefix}:{course_id}"
    
    def _get_processing_key(self, course_id: int) -> str:
        """获取处理中队列键名"""
        return f"{self.processing_prefix}:{course_id}"
    
    def add_to_queue(self, course_id: int, student_id: str, request_data: Dict) -> bool:
        """
        添加选课请求到队列
        
        Args:
            course_id: 课程ID
            student_id: 学生ID
            request_data: 请求数据
            
        Returns:
            bool: 是否添加成功
        """
        try:
            queue_key = self._get_queue_key(course_id)
            
            # 构造队列项
            queue_item = {
                'student_id': student_id,
                'course_id': course_id,
                'timestamp': time.time(),
                'request_data': request_data
            }
            
            # 添加到队列（使用LPUSH，FIFO顺序）
            result = self.redis_client.lpush(
                queue_key,
                json.dumps(queue_item, ensure_ascii=False)
            )
            
            logger.debug(f"添加选课请求到队列: 课程{course_id}, 学生{student_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"添加选课请求到队列失败: {str(e)}")
            return False
    
    def get_from_queue(self, course_id: int, timeout: int = 5) -> Optional[Dict]:
        """
        从队列获取选课请求
        
        Args:
            course_id: 课程ID
            timeout: 阻塞超时时间（秒）
            
        Returns:
            Dict: 选课请求数据，如果队列为空返回None
        """
        try:
            queue_key = self._get_queue_key(course_id)
            processing_key = self._get_processing_key(course_id)
            
            # 使用BRPOPLPUSH原子性地从队列移动到处理中队列
            result = self.redis_client.brpoplpush(
                queue_key,
                processing_key,
                timeout
            )
            
            if result:
                if isinstance(result, bytes):
                    result = result.decode()
                
                queue_item = json.loads(result)
                logger.debug(f"从队列获取选课请求: 课程{course_id}, 学生{queue_item['student_id']}")
                return queue_item
            
            return None
        except Exception as e:
            logger.error(f"从队列获取选课请求失败: {str(e)}")
            return None
    
    def complete_processing(self, course_id: int, queue_item: Dict) -> bool:
        """
        完成选课请求处理
        
        Args:
            course_id: 课程ID
            queue_item: 队列项数据
            
        Returns:
            bool: 是否完成成功
        """
        try:
            processing_key = self._get_processing_key(course_id)
            
            # 从处理中队列移除
            result = self.redis_client.lrem(
                processing_key,
                1,
                json.dumps(queue_item, ensure_ascii=False)
            )
            
            logger.debug(f"完成选课请求处理: 课程{course_id}, 学生{queue_item['student_id']}")
            return bool(result)
        except Exception as e:
            logger.error(f"完成选课请求处理失败: {str(e)}")
            return False
    
    def get_queue_length(self, course_id: int) -> int:
        """
        获取队列长度

        Args:
            course_id: 课程ID

        Returns:
            int: 队列长度
        """
        try:
            queue_key = self._get_queue_key(course_id)
            return self.redis_client.llen(queue_key)
        except Exception as e:
            logger.error(f"获取队列长度失败: {str(e)}")
            return 0


# ============================================================
# 名额预占工具（中职报名场景）
# ============================================================

class SpotReservation:
    """
    合作院校专业名额预占/释放/查询工具。

    键设计（TTL=15分钟，自动过期 = 自动释放）：
      - cooperation:{cooperation_id}  → openid           # 谁占了这个名额
      - user:{openid}                → cooperation_id   # 当前用户占着哪个名额

    行为：
      acquire  → 幂等抢锁（同一用户重抢同专业 = 刷新 TTL）
                → 其他用户已占 → 返回 occupied_by_other
      release  → 只允许占位人主动释放（或 TTL 自然过期）
      status   → 查询当前用户的占位状态和剩余秒数
    """

    # Lua 脚本：原子完成"查-判-占"三步
    _ACQUIRE_SCRIPT = """
    local coop_key   = KEYS[1]   -- zzbm:reserve:cooperation:{id}
    local user_key   = KEYS[2]   -- zzbm:reserve:user:{openid}
    local openid     = ARGV[1]
    local cooperation_id = ARGV[2]
    local ttl        = tonumber(ARGV[3]) or 900

    -- 当前是否已被他人占走
    local current = redis.call('GET', coop_key)
    if current then
        if current == openid then
            -- 同一用户重复占位：幂等刷新 TTL
            redis.call('EXPIRE', coop_key, ttl)
            redis.call('EXPIRE', user_key, ttl)
            local remain = redis.call('TTL', coop_key)
            return {1, 'refreshed', remain}
        else
            -- 被其他用户占走
            return {0, 'occupied_by_other'}
        end
    end

    -- 无人占位：占上
    redis.call('SET', coop_key, openid, 'EX', ttl)
    redis.call('SET', user_key, cooperation_id, 'EX', ttl)
    return {1, 'acquired', ttl}
    """

    _RELEASE_SCRIPT = """
    local coop_key = KEYS[1]
    local user_key = KEYS[2]
    local openid   = ARGV[1]

    -- 只有占位人才能释放
    local current = redis.call('GET', coop_key)
    if current and current == openid then
        redis.call('DEL', coop_key)
        redis.call('DEL', user_key)
        return {1, 'released'}
    end
    return {0, 'not_owner'}
    """

    def __init__(self, redis_client, ttl_seconds: int = 900):
        self.redis = redis_client
        self.ttl = ttl_seconds
        self._acquire_sha = None
        self._release_sha = None

    # ---- 内部 helpers ----

    def _coop_key(self, cooperation_id: str) -> str:
        return f"zzbm:reserve:cooperation:{cooperation_id}"

    def _user_key(self, openid: str) -> str:
        return f"zzbm:reserve:user:{openid}"

    def _ensure_script(self):
        if self._acquire_sha is None:
            self._acquire_sha = self.redis.script_load(self._ACQUIRE_SCRIPT)
        if self._release_sha is None:
            self._release_sha = self.redis.script_load(self._RELEASE_SCRIPT)

    # ---- 公开 API ----

    def acquire(self, openid: str, cooperation_id: str) -> dict:
        """
        抢占名额。

        Returns:
            success: bool
            code:    'acquired' | 'refreshed' | 'occupied_by_other'
            remain:  int（剩余 TTL 秒数）
        """
        try:
            self._ensure_script()
            result = self.redis.evalsha(
                self._acquire_sha, 2,
                self._coop_key(cooperation_id),
                self._user_key(openid),
                openid, cooperation_id, self.ttl
            )
            # Lua 返回 {ok_flag, code_str, remain}，ok_flag 在 result[0]，code_str 在 result[1]
            ok_flag = int(result[0])
            code_str = result[1].decode() if isinstance(result[1], bytes) else result[1]
            # occupied_by_other 时 Lua 只返回 2 个元素，acquired/refreshed 返回 3 个
            remain = int(result[2]) if len(result) >= 3 else 0
            logger.info(f"[SpotReservation] acquire openid={openid} coop={cooperation_id} result={result} ok_flag={ok_flag} code={code_str} remain={remain}")
            return {
                "success": ok_flag == 1,
                "code": code_str,
                "remain": remain,
            }
        except Exception as e:
            logger.error(f"[SpotReservation] acquire failed: {e}")
            return {"success": False, "code": "error", "remain": 0}

    def release(self, openid: str, cooperation_id: str) -> dict:
        """主动释放名额。"""
        try:
            self._ensure_script()
            result = self.redis.evalsha(
                self._release_sha, 2,
                self._coop_key(cooperation_id),
                self._user_key(openid),
                openid
            )
            ok_flag = int(result[0])
            code_str = result[1].decode() if isinstance(result[1], bytes) else result[1]
            logger.info(f"[SpotReservation] release openid={openid} coop={cooperation_id} result={result} ok_flag={ok_flag} code={code_str}")
            return {
                "success": ok_flag == 1,
                "code": code_str,
            }
        except Exception as e:
            logger.error(f"[SpotReservation] release failed: {e}")
            return {"success": False, "code": "error"}

    def get_status(self, openid: str) -> dict:
        """
        查询当前用户的占位状态。

        Returns:
            occupied: bool
            cooperation_id: str | None
            remain:   int（剩余秒数，occupied=True 时有效）
            major_name: str（前端显示用，可选）
        """
        try:
            user_key = self._user_key(openid)
            cooperation_id = self.redis.get(user_key)
            if not cooperation_id:
                return {"occupied": False, "cooperation_id": None, "remain": 0}
            if isinstance(cooperation_id, bytes):
                cooperation_id = cooperation_id.decode()
            remain = self.redis.ttl(user_key)
            if remain < 0:
                # 理论上不会走到这里（TTL 过期键已不存在），防御性处理
                return {"occupied": False, "cooperation_id": None, "remain": 0}
            return {
                "occupied": True,
                "cooperation_id": cooperation_id,
                "remain": remain,
            }
        except Exception as e:
            logger.error(f"[SpotReservation] get_status failed: {e}")
            return {"occupied": False, "cooperation_id": None, "remain": 0}

"""
Tortoise ORM 管理器 - 单例模式
提供数据库连接、原生SQL执行和事务支持
"""

import logging
from typing import Any, Optional, Dict, List
from contextlib import asynccontextmanager
from tortoise import connections
from tortoise.transactions import in_transaction
from tortoise.exceptions import DBConnectionError


class TortoiseManager:
    """Tortoise ORM 管理器 - 单例模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TortoiseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_init_done'):
            self._init_done = True
            self.logger = logging.getLogger(__name__)

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    def mark_initialized(self):
        """标记为已初始化（由Tortoise自动初始化后调用）"""
        self._initialized = True
        self.logger.info("Tortoise ORM manager marked as initialized")

    def get_connection(self, connection_name: str = "default"):
        """获取数据库连接对象"""
        if not self._initialized:
            raise DBConnectionError("Tortoise ORM not initialized")

        try:
            return connections.get(connection_name)
        except KeyError:
            raise DBConnectionError(f"Connection '{connection_name}' not found")

    async def execute_raw_sql(
        self,
        query: str,
        params: List = None,
        columns: List[str] = None,
        connection_name: str = "default"
    ) -> 'RawSQLResult':
        """
        执行原生SQL查询，返回增强的结果对象

        Args:
            query: SQL查询语句
            params: 查询参数
            columns: 列名列表（可选，用于 to_dict_list 重命名）
            connection_name: 连接名称

        Returns:
            RawSQLResult: 增强的原生查询结果，支持 .to_dict_list() 等便捷方法
        """
        conn = self.get_connection(connection_name)
        try:
            if params:
                result = await conn.execute_query(query, params)
            else:
                result = await conn.execute_query(query)
            return RawSQLResult(result, columns)
        except Exception as e:
            self.logger.error(f"Raw SQL execution failed: {e}")
            raise



    async def query(
        self,
        query: str,
        params: List = None,
        columns: List[str] = None,
        connection_name: str = "default"
    ) -> 'QueryResult':
        """
        执行查询并返回QueryResult对象

        Args:
            query: SQL查询语句
            params: 查询参数
            columns: 列名列表
            connection_name: 连接名称

        Returns:
            QueryResult: 查询结果对象，支持链式调用
        """
        raw_result = await self.execute_raw_sql(query, params, connection_name)
        return QueryResult(raw_result, columns)

    async def select(
        self,
        table: str,
        columns: List[str] = None,
        where: str = None,
        params: List = None,
        order_by: str = None,
        limit: int = None,
        offset: int = None,
        connection_name: str = "default"
    ) -> 'QueryResult':
        """
        便捷的SELECT查询方法

        Args:
            table: 表名
            columns: 要查询的列名列表，None表示查询所有列
            where: WHERE条件
            params: 查询参数
            order_by: 排序条件
            limit: 限制条数
            offset: 偏移量
            connection_name: 连接名称

        Returns:
            QueryResult: 查询结果对象
        """
        # 构建SQL语句
        col_str = ", ".join(columns) if columns else "*"
        sql = f"SELECT {col_str} FROM {table}"

        query_params = params or []

        if where:
            sql += f" WHERE {where}"

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit:
            sql += f" LIMIT {limit}"

        if offset:
            sql += f" OFFSET {offset}"

        raw_result = await self.execute_raw_sql(sql, query_params, connection_name)
        return QueryResult(raw_result, columns)

    async def execute_raw_sql_in_transaction(
        self,
        query: str,
        params: List = None,
        connection_name: str = "default"
    ) -> Any:
        """在事务中执行原生SQL"""
        async with in_transaction(connection_name) as conn:
            try:
                if params:
                    result = await conn.execute_query(query, params)
                else:
                    result = await conn.execute_query(query)
                return result
            except Exception as e:
                self.logger.error(f"Raw SQL execution in transaction failed: {e}")
                raise

    @asynccontextmanager
    async def transaction(self, connection_name: str = "default"):
        """获取事务连接上下文"""
        if not self._initialized:
            raise DBConnectionError("Tortoise ORM not initialized")

        async with in_transaction(connection_name) as conn:
            yield conn

    async def execute_multiple_in_transaction(
        self,
        queries: List[Dict[str, Any]],
        connection_name: str = "default"
    ) -> List[Any]:
        """在事务中执行多个SQL语句"""
        results = []
        async with self.transaction(connection_name) as conn:
            for query_info in queries:
                query = query_info.get("query")
                params = query_info.get("params")

                try:
                    if params:
                        result = await conn.execute_query(query, params)
                    else:
                        result = await conn.execute_query(query)
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Query failed in transaction: {query}, error: {e}")
                    raise

        return results

    def is_connected(self, connection_name: str = "default") -> bool:
        """检查连接是否可用"""
        if not self._initialized:
            return False

        try:
            conn = connections.get(connection_name)
            return conn is not None
        except KeyError:
            return False

    async def test_connection(self, connection_name: str = "default") -> bool:
        """测试数据库连接"""
        try:
            await self.execute_raw_sql("SELECT 1", connection_name=connection_name)
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    async def get_connection_info(self, connection_name: str = "default") -> Dict[str, Any]:
        """获取连接信息"""
        if not self._initialized:
            return {"status": "not_initialized"}

        try:
            self.get_connection(connection_name)
            return {
                "status": "connected",
                "connection_name": connection_name,
                "is_connected": self.is_connected(connection_name)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


# 创建全局单例实例
tortoise_manager = TortoiseManager()


# 便捷的装饰器
def with_transaction(connection_name: str = "default"):
    """事务装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with tortoise_manager.transaction(connection_name) as conn:
                return await func(conn, *args, **kwargs)
        return wrapper
    return decorator


# 便捷的原生SQL执行函数
async def execute_sql(query: str, params: List = None, connection_name: str = "default"):
    """便捷的原生SQL执行函数"""
    return await tortoise_manager.execute_raw_sql(query, params, connection_name)


async def execute_sql_in_transaction(query: str, params: List = None, connection_name: str = "default"):
    """便捷的事务中SQL执行函数"""
    return await tortoise_manager.execute_raw_sql_in_transaction(query, params, connection_name)



        
    try:
        db_creds = self._db_config["connections"]["default"]["credentials"]
        return {
            "status": "connected",
            "host": db_creds["host"],
            "port": db_creds["port"],
            "database": db_creds["database"],
            "config_name": self._config_name,
            "connections": len(connections._connections) if hasattr(connections, '_connections') else 0
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

def is_initialized(self) -> bool:
    """检查是否已初始化"""
    return self._initialized

async def health_check(self) -> Dict[str, Any]:
    """健康检查"""
    if not self._initialized:
        return {
            "status": "unhealthy",
            "reason": "not_initialized"
        }
    
    try:
        # 测试连接
        conn = connections.get("default")
        result = await conn.execute_query("SELECT 1 as health_check")
        
        return {
            "status": "healthy",
            "connection_info": self.get_connection_info(),
            "test_query": "passed"
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "reason": str(e)
        }

async def get_database_stats(self) -> Dict[str, Any]:
    """获取数据库统计信息"""
    if not self._initialized:
        return {"error": "Database not initialized"}
    
    try:
        conn = connections.get("default")
        
        # 获取表信息
        tables_query = """
            SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME
        """
        
        result = await conn.execute_query(tables_query)
        
        tables_info = []
        total_rows = 0
        total_data_size = 0
        total_index_size = 0
        
        if result and len(result) > 1:
            for row in result[1]:  # result[1] contains the data rows
                if isinstance(row, dict):
                    table_info = {
                        "table_name": row.get("TABLE_NAME"),
                        "rows": row.get("TABLE_ROWS", 0) or 0,
                        "data_size": row.get("DATA_LENGTH", 0) or 0,
                        "index_size": row.get("INDEX_LENGTH", 0) or 0
                    }
                else:
                    # Handle tuple/list format
                    table_info = {
                        "table_name": row[0],
                        "rows": row[1] or 0,
                        "data_size": row[2] or 0,
                        "index_size": row[3] or 0
                    }
                
                tables_info.append(table_info)
                total_rows += table_info["rows"]
                total_data_size += table_info["data_size"]
                total_index_size += table_info["index_size"]
        
        return {
            "total_tables": len(tables_info),
            "total_rows": total_rows,
            "total_data_size": total_data_size,
            "total_index_size": total_index_size,
            "tables": tables_info
        }
        
    except Exception as e:
        logging.error(f"Error getting database stats: {e}")
        return {"error": str(e)}

async def execute_raw_query(self, query: str, params: list = None) -> Any:
    """执行原始SQL查询"""
    if not self._initialized:
        raise DBConnectionError("Database not initialized")
    
    try:
        conn = connections.get("default")
        if params:
            result = await conn.execute_query(query, params)
        else:
            result = await conn.execute_query(query)
        return result
    except Exception as e:
        logging.error(f"Error executing raw query: {e}")
        raise


# 创建全局实例
tortoise_manager = TortoiseManager()


# 兼容性函数，用于FastAPI生命周期事件
async def init_tortoise_orm(config_name: str = 'development'):
    """初始化Tortoise ORM - 用于FastAPI startup事件"""
    return await tortoise_manager.init_db(config_name)


async def close_tortoise_orm():
    """关闭Tortoise ORM - 用于FastAPI shutdown事件"""
    await tortoise_manager.close_db()


# 依赖注入函数
def get_tortoise_manager() -> TortoiseManager:
    """获取Tortoise管理器实例 - 用于依赖注入"""
    return tortoise_manager


# 数据库连接装饰器
def require_db_connection(func):
    """装饰器：确保数据库连接可用"""
    async def wrapper(*args, **kwargs):
        if not tortoise_manager.is_initialized():
            raise DBConnectionError("Database connection not available")
        return await func(*args, **kwargs)
    return wrapper


# ==================== 查询结果包装类 ====================

class QueryResult:
    """查询结果包装类，提供便捷的转换方法"""

    def __init__(self, raw_result: tuple, columns: List[str] = None):
        """
        初始化查询结果

        Args:
            raw_result: 原始查询结果 (affected_rows, data_rows)
            columns: 列名列表，如果不提供则使用索引
        """
        self.raw_result = raw_result
        self.affected_rows = raw_result[0] if raw_result else 0
        self.data_rows = raw_result[1] if raw_result and len(raw_result) > 1 else []
        self.columns = columns or []

    def __bool__(self):
        """支持布尔判断"""
        return bool(self.data_rows)

    def __len__(self):
        """支持len()函数"""
        return len(self.data_rows)

    def __iter__(self):
        """支持迭代"""
        return iter(self.data_rows)

    def __getitem__(self, index):
        """支持索引访问"""
        return self.data_rows[index]

    @property
    def count(self) -> int:
        """获取数据行数"""
        return len(self.data_rows)

    @property
    def is_empty(self) -> bool:
        """检查是否为空"""
        return len(self.data_rows) == 0

    def first(self) -> tuple:
        """获取第一行数据"""
        return self.data_rows[0] if self.data_rows else None

    def last(self) -> tuple:
        """获取最后一行数据"""
        return self.data_rows[-1] if self.data_rows else None

    def debug_info(self) -> Dict[str, Any]:
        """获取调试信息"""
        return {
            "raw_result_type": type(self.raw_result).__name__,
            "raw_result_length": len(self.raw_result) if self.raw_result else 0,
            "raw_result": self.raw_result,
            "affected_rows": self.affected_rows,
            "data_rows_type": type(self.data_rows).__name__,
            "data_rows_length": len(self.data_rows) if self.data_rows else 0,
            "data_rows": self.data_rows,
            "columns": self.columns,
            "first_row_type": type(self.data_rows[0]).__name__ if self.data_rows else None,
            "first_row": self.data_rows[0] if self.data_rows else None
        }

    def to_dict_list(self, columns: List[str] = None) -> List[Dict[str, Any]]:
        """
        转换为字典列表

        Args:
            columns: 列名列表，如果不提供则使用初始化时的列名或自动生成

        Returns:
            List[Dict]: 字典列表
        """
        if not self.data_rows:
            return []

        # 如果数据行已经是字典格式，直接返回或重新映射列名
        if self.data_rows and isinstance(self.data_rows[0], dict):
            if columns:
                # 重新映射列名
                result = []
                for row in self.data_rows:
                    if row:
                        row_dict = {}
                        for i, col_name in enumerate(columns):
                            if i < len(self.columns) and self.columns[i] in row:
                                row_dict[col_name] = row[self.columns[i]]
                        result.append(row_dict)
                return result
            else:
                # 直接返回字典列表
                return [dict(row) for row in self.data_rows if row]

        # 处理元组格式的数据行
        col_names = columns or self.columns
        if not col_names:
            # 自动生成列名
            if self.data_rows and len(self.data_rows) > 0:
                col_count = len(self.data_rows[0])
                col_names = [f"col_{i}" for i in range(col_count)]
            else:
                return []

        # 转换为字典列表
        result = []
        for row in self.data_rows:
            if row:  # 确保行不为空
                row_dict = {}
                for i in range(min(len(col_names), len(row))):
                    row_dict[col_names[i]] = row[i]
                result.append(row_dict)

        return result

    def to_dict_list_fast(self, columns: List[str]) -> List[Dict[str, Any]]:
        """
        快速转换为字典列表（使用zip优化）

        Args:
            columns: 列名列表

        Returns:
            List[Dict]: 字典列表
        """
        if not self.data_rows or not columns:
            return []

        # 如果数据行已经是字典格式
        if self.data_rows and isinstance(self.data_rows[0], dict):
            result = []
            for row in self.data_rows:
                if row:
                    row_dict = {}
                    for i, col_name in enumerate(columns):
                        if i < len(self.columns) and self.columns[i] in row:
                            row_dict[col_name] = row[self.columns[i]]
                    result.append(row_dict)
            return result

        # 处理元组格式的数据行
        result = []
        for row in self.data_rows:
            if row:  # 确保行不为空
                result.append(dict(zip(columns, row)))

        return result

    def to_named_tuples(self, name: str = "Record", columns: List[str] = None):
        """
        转换为命名元组列表

        Args:
            name: 命名元组的名称
            columns: 列名列表

        Returns:
            List[NamedTuple]: 命名元组列表
        """
        if not self.data_rows:
            return []

        from collections import namedtuple

        col_names = columns or self.columns
        if not col_names:
            col_count = len(self.data_rows[0]) if self.data_rows else 0
            col_names = [f"col_{i}" for i in range(col_count)]

        # 创建命名元组类
        RecordType = namedtuple(name, col_names)

        return [RecordType(*row) for row in self.data_rows]

    def filter(self, predicate) -> 'QueryResult':
        """
        过滤数据行

        Args:
            predicate: 过滤函数，接收一行数据，返回布尔值

        Returns:
            QueryResult: 新的查询结果对象
        """
        filtered_rows = [row for row in self.data_rows if predicate(row)]
        return QueryResult((len(filtered_rows), filtered_rows), self.columns)

    def map(self, mapper) -> 'QueryResult':
        """
        映射数据行

        Args:
            mapper: 映射函数，接收一行数据，返回新的数据

        Returns:
            QueryResult: 新的查询结果对象
        """
        mapped_rows = [mapper(row) for row in self.data_rows]
        return QueryResult((len(mapped_rows), mapped_rows), self.columns)

    def slice(self, start: int, end: int = None) -> 'QueryResult':
        """
        切片数据

        Args:
            start: 开始索引
            end: 结束索引

        Returns:
            QueryResult: 新的查询结果对象
        """
        sliced_rows = self.data_rows[start:end]
        return QueryResult((len(sliced_rows), sliced_rows), self.columns)

    def group_by(self, key_func) -> Dict[Any, 'QueryResult']:
        """
        按指定函数分组

        Args:
            key_func: 分组键函数，接收一行数据，返回分组键

        Returns:
            Dict: 分组结果，键为分组键，值为QueryResult对象
        """
        from collections import defaultdict

        groups = defaultdict(list)
        for row in self.data_rows:
            key = key_func(row)
            groups[key].append(row)

        return {
            key: QueryResult((len(rows), rows), self.columns)
            for key, rows in groups.items()
        }

    def sort(self, key_func=None, reverse=False) -> 'QueryResult':
        """
        排序数据

        Args:
            key_func: 排序键函数
            reverse: 是否倒序

        Returns:
            QueryResult: 新的查询结果对象
        """
        sorted_rows = sorted(self.data_rows, key=key_func, reverse=reverse)
        return QueryResult((len(sorted_rows), sorted_rows), self.columns)

    def unique(self, key_func=None) -> 'QueryResult':
        """
        去重数据

        Args:
            key_func: 去重键函数，如果不提供则按整行去重

        Returns:
            QueryResult: 新的查询结果对象
        """
        if key_func is None:
            # 按整行去重
            seen = set()
            unique_rows = []
            for row in self.data_rows:
                if row not in seen:
                    seen.add(row)
                    unique_rows.append(row)
        else:
            # 按指定键去重
            seen = set()
            unique_rows = []
            for row in self.data_rows:
                key = key_func(row)
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)

        return QueryResult((len(unique_rows), unique_rows), self.columns)


# ==================== 原生SQL结果增强类 ====================

class RawSQLResult:
    """原生SQL查询结果增强类，支持便捷方法"""

    def __init__(self, raw_result: tuple, columns: List[str] = None):
        """
        初始化原生SQL结果

        Args:
            raw_result: 原始查询结果 (affected_rows, data_rows)
            columns: 列名列表（可选，用于 to_dict_list 重命名列）
        """
        self.raw_result = raw_result
        self.affected_rows = raw_result[0] if raw_result else 0
        self.data_rows = raw_result[1] if raw_result and len(raw_result) > 1 else []
        self.columns = columns or []

    def __getitem__(self, index):
        """支持索引访问，兼容原生结果格式"""
        return self.raw_result[index]

    def __dict__(self):
        """支持 FastAPI 序列化"""
        return {
            "affected_rows": self.affected_rows,
            "data_rows": self.data_rows,
            "columns": self.columns,
            "count": self.count
        }

    @property
    def count(self) -> int:
        """获取数据行数"""
        return len(self.data_rows)

    def first(self):
        """获取第一行数据"""
        return self.data_rows[0] if self.data_rows else None

    def to_dict_list(self, columns: List[str] = None) -> List[Dict[str, Any]]:
        """
        转换为字典列表

        Args:
            columns: 列名列表（可选）
                    - 如果不提供，直接返回原始字典列表
                    - 如果提供，用于重命名列

        Returns:
            List[Dict]: 字典列表
        """
        if not self.data_rows:
            return []

        # 数据行已经是字典格式
        if self.data_rows and isinstance(self.data_rows[0], dict):
            if columns:
                # 重新映射列名
                result = []
                original_keys = list(self.data_rows[0].keys()) if self.data_rows else []
                for row in self.data_rows:
                    if row:
                        row_dict = {}
                        for i, col_name in enumerate(columns):
                            if i < len(original_keys) and original_keys[i] in row:
                                row_dict[col_name] = row[original_keys[i]]
                        result.append(row_dict)
                return result
            else:
                # 直接返回字典列表（最常用的情况）
                return [dict(row) for row in self.data_rows if row]

        # 处理元组格式的数据行（向后兼容，实际很少用到）
        col_names = columns
        if not col_names:
            # 自动生成列名
            if self.data_rows and len(self.data_rows) > 0:
                col_count = len(self.data_rows[0])
                col_names = [f"col_{i}" for i in range(col_count)]
            else:
                return []

        # 转换为字典列表
        result = []
        for row in self.data_rows:
            if row:
                row_dict = {}
                for i in range(min(len(col_names), len(row))):
                    row_dict[col_names[i]] = row[i]
                result.append(row_dict)

        return result



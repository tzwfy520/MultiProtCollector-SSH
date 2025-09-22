"""
SQLite数据库模块
用于存储任务历史、状态和统计信息
"""
import sqlite3
import aiosqlite
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.sqlite import JSON
from contextlib import contextmanager, asynccontextmanager

from .config import settings
from .utils import logger, handle_exception, CollectorException

# SQLAlchemy基类
Base = declarative_base()


class TaskRecord(Base):
    """任务记录表"""
    __tablename__ = "task_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    task_type = Column(String(32), nullable=False, default="simple")
    status = Column(String(32), nullable=False, default="pending")
    
    # 目标设备信息
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=22)
    device_type = Column(String(64), nullable=True)
    
    # 任务配置
    commands = Column(Text, nullable=False)  # JSON格式存储命令列表
    timeout = Column(Integer, default=300)
    retry_count = Column(Integer, default=3)
    
    # 执行信息
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time = Column(Float, nullable=True)
    
    # 结果信息
    success = Column(Boolean, nullable=True)
    result_data = Column(Text, nullable=True)  # JSON格式存储结果
    error_message = Column(Text, nullable=True)
    error_code = Column(String(64), nullable=True)
    
    # 元数据
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CollectorStats(Base):
    """采集器统计表"""
    __tablename__ = "collector_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD格式
    
    # 任务统计
    total_tasks = Column(Integer, default=0)
    successful_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    
    # 性能统计
    avg_execution_time = Column(Float, default=0.0)
    max_execution_time = Column(Float, default=0.0)
    min_execution_time = Column(Float, default=0.0)
    
    # 系统统计
    uptime_seconds = Column(Integer, default=0)
    cpu_usage_avg = Column(Float, default=0.0)
    memory_usage_avg = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemLog(Base):
    """系统日志表"""
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(10), nullable=False, index=True)  # INFO, WARNING, ERROR
    module = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON格式存储详细信息
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class DatabaseException(CollectorException):
    """数据库异常"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "DATABASE_ERROR", details)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self.engine = None
        self.SessionLocal = None
        self._ensure_db_directory()
        self._init_database()
    
    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self):
        """初始化数据库"""
        try:
            # 创建SQLAlchemy引擎
            self.engine = create_engine(
                f"sqlite:///{self.db_path}",
                echo=settings.debug,  # 使用小写的debug
                pool_pre_ping=True,
                connect_args={"check_same_thread": False}
            )
            
            # 创建会话工厂
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # 创建所有表
            Base.metadata.create_all(bind=self.engine)
            logger.info(f"数据库初始化完成: {self.db_path}")
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise DatabaseException(f"数据库初始化失败: {e}")
    
    @contextmanager
    def get_session(self) -> Session:
        """获取数据库会话"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise DatabaseException(f"数据库操作失败: {e}")
        finally:
            session.close()
    
    @asynccontextmanager
    async def get_async_connection(self):
        """获取异步数据库连接"""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn
    
    @handle_exception
    def create_task_record(self, task_data: Dict[str, Any]) -> str:
        """创建任务记录"""
        with self.get_session() as session:
            task_record = TaskRecord(
                task_id=task_data["task_id"],
                task_type=task_data.get("task_type", "simple"),
                status="pending",
                host=task_data["credentials"]["host"],
                port=task_data["credentials"].get("port", 22),
                device_type=task_data["credentials"].get("device_type"),
                commands=json.dumps(task_data["commands"]),
                timeout=task_data.get("timeout", 300),
                retry_count=task_data.get("retry_count", 3),
                created_by=task_data.get("created_by", "system")
            )
            
            session.add(task_record)
            session.flush()
            
            logger.info(f"创建任务记录: {task_data['task_id']}")
            return task_data["task_id"]
    
    @handle_exception
    def update_task_status(self, task_id: str, status: str, **kwargs):
        """更新任务状态"""
        with self.get_session() as session:
            task_record = session.query(TaskRecord).filter(
                TaskRecord.task_id == task_id
            ).first()
            
            if not task_record:
                raise DatabaseException(f"任务记录不存在: {task_id}")
            
            # 更新状态
            task_record.status = status
            task_record.updated_at = datetime.utcnow()
            
            # 更新其他字段
            for key, value in kwargs.items():
                if hasattr(task_record, key):
                    setattr(task_record, key, value)
            
            logger.info(f"更新任务状态: {task_id} -> {status}")
    
    @handle_exception
    def complete_task(self, task_id: str, success: bool, result_data: Optional[Dict] = None, 
                     error_message: Optional[str] = None, execution_time: Optional[float] = None):
        """完成任务记录"""
        with self.get_session() as session:
            task_record = session.query(TaskRecord).filter(
                TaskRecord.task_id == task_id
            ).first()
            
            if not task_record:
                raise DatabaseException(f"任务记录不存在: {task_id}")
            
            # 更新完成信息
            task_record.status = "completed" if success else "failed"
            task_record.success = success
            task_record.completed_at = datetime.utcnow()
            task_record.updated_at = datetime.utcnow()
            
            if execution_time:
                task_record.execution_time = execution_time
            
            if result_data:
                task_record.result_data = json.dumps(result_data)
            
            if error_message:
                task_record.error_message = error_message
            
            logger.info(f"完成任务记录: {task_id} (成功: {success})")
    
    @handle_exception
    def get_task_record(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务记录"""
        with self.get_session() as session:
            task_record = session.query(TaskRecord).filter(
                TaskRecord.task_id == task_id
            ).first()
            
            if not task_record:
                return None
            
            return {
                "task_id": task_record.task_id,
                "task_type": task_record.task_type,
                "status": task_record.status,
                "host": task_record.host,
                "port": task_record.port,
                "device_type": task_record.device_type,
                "commands": json.loads(task_record.commands) if task_record.commands else [],
                "timeout": task_record.timeout,
                "retry_count": task_record.retry_count,
                "started_at": task_record.started_at.isoformat() if task_record.started_at else None,
                "completed_at": task_record.completed_at.isoformat() if task_record.completed_at else None,
                "execution_time": task_record.execution_time,
                "success": task_record.success,
                "result_data": json.loads(task_record.result_data) if task_record.result_data else None,
                "error_message": task_record.error_message,
                "error_code": task_record.error_code,
                "created_by": task_record.created_by,
                "created_at": task_record.created_at.isoformat(),
                "updated_at": task_record.updated_at.isoformat()
            }
    
    @handle_exception
    def get_task_history(self, limit: int = 100, offset: int = 0, 
                        status: Optional[str] = None, host: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取任务历史"""
        with self.get_session() as session:
            query = session.query(TaskRecord)
            
            # 添加过滤条件
            if status:
                query = query.filter(TaskRecord.status == status)
            if host:
                query = query.filter(TaskRecord.host == host)
            
            # 排序和分页
            query = query.order_by(TaskRecord.created_at.desc())
            query = query.offset(offset).limit(limit)
            
            records = query.all()
            
            return [
                {
                    "task_id": record.task_id,
                    "task_type": record.task_type,
                    "status": record.status,
                    "host": record.host,
                    "port": record.port,
                    "device_type": record.device_type,
                    "timeout": record.timeout,
                    "started_at": record.started_at.isoformat() if record.started_at else None,
                    "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                    "execution_time": record.execution_time,
                    "success": record.success,
                    "error_message": record.error_message,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat()
                }
                for record in records
            ]
    
    @handle_exception
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """获取统计信息"""
        with self.get_session() as session:
            # 获取最近N天的任务统计
            from sqlalchemy import func, and_
            from datetime import timedelta
            
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # 总任务数
            total_tasks = session.query(func.count(TaskRecord.id)).filter(
                TaskRecord.created_at >= start_date
            ).scalar() or 0
            
            # 成功任务数
            successful_tasks = session.query(func.count(TaskRecord.id)).filter(
                and_(
                    TaskRecord.created_at >= start_date,
                    TaskRecord.success == True
                )
            ).scalar() or 0
            
            # 失败任务数
            failed_tasks = session.query(func.count(TaskRecord.id)).filter(
                and_(
                    TaskRecord.created_at >= start_date,
                    TaskRecord.success == False
                )
            ).scalar() or 0
            
            # 平均执行时间
            avg_execution_time = session.query(func.avg(TaskRecord.execution_time)).filter(
                and_(
                    TaskRecord.created_at >= start_date,
                    TaskRecord.execution_time.isnot(None)
                )
            ).scalar() or 0.0
            
            # 按状态分组统计
            status_stats = session.query(
                TaskRecord.status,
                func.count(TaskRecord.id)
            ).filter(
                TaskRecord.created_at >= start_date
            ).group_by(TaskRecord.status).all()
            
            status_counts = {status: count for status, count in status_stats}
            
            return {
                "period_days": days,
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "failed_tasks": failed_tasks,
                "success_rate": (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0.0,
                "avg_execution_time": float(avg_execution_time),
                "status_counts": status_counts
            }
    
    @handle_exception
    def log_system_event(self, level: str, module: str, message: str, details: Optional[Dict] = None):
        """记录系统日志"""
        with self.get_session() as session:
            log_entry = SystemLog(
                level=level.upper(),
                module=module,
                message=message,
                details=json.dumps(details) if details else None
            )
            
            session.add(log_entry)
    
    @handle_exception
    def cleanup_old_records(self, days: int = 30):
        """清理旧记录"""
        with self.get_session() as session:
            from datetime import timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # 清理旧任务记录
            deleted_tasks = session.query(TaskRecord).filter(
                TaskRecord.created_at < cutoff_date
            ).delete()
            
            # 清理旧日志记录
            deleted_logs = session.query(SystemLog).filter(
                SystemLog.timestamp < cutoff_date
            ).delete()
            
            logger.info(f"清理完成: 删除 {deleted_tasks} 个任务记录, {deleted_logs} 个日志记录")
            
            return {
                "deleted_tasks": deleted_tasks,
                "deleted_logs": deleted_logs
            }


# 全局数据库管理器实例
db_manager = DatabaseManager()


# 便捷函数
def create_task_record(task_data: Dict[str, Any]) -> str:
    """创建任务记录"""
    return db_manager.create_task_record(task_data)


def update_task_status(task_id: str, status: str, **kwargs):
    """更新任务状态"""
    return db_manager.update_task_status(task_id, status, **kwargs)


def complete_task(task_id: str, success: bool, result_data: Optional[Dict] = None, 
                 error_message: Optional[str] = None, execution_time: Optional[float] = None):
    """完成任务记录"""
    return db_manager.complete_task(task_id, success, result_data, error_message, execution_time)


def get_task_record(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务记录"""
    return db_manager.get_task_record(task_id)


def get_task_history(limit: int = 100, offset: int = 0, 
                    status: Optional[str] = None, host: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取任务历史"""
    return db_manager.get_task_history(limit, offset, status, host)


def get_statistics(days: int = 7) -> Dict[str, Any]:
    """获取统计信息"""
    return db_manager.get_statistics(days)


def log_system_event(level: str, module: str, message: str, details: Optional[Dict] = None):
    """记录系统日志"""
    return db_manager.log_system_event(level, module, message, details)
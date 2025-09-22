#!/usr/bin/env python3
"""
数据库初始化脚本
用于初始化SQLite数据库和创建必要的表结构
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import DatabaseManager, db_manager
from src.config import settings
from src.utils import logger


def init_database():
    """初始化数据库"""
    try:
        logger.info("开始初始化数据库...")
        
        # 确保数据库目录存在
        db_path = Path(settings.database_path)
        db_dir = db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库管理器
        db_manager._init_database()
        
        logger.info(f"数据库初始化完成: {settings.database_path}")
        
        # 验证表是否创建成功
        with db_manager.get_session() as session:
            from src.database import TaskRecord, CollectorStats, SystemLog
            
            # 检查表是否存在
            tables = [TaskRecord, CollectorStats, SystemLog]
            for table in tables:
                count = session.query(table).count()
                logger.info(f"表 {table.__tablename__} 创建成功，当前记录数: {count}")
        
        return True
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        return False


def create_sample_data():
    """创建示例数据"""
    try:
        logger.info("创建示例数据...")
        
        from src.database import log_system_event
        
        # 创建系统日志示例
        log_system_event("INFO", "database", "数据库初始化完成", {
            "database_path": settings.database_path,
            "version": "1.0.0"
        })
        
        log_system_event("INFO", "system", "采集器启动", {
            "collector_id": settings.collector_id,
            "collector_name": settings.collector_name
        })
        
        logger.info("示例数据创建完成")
        return True
        
    except Exception as e:
        logger.error(f"创建示例数据失败: {e}")
        return False


def check_database_health():
    """检查数据库健康状态"""
    try:
        logger.info("检查数据库健康状态...")
        
        with db_manager.get_session() as session:
            from src.database import TaskRecord, CollectorStats, SystemLog
            
            # 检查各表的记录数
            task_count = session.query(TaskRecord).count()
            stats_count = session.query(CollectorStats).count()
            log_count = session.query(SystemLog).count()
            
            logger.info(f"数据库健康检查结果:")
            logger.info(f"  - 任务记录: {task_count} 条")
            logger.info(f"  - 统计记录: {stats_count} 条")
            logger.info(f"  - 日志记录: {log_count} 条")
            
            # 测试数据库操作
            from src.database import get_statistics
            stats = get_statistics(days=30)
            logger.info(f"  - 统计查询测试: 成功 (最近30天任务数: {stats['total_tasks']})")
            
        return True
        
    except Exception as e:
        logger.error(f"数据库健康检查失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("SSH采集器 - 数据库初始化脚本")
    print("=" * 60)
    
    # 显示配置信息
    print(f"数据库路径: {settings.database_path}")
    print(f"采集器ID: {settings.collector_id}")
    print(f"采集器名称: {settings.collector_name}")
    print("-" * 60)
    
    # 初始化数据库
    if not init_database():
        print("❌ 数据库初始化失败")
        sys.exit(1)
    
    print("✅ 数据库初始化成功")
    
    # 创建示例数据
    if not create_sample_data():
        print("⚠️  示例数据创建失败")
    else:
        print("✅ 示例数据创建成功")
    
    # 健康检查
    if not check_database_health():
        print("❌ 数据库健康检查失败")
        sys.exit(1)
    
    print("✅ 数据库健康检查通过")
    print("-" * 60)
    print("🎉 数据库初始化完成！")
    print()
    print("可用的API接口:")
    print("  - GET /tasks          - 获取任务列表")
    print("  - GET /tasks/{id}     - 获取任务详情")
    print("  - GET /statistics     - 获取统计信息")
    print()
    print("数据库文件位置:", os.path.abspath(settings.database_path))


if __name__ == "__main__":
    main()
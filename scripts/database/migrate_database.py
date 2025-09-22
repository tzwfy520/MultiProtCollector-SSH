#!/usr/bin/env python3
"""
数据库迁移脚本
用于数据库版本升级和数据迁移
"""
import sys
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import settings
from src.utils import logger


class DatabaseMigrator:
    """数据库迁移器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations_dir = Path(__file__).parent / "migrations"
        self.migrations_dir.mkdir(exist_ok=True)
        
    def get_current_version(self) -> str:
        """获取当前数据库版本"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查版本表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='schema_version'
            """)
            
            if not cursor.fetchone():
                # 创建版本表
                cursor.execute("""
                    CREATE TABLE schema_version (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    )
                """)
                conn.commit()
                return "0.0.0"
            
            # 获取最新版本
            cursor.execute("""
                SELECT version FROM schema_version 
                ORDER BY applied_at DESC LIMIT 1
            """)
            
            result = cursor.fetchone()
            return result[0] if result else "0.0.0"
            
        except Exception as e:
            logger.error(f"获取数据库版本失败: {e}")
            return "0.0.0"
        finally:
            if 'conn' in locals():
                conn.close()
    
    def set_version(self, version: str, description: str = ""):
        """设置数据库版本"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO schema_version (version, description)
                VALUES (?, ?)
            """, (version, description))
            
            conn.commit()
            logger.info(f"数据库版本更新为: {version}")
            
        except Exception as e:
            logger.error(f"设置数据库版本失败: {e}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()
    
    def backup_database(self) -> str:
        """备份数据库"""
        try:
            backup_dir = Path(__file__).parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"collector_backup_{timestamp}.db"
            
            # 复制数据库文件
            import shutil
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"数据库备份完成: {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            raise
    
    def execute_migration(self, migration_sql: str, version: str, description: str):
        """执行迁移SQL"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 执行迁移SQL
            for statement in migration_sql.split(';'):
                statement = statement.strip()
                if statement:
                    cursor.execute(statement)
            
            conn.commit()
            
            # 更新版本
            self.set_version(version, description)
            
            logger.info(f"迁移完成: {version} - {description}")
            
        except Exception as e:
            logger.error(f"执行迁移失败: {e}")
            if 'conn' in locals():
                conn.rollback()
            raise
        finally:
            if 'conn' in locals():
                conn.close()
    
    def migrate_to_v1_0_0(self):
        """迁移到版本1.0.0 - 初始版本"""
        migration_sql = """
        -- 创建任务记录表
        CREATE TABLE IF NOT EXISTS task_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            collector_id TEXT NOT NULL,
            target_host TEXT NOT NULL,
            target_port INTEGER NOT NULL,
            username TEXT NOT NULL,
            command TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            execution_time REAL,
            result TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- 创建采集器统计表
        CREATE TABLE IF NOT EXISTS collector_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collector_id TEXT NOT NULL,
            date DATE NOT NULL,
            total_tasks INTEGER DEFAULT 0,
            successful_tasks INTEGER DEFAULT 0,
            failed_tasks INTEGER DEFAULT 0,
            avg_execution_time REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(collector_id, date)
        );
        
        -- 创建系统日志表
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            component TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_task_records_collector_id ON task_records(collector_id);
        CREATE INDEX IF NOT EXISTS idx_task_records_status ON task_records(status);
        CREATE INDEX IF NOT EXISTS idx_task_records_created_at ON task_records(created_at);
        CREATE INDEX IF NOT EXISTS idx_collector_stats_collector_id ON collector_stats(collector_id);
        CREATE INDEX IF NOT EXISTS idx_collector_stats_date ON collector_stats(date);
        CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);
        CREATE INDEX IF NOT EXISTS idx_system_logs_component ON system_logs(component);
        CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp);
        """
        
        self.execute_migration(migration_sql, "1.0.0", "初始数据库结构")
    
    def migrate_to_v1_1_0(self):
        """迁移到版本1.1.0 - 添加性能监控"""
        migration_sql = """
        -- 为任务记录表添加性能相关字段
        ALTER TABLE task_records ADD COLUMN cpu_usage REAL DEFAULT 0.0;
        ALTER TABLE task_records ADD COLUMN memory_usage REAL DEFAULT 0.0;
        ALTER TABLE task_records ADD COLUMN network_latency REAL DEFAULT 0.0;
        
        -- 为统计表添加性能统计字段
        ALTER TABLE collector_stats ADD COLUMN avg_cpu_usage REAL DEFAULT 0.0;
        ALTER TABLE collector_stats ADD COLUMN avg_memory_usage REAL DEFAULT 0.0;
        ALTER TABLE collector_stats ADD COLUMN avg_network_latency REAL DEFAULT 0.0;
        """
        
        self.execute_migration(migration_sql, "1.1.0", "添加性能监控字段")
    
    def run_migrations(self):
        """运行所有需要的迁移"""
        current_version = self.get_current_version()
        logger.info(f"当前数据库版本: {current_version}")
        
        # 备份数据库
        if current_version != "0.0.0":
            self.backup_database()
        
        # 定义迁移路径
        migrations = [
            ("1.0.0", self.migrate_to_v1_0_0),
            ("1.1.0", self.migrate_to_v1_1_0),
        ]
        
        # 执行迁移
        for version, migration_func in migrations:
            if self.version_compare(current_version, version) < 0:
                logger.info(f"执行迁移到版本 {version}")
                migration_func()
                current_version = version
        
        logger.info("所有迁移完成")
    
    def version_compare(self, v1: str, v2: str) -> int:
        """比较版本号"""
        def version_tuple(v):
            return tuple(map(int, v.split('.')))
        
        v1_tuple = version_tuple(v1)
        v2_tuple = version_tuple(v2)
        
        if v1_tuple < v2_tuple:
            return -1
        elif v1_tuple > v2_tuple:
            return 1
        else:
            return 0


def export_data(output_file: str):
    """导出数据库数据"""
    try:
        conn = sqlite3.connect(settings.database_path)
        
        # 获取所有表的数据
        tables = ['task_records', 'collector_stats', 'system_logs']
        export_data = {}
        
        for table in tables:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table}")
            
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            export_data[table] = {
                'columns': columns,
                'data': rows
            }
        
        # 保存到JSON文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"数据导出完成: {output_file}")
        
    except Exception as e:
        logger.error(f"数据导出失败: {e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()


def import_data(input_file: str):
    """导入数据库数据"""
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        conn = sqlite3.connect(settings.database_path)
        cursor = conn.cursor()
        
        for table, table_data in import_data.items():
            columns = table_data['columns']
            rows = table_data['data']
            
            # 清空表
            cursor.execute(f"DELETE FROM {table}")
            
            # 插入数据
            placeholders = ','.join(['?' for _ in columns])
            cursor.executemany(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                rows
            )
        
        conn.commit()
        logger.info(f"数据导入完成: {input_file}")
        
    except Exception as e:
        logger.error(f"数据导入失败: {e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移工具")
    parser.add_argument("--migrate", action="store_true", help="执行数据库迁移")
    parser.add_argument("--export", type=str, help="导出数据到文件")
    parser.add_argument("--import", type=str, dest="import_file", help="从文件导入数据")
    parser.add_argument("--version", action="store_true", help="显示当前数据库版本")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("SSH采集器 - 数据库迁移工具")
    print("=" * 60)
    
    migrator = DatabaseMigrator(settings.database_path)
    
    if args.version:
        version = migrator.get_current_version()
        print(f"当前数据库版本: {version}")
        
    elif args.migrate:
        print("开始执行数据库迁移...")
        migrator.run_migrations()
        print("✅ 数据库迁移完成")
        
    elif args.export:
        print(f"导出数据到: {args.export}")
        export_data(args.export)
        print("✅ 数据导出完成")
        
    elif args.import_file:
        print(f"从文件导入数据: {args.import_file}")
        import_data(args.import_file)
        print("✅ 数据导入完成")
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
# SQLite 数据库使用说明

## 概述

SSH采集器现在使用SQLite数据库来存储任务记录、统计信息和系统日志。SQLite是一个轻量级的嵌入式数据库，无需单独的数据库服务器，非常适合本项目的需求。

## 数据库结构

### 表结构

#### 1. task_records (任务记录表)
存储所有SSH采集任务的执行记录。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | 主键，自增 |
| task_id | TEXT | 任务唯一标识符 |
| collector_id | TEXT | 采集器ID |
| target_host | TEXT | 目标主机地址 |
| target_port | INTEGER | 目标端口 |
| username | TEXT | SSH用户名 |
| command | TEXT | 执行的命令 |
| status | TEXT | 任务状态 (pending/running/completed/failed) |
| start_time | TIMESTAMP | 开始时间 |
| end_time | TIMESTAMP | 结束时间 |
| execution_time | REAL | 执行耗时(秒) |
| result | TEXT | 执行结果 |
| error_message | TEXT | 错误信息 |
| retry_count | INTEGER | 重试次数 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### 2. collector_stats (采集器统计表)
存储采集器的每日统计信息。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | 主键，自增 |
| collector_id | TEXT | 采集器ID |
| date | DATE | 统计日期 |
| total_tasks | INTEGER | 总任务数 |
| successful_tasks | INTEGER | 成功任务数 |
| failed_tasks | INTEGER | 失败任务数 |
| avg_execution_time | REAL | 平均执行时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### 3. system_logs (系统日志表)
存储系统运行日志。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | 主键，自增 |
| level | TEXT | 日志级别 (INFO/WARNING/ERROR) |
| component | TEXT | 组件名称 |
| message | TEXT | 日志消息 |
| details | TEXT | 详细信息(JSON格式) |
| timestamp | TIMESTAMP | 时间戳 |

## 数据库操作

### 初始化数据库

首次使用时需要初始化数据库：

```bash
# 初始化数据库和表结构
python scripts/init_database.py
```

### 数据库迁移

当数据库结构需要升级时：

```bash
# 执行数据库迁移
python scripts/migrate_database.py --migrate

# 查看当前数据库版本
python scripts/migrate_database.py --version
```

### 数据备份和恢复

```bash
# 导出数据
python scripts/migrate_database.py --export backup_data.json

# 导入数据
python scripts/migrate_database.py --import backup_data.json
```

## API接口

### 查询任务记录

```http
# 获取任务列表
GET /tasks?limit=10&offset=0&status=completed

# 获取特定任务详情
GET /tasks/{task_id}
```

### 获取统计信息

```http
# 获取采集器统计信息
GET /statistics?days=30
```

## 配置说明

数据库相关配置在 `src/config.py` 中：

```python
# 数据库配置
database_path: str = "data/collector.db"  # 数据库文件路径
```

## 数据库文件位置

默认情况下，数据库文件位于：
```
SSHCollector/
├── data/
│   └── collector.db    # SQLite数据库文件
```

## 性能优化

### 索引

数据库已创建以下索引以提高查询性能：

- `idx_task_records_collector_id`: 按采集器ID查询任务
- `idx_task_records_status`: 按任务状态查询
- `idx_task_records_created_at`: 按创建时间查询
- `idx_collector_stats_collector_id`: 按采集器ID查询统计
- `idx_collector_stats_date`: 按日期查询统计
- `idx_system_logs_level`: 按日志级别查询
- `idx_system_logs_component`: 按组件查询日志
- `idx_system_logs_timestamp`: 按时间戳查询日志

### 数据清理

建议定期清理旧数据以保持数据库性能：

```python
# 清理30天前的任务记录
from src.database import db_manager
from datetime import datetime, timedelta

cutoff_date = datetime.now() - timedelta(days=30)
with db_manager.get_session() as session:
    session.query(TaskRecord).filter(
        TaskRecord.created_at < cutoff_date
    ).delete()
    session.commit()
```

## 故障排除

### 常见问题

1. **数据库文件权限问题**
   ```bash
   chmod 644 data/collector.db
   ```

2. **数据库锁定问题**
   - 确保没有其他进程在使用数据库
   - 重启应用程序

3. **数据库损坏**
   ```bash
   # 检查数据库完整性
   sqlite3 data/collector.db "PRAGMA integrity_check;"
   
   # 如果损坏，从备份恢复
   python scripts/migrate_database.py --import backup_data.json
   ```

### 日志查看

查看数据库相关日志：

```bash
# 查看应用日志
tail -f logs/collector.log | grep -i database
```

## 开发指南

### 添加新表

1. 在 `src/database.py` 中定义新的模型类
2. 在 `scripts/migrate_database.py` 中添加迁移脚本
3. 运行迁移更新数据库结构

### 添加新的查询功能

1. 在 `src/database.py` 中添加查询函数
2. 在 `src/api.py` 中添加对应的API接口
3. 更新文档说明

## 版本历史

- **v1.0.0**: 初始数据库结构
  - 创建基础表结构
  - 添加基本索引
  
- **v1.1.0**: 性能监控增强 (计划中)
  - 添加性能监控字段
  - 增强统计功能
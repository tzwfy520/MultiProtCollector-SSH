# SSH采集器控制器侧设计文档

## 1. 概述

本文档描述了与SSH采集器配套的控制器系统设计，控制器负责管理多个采集器实例，分发采集任务，收集采集结果，并提供统一的管理界面。

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        控制器系统                            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Web管理界面 │  │   API网关   │  │  任务调度器  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ 采集器管理器 │  │ 任务管理器   │  │ 结果处理器   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   数据库    │  │  RabbitMQ   │  │   Redis     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      SSH采集器集群                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  采集器实例1 │  │  采集器实例2 │  │  采集器实例N │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

- **后端框架**: FastAPI / Django
- **数据库**: SQLite (轻量级嵌入式数据库)
- **缓存**: Redis
- **消息队列**: RabbitMQ
- **前端**: Vue.js / React
- **部署**: Docker + Kubernetes

## 3. 核心模块设计

### 3.1 采集器管理器 (Collector Manager)

#### 3.1.1 采集器注册接口

```python
# POST /api/v1/collectors/register
{
    "collector_id": "collector_001",
    "host": "192.168.1.100",
    "port": 8000,
    "version": "1.0.0",
    "capabilities": ["ssh", "telnet"],
    "max_concurrent_tasks": 10,
    "system_info": {
        "cpu_count": 4,
        "memory_total": 8192,
        "disk_total": 100
    }
}

# 响应
{
    "success": true,
    "message": "采集器注册成功",
    "collector_id": "collector_001",
    "assigned_queues": ["task_queue_001"],
    "heartbeat_interval": 3
}
```

#### 3.1.2 心跳处理接口

```python
# POST /api/v1/collectors/{collector_id}/heartbeat
{
    "timestamp": "2024-01-01T12:00:00Z",
    "status": "running",
    "system_info": {
        "cpu_percent": 25.5,
        "memory_percent": 60.2,
        "disk_percent": 45.8
    },
    "active_tasks": 3,
    "completed_tasks": 150,
    "error_count": 2
}

# 响应
{
    "success": true,
    "message": "心跳接收成功",
    "next_heartbeat": 3
}
```

#### 3.1.3 采集器状态管理

```python
class CollectorStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"
    MAINTENANCE = "maintenance"

class Collector(BaseModel):
    collector_id: str
    host: str
    port: int
    status: CollectorStatus
    last_heartbeat: datetime
    version: str
    capabilities: List[str]
    max_concurrent_tasks: int
    current_tasks: int
    total_completed: int
    total_errors: int
    system_info: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

### 3.2 任务管理器 (Task Manager)

#### 3.2.1 任务模型设计

```python
class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class CollectionTask(BaseModel):
    task_id: str
    task_type: str  # "simple", "batch", "scheduled"
    priority: int  # 1-10, 10为最高优先级
    status: TaskStatus
    assigned_collector: Optional[str]
    
    # 目标设备信息
    target_devices: List[Dict[str, Any]]
    
    # SSH凭据
    credentials: Dict[str, Any]
    
    # 执行命令
    commands: List[Dict[str, Any]]
    
    # 任务配置
    timeout: int
    retry_count: int
    
    # 调度信息
    scheduled_time: Optional[datetime]
    created_by: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    # 结果信息
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
```

#### 3.2.2 任务分发策略

```python
class TaskDispatcher:
    """任务分发器"""
    
    def select_collector(self, task: CollectionTask) -> Optional[str]:
        """选择最适合的采集器"""
        available_collectors = self.get_available_collectors()
        
        # 负载均衡策略
        if task.priority >= 8:
            # 高优先级任务选择负载最低的采集器
            return self.select_by_load(available_collectors)
        else:
            # 普通任务轮询分配
            return self.select_round_robin(available_collectors)
    
    def get_available_collectors(self) -> List[Collector]:
        """获取可用的采集器"""
        return [
            collector for collector in self.collectors
            if collector.status == CollectorStatus.ONLINE
            and collector.current_tasks < collector.max_concurrent_tasks
        ]
```

#### 3.2.3 任务队列设计

```python
# RabbitMQ队列配置
QUEUE_CONFIG = {
    "task_queue": {
        "durable": True,
        "auto_delete": False,
        "arguments": {
            "x-message-ttl": 3600000,  # 1小时TTL
            "x-max-priority": 10       # 支持优先级
        }
    },
    "result_queue": {
        "durable": True,
        "auto_delete": False
    },
    "heartbeat_queue": {
        "durable": False,
        "auto_delete": True
    }
}

# 任务消息格式
{
    "task_id": "task_123456789",
    "priority": 5,
    "credentials": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "admin",
        "password": "encrypted_password",
        "device_type": "cisco_ios"
    },
    "commands": [
        {
            "command": "show version",
            "delay_factor": 1.0
        }
    ],
    "timeout": 300,
    "retry_count": 3,
    "callback_url": "http://controller/api/v1/tasks/callback"
}
```

### 3.3 结果处理器 (Result Processor)

#### 3.3.1 结果接收接口

```python
# POST /api/v1/tasks/{task_id}/result
{
    "task_id": "task_123456789",
    "collector_id": "collector_001",
    "success": true,
    "execution_time": 5.23,
    "timestamp": "2024-01-01T12:00:00Z",
    "data": {
        "commands": [
            {
                "command": "show version",
                "output": "Cisco IOS Software...",
                "success": true,
                "execution_time": 2.1
            }
        ]
    },
    "error": null
}
```

#### 3.3.2 结果存储设计

```python
class TaskResult(BaseModel):
    result_id: str
    task_id: str
    collector_id: str
    success: bool
    execution_time: float
    timestamp: datetime
    
    # 原始数据
    raw_data: Dict[str, Any]
    
    # 解析后的结构化数据
    parsed_data: Optional[Dict[str, Any]]
    
    # 错误信息
    error_message: Optional[str]
    error_code: Optional[str]
    
    # 存储路径（大数据存储）
    storage_path: Optional[str]
    
    created_at: datetime
```

### 3.4 数据库设计

#### 3.4.1 核心表结构

```sql
-- 采集器表
CREATE TABLE collectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id TEXT UNIQUE NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    status TEXT NOT NULL,
    version TEXT,
    capabilities TEXT, -- JSON格式存储
    max_concurrent_tasks INTEGER DEFAULT 10,
    current_tasks INTEGER DEFAULT 0,
    total_completed INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    system_info TEXT, -- JSON格式存储
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 任务表
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    task_type TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL,
    assigned_collector TEXT,
    target_devices TEXT, -- JSON格式存储
    credentials TEXT, -- JSON格式存储
    commands TEXT, -- JSON格式存储
    timeout INTEGER DEFAULT 300,
    retry_count INTEGER DEFAULT 3,
    scheduled_time TIMESTAMP,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result TEXT, -- JSON格式存储
    error_message TEXT
);

-- 结果表
CREATE TABLE task_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT UNIQUE NOT NULL,
    task_id TEXT NOT NULL,
    collector_id TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    execution_time REAL,
    timestamp TIMESTAMP NOT NULL,
    raw_data TEXT, -- JSON格式存储
    parsed_data TEXT, -- JSON格式存储
    error_message TEXT,
    error_code TEXT,
    storage_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

-- 心跳记录表
CREATE TABLE heartbeat_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    status TEXT NOT NULL,
    system_info TEXT, -- JSON格式存储
    active_tasks INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引以提高查询性能
CREATE INDEX idx_collectors_collector_id ON collectors(collector_id);
CREATE INDEX idx_collectors_status ON collectors(status);
CREATE INDEX idx_tasks_task_id ON tasks(task_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assigned_collector ON tasks(assigned_collector);
CREATE INDEX idx_task_results_task_id ON task_results(task_id);
CREATE INDEX idx_task_results_collector_id ON task_results(collector_id);
CREATE INDEX idx_heartbeat_logs_collector_id ON heartbeat_logs(collector_id);
```

## 4. API接口设计

### 4.1 采集器管理接口

```python
# 获取采集器列表
GET /api/v1/collectors
# 获取采集器详情
GET /api/v1/collectors/{collector_id}
# 采集器注册
POST /api/v1/collectors/register
# 心跳上报
POST /api/v1/collectors/{collector_id}/heartbeat
# 采集器下线
DELETE /api/v1/collectors/{collector_id}
```

### 4.2 任务管理接口

```python
# 创建任务
POST /api/v1/tasks
# 获取任务列表
GET /api/v1/tasks
# 获取任务详情
GET /api/v1/tasks/{task_id}
# 取消任务
DELETE /api/v1/tasks/{task_id}
# 任务结果回调
POST /api/v1/tasks/{task_id}/result
```

### 4.3 监控接口

```python
# 系统状态
GET /api/v1/status
# 采集器统计
GET /api/v1/statistics/collectors
# 任务统计
GET /api/v1/statistics/tasks
# 性能指标
GET /api/v1/metrics
```

## 5. 部署架构

### 5.1 Docker Compose部署

```yaml
version: '3.8'
services:
  controller:
    build: .
    ports:
      - "8080:8080"
    environment:
      - DATABASE_PATH=/app/data/controller.db
      - REDIS_URL=redis://redis:6379
      - RABBITMQ_URL=amqp://user:pass@rabbitmq:5672
    volumes:
      - controller_data:/app/data
    depends_on:
      - redis
      - rabbitmq

  redis:
    image: redis:6-alpine
    volumes:
      - redis_data:/data

  rabbitmq:
    image: rabbitmq:3-management
    environment:
      - RABBITMQ_DEFAULT_USER=user
      - RABBITMQ_DEFAULT_PASS=pass
    ports:
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

volumes:
  controller_data:
  redis_data:
  rabbitmq_data:
```

### 5.2 Kubernetes部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ssh-controller
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ssh-controller
  template:
    metadata:
      labels:
        app: ssh-controller
    spec:
      containers:
      - name: controller
        image: ssh-controller:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_PATH
          value: "/app/data/controller.db"
        - name: REDIS_URL
          value: "redis://redis:6379"
        - name: RABBITMQ_URL
          valueFrom:
            secretKeyRef:
              name: controller-secrets
              key: rabbitmq-url
        volumeMounts:
        - name: controller-data
          mountPath: /app/data
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
```

## 6. 安全设计

### 6.1 认证授权

- JWT Token认证
- RBAC权限控制
- API密钥管理
- 采集器证书认证

### 6.2 数据安全

- SSH凭据加密存储
- 传输数据TLS加密
- 敏感数据脱敏
- 审计日志记录

## 7. 监控告警

### 7.1 监控指标

- 采集器在线状态
- 任务执行成功率
- 系统资源使用率
- 接口响应时间

### 7.2 告警规则

- 采集器离线告警
- 任务失败率过高告警
- 系统资源不足告警
- 接口异常告警

## 8. 扩展性设计

### 8.1 水平扩展

- 控制器集群部署
- 数据库读写分离
- 缓存集群
- 消息队列集群

### 8.2 插件机制

- 自定义任务类型
- 结果解析插件
- 通知插件
- 存储插件

## 9. 开发计划

### 9.1 第一阶段（核心功能）

- [ ] 采集器注册管理
- [ ] 心跳检测机制
- [ ] 任务分发调度
- [ ] 结果收集处理

### 9.2 第二阶段（管理功能）

- [ ] Web管理界面
- [ ] 用户权限管理
- [ ] 任务模板管理
- [ ] 统计报表功能

### 9.3 第三阶段（高级功能）

- [ ] 任务编排引擎
- [ ] 智能调度算法
- [ ] 实时监控大屏
- [ ] 自动化运维

## 10. 总结

本设计文档提供了与SSH采集器配套的控制器系统完整设计方案，涵盖了架构设计、接口定义、数据库设计、部署方案等各个方面。控制器系统将为SSH采集器提供统一的管理平台，实现采集任务的自动化分发和结果收集，提高运维效率。
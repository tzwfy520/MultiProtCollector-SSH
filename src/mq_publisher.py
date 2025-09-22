"""
RabbitMQ发布者模块
用于发送采集结果到控制器
"""
import json
import pika
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from .config import settings
from .utils import logger, CollectorException, handle_exception


class MQPublishException(CollectorException):
    """MQ发布异常"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "MQ_PUBLISH_ERROR", details)


class RabbitMQPublisher:
    """RabbitMQ发布者"""
    
    def __init__(self):
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self.connected = False
    
    @handle_exception
    def connect(self):
        """连接到RabbitMQ"""
        try:
            # 连接参数
            credentials = pika.PlainCredentials(
                settings.rabbitmq_username,
                settings.rabbitmq_password
            )
            
            parameters = pika.ConnectionParameters(
                host=settings.rabbitmq_host,
                port=settings.rabbitmq_port,
                virtual_host=settings.rabbitmq_vhost,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            logger.info(f"正在连接到RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
            
            # 建立连接
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # 声明结果队列
            self.channel.queue_declare(
                queue=settings.result_queue,
                durable=True,
                exclusive=False,
                auto_delete=False
            )
            
            self.connected = True
            logger.info("RabbitMQ连接成功")
            
        except Exception as e:
            error_msg = f"RabbitMQ连接失败: {str(e)}"
            logger.error(error_msg)
            raise MQPublishException(error_msg, details={"connection_error": str(e)})
    
    def disconnect(self):
        """断开RabbitMQ连接"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("RabbitMQ连接已断开")
        except Exception as e:
            logger.warning(f"断开RabbitMQ连接时发生错误: {str(e)}")
        finally:
            self.connection = None
            self.channel = None
            self.connected = False
    
    @handle_exception
    def publish_result(self, result: Dict[str, Any], routing_key: str = None) -> bool:
        """发布采集结果"""
        if not self.connected:
            self.connect()
        
        try:
            # 准备消息
            message = {
                "collector_id": settings.collector_id,
                "timestamp": datetime.now().isoformat(),
                "result": result
            }
            
            # 序列化消息
            message_body = json.dumps(message, ensure_ascii=False, indent=None)
            
            # 发布消息
            self.channel.basic_publish(
                exchange='',
                routing_key=routing_key or settings.result_queue,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 持久化消息
                    content_type='application/json',
                    timestamp=int(datetime.now().timestamp())
                )
            )
            
            logger.debug(f"采集结果已发布到队列: {routing_key or settings.result_queue}")
            return True
            
        except Exception as e:
            error_msg = f"发布采集结果失败: {str(e)}"
            logger.error(error_msg)
            
            # 尝试重新连接
            try:
                self.disconnect()
                self.connect()
                return self.publish_result(result, routing_key)
            except Exception as reconnect_error:
                logger.error(f"重新连接失败: {str(reconnect_error)}")
                raise MQPublishException(error_msg, details={"publish_error": str(e)})
    
    @handle_exception
    def publish_task_result(self, task_id: str, success: bool, data: Any = None, error: str = None) -> bool:
        """发布任务执行结果"""
        result = {
            "task_id": task_id,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        
        if success and data is not None:
            result["data"] = data
        
        if not success and error:
            result["error"] = error
        
        return self.publish_result(result)
    
    @handle_exception
    def publish_status_update(self, status: str, details: Dict[str, Any] = None) -> bool:
        """发布状态更新"""
        result = {
            "type": "status_update",
            "status": status,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        
        return self.publish_result(result)
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()


class AsyncRabbitMQPublisher:
    """异步RabbitMQ发布者（用于与FastAPI集成）"""
    
    def __init__(self):
        self.publisher = RabbitMQPublisher()
        self._lock = asyncio.Lock()
    
    async def publish_result(self, result: Dict[str, Any], routing_key: str = None) -> bool:
        """异步发布采集结果"""
        async with self._lock:
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.publisher.publish_result,
                result,
                routing_key
            )
    
    async def publish_task_result(self, task_id: str, success: bool, data: Any = None, error: str = None) -> bool:
        """异步发布任务执行结果"""
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.publisher.publish_task_result,
                task_id,
                success,
                data,
                error
            )
    
    async def publish_status_update(self, status: str, details: Dict[str, Any] = None) -> bool:
        """异步发布状态更新"""
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.publisher.publish_status_update,
                status,
                details
            )
    
    async def connect(self):
        """异步连接"""
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.publisher.connect)
    
    async def disconnect(self):
        """异步断开连接"""
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.publisher.disconnect)


# 全局发布者实例
mq_publisher = RabbitMQPublisher()
async_mq_publisher = AsyncRabbitMQPublisher()
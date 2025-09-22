"""
RabbitMQ消费者模块
用于接收和处理控制器分发的采集任务
"""
import json
import pika
import asyncio
import threading
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from .config import settings
from .utils import logger, CollectorException, handle_exception
from .ssh_core import ssh_collector, CollectionTask, SSHCredentials, SSHCommand
from .mq_publisher import mq_publisher


class MQConsumeException(CollectorException):
    """MQ消费异常"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "MQ_CONSUME_ERROR", details)


class TaskProcessor:
    """任务处理器"""
    
    def __init__(self):
        self.processing_tasks = set()
    
    @handle_exception
    def process_collection_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理采集任务"""
        try:
            # 解析任务数据
            task_id = task_data.get("task_id")
            if not task_id:
                raise ValueError("任务ID不能为空")
            
            # 避免重复处理
            if task_id in self.processing_tasks:
                logger.warning(f"任务 {task_id} 正在处理中，跳过")
                return {"success": False, "error": "任务正在处理中"}
            
            self.processing_tasks.add(task_id)
            
            try:
                logger.info(f"开始处理采集任务: {task_id}")
                
                # 构建SSH凭据
                credentials_data = task_data.get("credentials", {})
                credentials = SSHCredentials(**credentials_data)
                
                # 构建SSH命令列表
                commands_data = task_data.get("commands", [])
                commands = [SSHCommand(**cmd) for cmd in commands_data]
                
                # 构建采集任务
                task = CollectionTask(
                    task_id=task_id,
                    credentials=credentials,
                    commands=commands,
                    timeout=task_data.get("timeout", 300),
                    retry_count=task_data.get("retry_count", 3)
                )
                
                # 执行采集任务
                result = ssh_collector.collect_with_retry(task)
                
                logger.info(f"采集任务 {task_id} 处理完成，成功: {result['success']}")
                return result
                
            finally:
                self.processing_tasks.discard(task_id)
                
        except Exception as e:
            error_msg = f"处理采集任务失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "task_id": task_data.get("task_id", "unknown")
            }


class RabbitMQConsumer:
    """RabbitMQ消费者"""
    
    def __init__(self):
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self.connected = False
        self.consuming = False
        self.task_processor = TaskProcessor()
        self._stop_event = threading.Event()
    
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
            
            # 声明任务队列
            self.channel.queue_declare(
                queue=settings.task_queue,
                durable=True,
                exclusive=False,
                auto_delete=False
            )
            
            # 设置QoS，一次只处理一个消息
            self.channel.basic_qos(prefetch_count=1)
            
            self.connected = True
            logger.info("RabbitMQ消费者连接成功")
            
        except Exception as e:
            error_msg = f"RabbitMQ消费者连接失败: {str(e)}"
            logger.error(error_msg)
            raise MQConsumeException(error_msg, details={"connection_error": str(e)})
    
    def disconnect(self):
        """断开RabbitMQ连接"""
        try:
            self.consuming = False
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("RabbitMQ消费者连接已断开")
        except Exception as e:
            logger.warning(f"断开RabbitMQ消费者连接时发生错误: {str(e)}")
        finally:
            self.connection = None
            self.channel = None
            self.connected = False
    
    def _message_callback(self, channel, method, properties, body):
        """消息回调处理函数"""
        try:
            # 解析消息
            message = json.loads(body.decode('utf-8'))
            logger.debug(f"收到任务消息: {message.get('task_id', 'unknown')}")
            
            # 处理任务
            result = self.task_processor.process_collection_task(message)
            
            # 发布结果
            try:
                mq_publisher.publish_task_result(
                    task_id=result.get("task_id", message.get("task_id", "unknown")),
                    success=result["success"],
                    data=result.get("data"),
                    error=result.get("error")
                )
            except Exception as publish_error:
                logger.error(f"发布任务结果失败: {str(publish_error)}")
            
            # 确认消息
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.debug(f"任务消息处理完成: {message.get('task_id', 'unknown')}")
            
        except json.JSONDecodeError as e:
            logger.error(f"消息格式错误: {str(e)}")
            # 拒绝消息，不重新入队
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error(f"处理消息时发生错误: {str(e)}")
            # 拒绝消息，重新入队
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    @handle_exception
    def start_consuming(self):
        """开始消费消息"""
        if not self.connected:
            self.connect()
        
        if self.consuming:
            logger.warning("消费者已在运行")
            return
        
        try:
            logger.info(f"开始消费队列: {settings.task_queue}")
            
            # 设置消息回调
            self.channel.basic_consume(
                queue=settings.task_queue,
                on_message_callback=self._message_callback
            )
            
            self.consuming = True
            
            # 开始消费（阻塞）
            while self.consuming and not self._stop_event.is_set():
                try:
                    self.connection.process_data_events(time_limit=1)
                except Exception as e:
                    logger.error(f"处理消息事件时发生错误: {str(e)}")
                    # 尝试重新连接
                    try:
                        self.disconnect()
                        self.connect()
                        self.channel.basic_consume(
                            queue=settings.task_queue,
                            on_message_callback=self._message_callback
                        )
                    except Exception as reconnect_error:
                        logger.error(f"重新连接失败: {str(reconnect_error)}")
                        break
            
            logger.info("消息消费已停止")
            
        except Exception as e:
            error_msg = f"消费消息失败: {str(e)}"
            logger.error(error_msg)
            raise MQConsumeException(error_msg, details={"consume_error": str(e)})
        finally:
            self.consuming = False
    
    def stop_consuming(self):
        """停止消费消息"""
        logger.info("正在停止消息消费")
        self.consuming = False
        self._stop_event.set()
        
        if self.channel:
            try:
                self.channel.stop_consuming()
            except Exception as e:
                logger.warning(f"停止消费时发生错误: {str(e)}")


class AsyncMQConsumer:
    """异步MQ消费者管理器"""
    
    def __init__(self):
        self.consumer = RabbitMQConsumer()
        self.consumer_thread: Optional[threading.Thread] = None
        self.running = False
    
    async def start(self):
        """启动异步消费者"""
        if self.running:
            logger.warning("异步消费者已在运行")
            return
        
        self.running = True
        logger.info("启动异步MQ消费者")
        
        # 在单独线程中运行消费者
        self.consumer_thread = threading.Thread(
            target=self._run_consumer,
            name="MQConsumerThread",
            daemon=True
        )
        self.consumer_thread.start()
    
    async def stop(self):
        """停止异步消费者"""
        if not self.running:
            return
        
        self.running = False
        logger.info("停止异步MQ消费者")
        
        # 停止消费者
        self.consumer.stop_consuming()
        
        # 等待线程结束
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=10)
        
        # 断开连接
        self.consumer.disconnect()
    
    def _run_consumer(self):
        """在线程中运行消费者"""
        try:
            self.consumer.start_consuming()
        except Exception as e:
            logger.error(f"消费者线程异常: {str(e)}")
        finally:
            self.running = False
    
    def is_running(self) -> bool:
        """检查消费者是否在运行"""
        return self.running and self.consumer.consuming


# 全局消费者实例
mq_consumer = RabbitMQConsumer()
async_mq_consumer = AsyncMQConsumer()
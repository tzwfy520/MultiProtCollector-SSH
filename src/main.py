"""
SSH采集器主入口文件
整合所有模块并启动服务
"""
import asyncio
import signal
import sys
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any

from .config import settings
from .utils import logger, CollectorException
from .registration import registration_manager
from .mq_consumer import async_mq_consumer
from .mq_publisher import mq_publisher
from .api import app


class SSHCollectorService:
    """SSH采集器服务管理器"""
    
    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()
        
    async def startup(self):
        """启动服务"""
        try:
            logger.info("=" * 60)
            logger.info("SSH采集器启动中...")
            logger.info(f"采集器ID: {settings.collector_id}")
            logger.info(f"服务端口: {settings.service_port}")
            logger.info(f"控制器地址: {settings.controller_host}:{settings.controller_port}")
            logger.info("=" * 60)
            
            # 1. 初始化MQ发布者
            logger.info("初始化MQ发布者...")
            await self._init_mq_publisher()
            
            # 2. 启动MQ消费者
            logger.info("启动MQ消费者...")
            await async_mq_consumer.start()
            
            # 3. 注册到控制器
            logger.info("注册到控制器...")
            await registration_manager.start()
            
            self.running = True
            logger.info("SSH采集器启动完成！")
            
        except Exception as e:
            logger.error(f"启动服务失败: {str(e)}")
            await self.shutdown()
            raise
    
    async def shutdown(self):
        """关闭服务"""
        if not self.running:
            return
            
        logger.info("SSH采集器关闭中...")
        self.running = False
        
        try:
            # 1. 停止心跳检测
            logger.info("停止心跳检测...")
            await registration_manager.stop_heartbeat()
            
            # 2. 停止MQ消费者
            logger.info("停止MQ消费者...")
            await async_mq_consumer.stop()
            
            # 3. 断开MQ发布者连接
            logger.info("断开MQ发布者连接...")
            mq_publisher.disconnect()
            
            logger.info("SSH采集器已关闭")
            
        except Exception as e:
            logger.error(f"关闭服务时发生错误: {str(e)}")
        
        finally:
            self.shutdown_event.set()
    
    async def _init_mq_publisher(self):
        """初始化MQ发布者"""
        try:
            mq_publisher.connect()
            logger.info("MQ发布者初始化成功")
        except Exception as e:
            logger.error(f"MQ发布者初始化失败: {str(e)}")
            # MQ发布者失败不阻止服务启动，但会记录错误
    
    async def _register_to_controller(self):
        """注册到控制器"""
        try:
            await registration_manager.register()
            logger.info("控制器注册成功")
        except Exception as e:
            logger.error(f"控制器注册失败: {str(e)}")
            # 注册失败不阻止服务启动，但会记录错误
    
    def setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，开始关闭服务...")
            asyncio.create_task(self.shutdown())
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)


# 全局服务实例
collector_service = SSHCollectorService()


@asynccontextmanager
async def lifespan(app):
    """FastAPI生命周期管理"""
    # 启动
    await collector_service.startup()
    
    try:
        yield
    finally:
        # 关闭
        await collector_service.shutdown()


# 将生命周期管理器绑定到FastAPI应用
app.router.lifespan_context = lifespan


async def run_server():
    """运行服务器"""
    try:
        # 设置信号处理器
        collector_service.setup_signal_handlers()
        
        # 配置uvicorn
        config = uvicorn.Config(
            app=app,
            host=settings.service_host,
            port=settings.service_port,
            log_level="info",
            access_log=True,
            reload=False,
            workers=1
        )
        
        server = uvicorn.Server(config)
        
        # 启动服务器
        logger.info(f"启动HTTP服务器: http://{settings.service_host}:{settings.service_port}")
        await server.serve()
        
    except Exception as e:
        logger.error(f"运行服务器失败: {str(e)}")
        raise
    finally:
        # 确保服务正确关闭
        await collector_service.shutdown()


def main():
    """主函数"""
    try:
        # 显示启动信息
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    SSH采集器 v{settings.app_version}                     ║
║                                                              ║
║  采集器ID: {settings.collector_id:<47} ║
║  服务地址: http://{settings.service_host}:{settings.service_port:<39} ║
║  控制器:   {settings.controller_host}:{settings.controller_port:<47} ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
        # 运行异步服务
        asyncio.run(run_server())
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"服务运行异常: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("服务已退出")


if __name__ == "__main__":
    main()
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
from .database import database_manager
from .api import app
from .xxl_job.executor import xxl_job_executor
from .xxl_job.client import xxl_job_client


class SSHCollectorService:
    """SSH采集器服务管理器"""
    
    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()
        
    async def startup(self):
        """启动服务"""
        try:
            logger.info("启动SSH采集器服务...")
            
            # 初始化数据库
            logger.info("初始化数据库...")
            await database_manager.init_database()
            
            # 启动XXL-Job执行器
            logger.info("启动XXL-Job执行器...")
            await xxl_job_executor.start_server()
            
            # 注册到XXL-Job调度中心
            logger.info("注册到XXL-Job调度中心...")
            await xxl_job_client.register_executor()
            
            # 注册到控制器
            logger.info("注册到控制器...")
            await registration_manager.register()
            
            self.running = True
            logger.info("SSH采集器服务启动完成")
            
        except Exception as e:
            logger.error(f"服务启动失败: {e}")
            raise CollectorException(f"服务启动失败: {e}")
            raise
    
    async def shutdown(self):
        """关闭服务"""
        try:
            logger.info("开始关闭SSH采集器服务...")
            self.running = False
            
            # 注销XXL-Job执行器
            logger.info("注销XXL-Job执行器...")
            await xxl_job_client.unregister_executor()
            
            # 停止XXL-Job执行器
            logger.info("停止XXL-Job执行器...")
            await xxl_job_executor.stop_server()
            
            # 从控制器注销
            logger.info("从控制器注销...")
            await registration_manager.unregister()
            
            # 关闭数据库连接
            logger.info("关闭数据库连接...")
            await database_manager.close()
            
            logger.info("SSH采集器服务已关闭")
            
        except Exception as e:
            logger.error(f"关闭服务时发生错误: {e}")
        finally:
            self.shutdown_event.set()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，准备关闭服务...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


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
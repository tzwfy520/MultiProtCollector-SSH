"""
控制器注册和心跳检测模块
实现采集器与控制器的注册和状态监控
"""
import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional
from datetime import datetime
from .config import settings
from .utils import logger, SystemMonitor, CollectorException, handle_exception


class RegistrationException(CollectorException):
    """注册异常"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "REGISTRATION_ERROR", details)


class HeartbeatException(CollectorException):
    """心跳异常"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "HEARTBEAT_ERROR", details)


class ControllerClient:
    """控制器客户端"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.registered = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.controller_base_url = f"http://{settings.controller_host}:{settings.controller_port}"
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def register(self) -> bool:
        """向控制器注册采集器"""
        try:
            registration_data = {
                "collector_id": settings.collector_id,
                "collector_name": settings.collector_name,
                "version": settings.app_version,
                "host": settings.host,
                "port": settings.port,
                "capabilities": {
                    "ssh_collection": True,
                    "supported_device_types": ["linux", "cisco_ios", "cisco_nxos", "juniper", "huawei"],
                    "max_concurrent_tasks": 10
                },
                "system_info": SystemMonitor.get_system_info(),
                "registration_time": datetime.now().isoformat()
            }
            
            url = f"{self.controller_base_url}{settings.controller_register_url}"
            logger.info(f"正在向控制器注册: {url}")
            
            async with self.session.post(url, json=registration_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"采集器注册成功: {result}")
                    self.registered = True
                    return True
                else:
                    error_text = await response.text()
                    raise RegistrationException(
                        f"注册失败，HTTP状态码: {response.status}",
                        details={"status_code": response.status, "response": error_text}
                    )
                    
        except aiohttp.ClientError as e:
            error_msg = f"注册请求失败: {str(e)}"
            logger.error(error_msg)
            raise RegistrationException(error_msg, details={"client_error": str(e)})
        
        except Exception as e:
            error_msg = f"注册过程中发生未知错误: {str(e)}"
            logger.error(error_msg)
            raise RegistrationException(error_msg, details={"unknown_error": str(e)})
    
    @handle_exception
    async def send_heartbeat(self) -> bool:
        """发送心跳报文"""
        if not self.registered:
            logger.warning("采集器未注册，跳过心跳发送")
            return False
        
        try:
            heartbeat_data = {
                "collector_id": settings.collector_id,
                "timestamp": datetime.now().isoformat(),
                "status": "running",
                "system_info": SystemMonitor.get_system_info()
            }
            
            url = f"{self.controller_base_url}{settings.controller_heartbeat_url}"
            
            async with self.session.post(url, json=heartbeat_data) as response:
                if response.status == 200:
                    logger.debug("心跳发送成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.warning(f"心跳发送失败，HTTP状态码: {response.status}, 响应: {error_text}")
                    return False
                    
        except aiohttp.ClientError as e:
            logger.warning(f"心跳请求失败: {str(e)}")
            return False
        
        except Exception as e:
            logger.error(f"心跳发送过程中发生未知错误: {str(e)}")
            return False
    
    async def start_heartbeat(self):
        """启动心跳任务"""
        if self.heartbeat_task and not self.heartbeat_task.done():
            logger.warning("心跳任务已在运行")
            return
        
        logger.info(f"启动心跳任务，间隔: {settings.heartbeat_interval}秒")
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def stop_heartbeat(self):
        """停止心跳任务"""
        if self.heartbeat_task and not self.heartbeat_task.done():
            logger.info("停止心跳任务")
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        consecutive_failures = 0
        max_failures = 3
        
        while True:
            try:
                success = await self.send_heartbeat()
                
                if success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    logger.warning(f"心跳发送失败，连续失败次数: {consecutive_failures}")
                
                # 如果连续失败次数达到阈值，尝试重新注册
                if consecutive_failures >= max_failures:
                    logger.error(f"心跳连续失败 {max_failures} 次，尝试重新注册")
                    try:
                        await self.register()
                        consecutive_failures = 0
                    except Exception as e:
                        logger.error(f"重新注册失败: {str(e)}")
                
                # 等待下次心跳
                await asyncio.sleep(settings.heartbeat_interval)
                
            except asyncio.CancelledError:
                logger.info("心跳任务被取消")
                break
            except Exception as e:
                logger.error(f"心跳循环中发生未知错误: {str(e)}")
                consecutive_failures += 1
                await asyncio.sleep(settings.heartbeat_interval)


class RegistrationManager:
    """注册管理器"""
    
    def __init__(self):
        self.client: Optional[ControllerClient] = None
        self._running = False
    
    async def start(self):
        """启动注册管理器"""
        if self._running:
            logger.warning("注册管理器已在运行")
            return
        
        self._running = True
        logger.info("启动注册管理器")
        
        try:
            self.client = ControllerClient()
            await self.client.__aenter__()
            
            # 尝试注册
            max_register_attempts = 5
            register_attempt = 0
            
            while register_attempt < max_register_attempts and self._running:
                try:
                    await self.client.register()
                    break
                except Exception as e:
                    register_attempt += 1
                    logger.error(f"注册失败 (尝试 {register_attempt}/{max_register_attempts}): {str(e)}")
                    
                    if register_attempt < max_register_attempts:
                        wait_time = min(30, 5 * register_attempt)  # 指数退避，最大30秒
                        logger.info(f"等待 {wait_time} 秒后重试注册")
                        await asyncio.sleep(wait_time)
            
            if not self.client.registered:
                logger.warning("达到最大注册尝试次数，控制器可能不可用，但继续启动服务")
                # 不抛出异常，允许服务继续启动
                return
            
            # 启动心跳
            await self.client.start_heartbeat()
            
        except RegistrationException as e:
            # 注册异常不影响服务启动
            logger.warning(f"注册管理器启动失败，但服务继续运行: {str(e)}")
            await self.stop()
        except Exception as e:
            logger.error(f"启动注册管理器失败: {str(e)}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止注册管理器"""
        if not self._running:
            return
        
        self._running = False
        logger.info("停止注册管理器")
        
        if self.client:
            try:
                await self.client.stop_heartbeat()
                await self.client.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"停止注册管理器时发生错误: {str(e)}")
            finally:
                self.client = None
    
    def is_registered(self) -> bool:
        """检查是否已注册"""
        return self.client and self.client.registered if self.client else False
    
    async def get_status(self) -> Dict[str, Any]:
        """获取注册状态"""
        return {
            "running": self._running,
            "registered": self.is_registered(),
            "collector_id": settings.collector_id,
            "controller_url": f"http://{settings.controller_host}:{settings.controller_port}",
            "heartbeat_interval": settings.heartbeat_interval
        }


# 全局注册管理器实例
registration_manager = RegistrationManager()
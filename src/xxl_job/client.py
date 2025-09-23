"""
XXL-Job客户端
负责与XXL-Job调度中心的HTTP通信
"""

import asyncio
import json
import logging
import socket
from typing import Dict, Any, Optional
from datetime import datetime

import aiohttp
from ..config import settings
from ..utils import logger


class XXLJobClient:
    """XXL-Job客户端"""
    
    def __init__(self):
        """初始化XXL-Job客户端"""
        self.admin_addresses = settings.xxl_job_admin_addresses
        self.access_token = settings.xxl_job_access_token
        self.app_name = settings.xxl_job_executor_app_name
        self.executor_address = settings.xxl_job_executor_address
        self.executor_ip = settings.xxl_job_executor_ip or self._get_local_ip()
        self.executor_port = settings.xxl_job_executor_port
        self.session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._registered = False
        
    def _get_local_ip(self) -> str:
        """获取本机IP地址"""
        try:
            # 创建一个UDP socket连接到外部地址来获取本机IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """发送HTTP请求到XXL-Job调度中心"""
        session = await self._get_session()
        
        # 添加访问令牌
        if self.access_token:
            data['accessToken'] = self.access_token
            
        url = f"{self.admin_addresses.rstrip('/')}/api/{endpoint}"
        
        try:
            async with session.post(url, json=data) as response:
                result = await response.json()
                logger.debug(f"XXL-Job API调用: {endpoint}, 响应: {result}")
                return result
        except Exception as e:
            logger.error(f"XXL-Job API调用失败: {endpoint}, 错误: {e}")
            raise
    
    async def register_executor(self) -> bool:
        """注册执行器到调度中心"""
        try:
            # 构建执行器地址
            if not self.executor_address:
                self.executor_address = f"http://{self.executor_ip}:{self.executor_port}"
            
            data = {
                "registryGroup": "EXECUTOR",
                "registryKey": self.app_name,
                "registryValue": self.executor_address
            }
            
            result = await self._make_request("registry", data)
            
            if result.get("code") == 200:
                self._registered = True
                logger.info(f"XXL-Job执行器注册成功: {self.executor_address}")
                
                # 启动心跳任务
                await self._start_heartbeat()
                return True
            else:
                logger.error(f"XXL-Job执行器注册失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"注册执行器时发生错误: {e}")
            return False
    
    async def unregister_executor(self) -> bool:
        """从调度中心注销执行器"""
        try:
            # 停止心跳任务
            await self._stop_heartbeat()
            
            if not self._registered:
                return True
                
            data = {
                "registryGroup": "EXECUTOR",
                "registryKey": self.app_name,
                "registryValue": self.executor_address
            }
            
            result = await self._make_request("registryRemove", data)
            
            if result.get("code") == 200:
                self._registered = False
                logger.info("XXL-Job执行器注销成功")
                return True
            else:
                logger.error(f"XXL-Job执行器注销失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"注销执行器时发生错误: {e}")
            return False
        finally:
            # 关闭HTTP会话
            if self.session and not self.session.closed:
                await self.session.close()
    
    async def _start_heartbeat(self):
        """启动心跳任务"""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _stop_heartbeat(self):
        """停止心跳任务"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._registered:
            try:
                await self.heartbeat()
                await asyncio.sleep(30)  # 每30秒发送一次心跳
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                await asyncio.sleep(10)  # 失败后等待10秒重试
    
    async def heartbeat(self) -> bool:
        """发送心跳到调度中心"""
        try:
            data = {
                "registryGroup": "EXECUTOR",
                "registryKey": self.app_name,
                "registryValue": self.executor_address
            }
            
            result = await self._make_request("registry", data)
            
            if result.get("code") == 200:
                logger.debug("XXL-Job心跳发送成功")
                return True
            else:
                logger.warning(f"XXL-Job心跳发送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"发送心跳时发生错误: {e}")
            return False
    
    async def callback_task_result(self, task_id: str, result: Dict[str, Any]) -> bool:
        """回调任务执行结果"""
        try:
            callback_data = {
                "logId": task_id,
                "logDateTim": int(datetime.now().timestamp() * 1000),
                "executeResult": {
                    "code": 200 if result.get("success", False) else 500,
                    "msg": result.get("message", ""),
                    "content": json.dumps(result, ensure_ascii=False)
                }
            }
            
            api_result = await self._make_request("callback", [callback_data])
            
            if api_result.get("code") == 200:
                logger.info(f"任务结果回调成功: {task_id}")
                return True
            else:
                logger.error(f"任务结果回调失败: {api_result}")
                return False
                
        except Exception as e:
            logger.error(f"回调任务结果时发生错误: {e}")
            return False


# 全局客户端实例
xxl_job_client = XXLJobClient()
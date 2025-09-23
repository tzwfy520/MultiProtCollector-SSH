"""
XXL-Job执行器
提供HTTP服务接收调度中心的任务分发请求
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from ..config import config
from ..utils import logger
from .handler import ssh_collection_handler


class XXLJobExecutor:
    """XXL-Job执行器"""
    
    def __init__(self):
        self.app = FastAPI(title="XXL-Job Executor")
        self.server: Optional[uvicorn.Server] = None
        self.server_task: Optional[asyncio.Task] = None
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # 设置路由
        self._setup_routes()
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.post("/run")
        async def handle_run_task(request: Request):
            """处理任务执行请求"""
            return await self.handle_run_task(request)
        
        @self.app.post("/kill")
        async def handle_kill_task(request: Request):
            """处理任务终止请求"""
            return await self.handle_kill_task(request)
        
        @self.app.post("/log")
        async def handle_log_request(request: Request):
            """处理日志查询请求"""
            return await self.handle_log_request(request)
        
        @self.app.post("/beat")
        async def handle_beat_request(request: Request):
            """处理心跳检测请求"""
            return await self.handle_beat_request(request)
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    
    async def start_server(self):
        """启动执行器HTTP服务"""
        try:
            # 确保日志目录存在
            log_path = config.xxl_job_executor_log_path
            os.makedirs(log_path, exist_ok=True)
            
            # 配置uvicorn服务器
            server_config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=config.xxl_job_executor_port,
                log_level="info",
                access_log=False
            )
            
            self.server = uvicorn.Server(server_config)
            
            # 在后台任务中启动服务器
            self.server_task = asyncio.create_task(self.server.serve())
            
            logger.info(f"XXL-Job执行器HTTP服务启动成功，端口: {config.xxl_job_executor_port}")
            
        except Exception as e:
            logger.error(f"启动XXL-Job执行器HTTP服务失败: {e}")
            raise
    
    async def stop_server(self):
        """停止执行器HTTP服务"""
        try:
            # 停止所有运行中的任务
            for task_id, task in self.running_tasks.items():
                if not task.done():
                    logger.info(f"终止运行中的任务: {task_id}")
                    task.cancel()
            
            # 等待所有任务完成
            if self.running_tasks:
                await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
            
            # 停止HTTP服务器
            if self.server:
                self.server.should_exit = True
                
            if self.server_task and not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭线程池
            self.executor.shutdown(wait=True)
            
            logger.info("XXL-Job执行器HTTP服务停止完成")
            
        except Exception as e:
            logger.error(f"停止XXL-Job执行器HTTP服务失败: {e}")
            raise
    
    async def handle_run_task(self, request: Request) -> JSONResponse:
        """处理任务执行请求"""
        try:
            # 解析请求数据
            data = await request.json()
            
            job_id = str(data.get("jobId", ""))
            log_id = str(data.get("logId", ""))
            log_datetime = data.get("logDateTime", 0)
            glue_type = data.get("glueType", "")
            glue_source = data.get("glueSource", "")
            glue_update_time = data.get("glueUpdatetime", 0)
            broad_cast_index = data.get("broadcastIndex", 0)
            broad_cast_total = data.get("broadcastTotal", 1)
            executor_params = data.get("executorParams", "")
            executor_timeout = data.get("executorTimeout", 0)
            
            logger.info(f"接收到任务执行请求: jobId={job_id}, logId={log_id}, params={executor_params}")
            
            # 检查是否已有相同任务在运行
            if log_id in self.running_tasks:
                return JSONResponse({
                    "code": 500,
                    "msg": f"任务已在运行中: {log_id}"
                })
            
            # 创建任务执行协程
            task = asyncio.create_task(
                self._execute_task(log_id, executor_params, executor_timeout)
            )
            self.running_tasks[log_id] = task
            
            return JSONResponse({
                "code": 200,
                "msg": "任务启动成功"
            })
            
        except Exception as e:
            logger.error(f"处理任务执行请求失败: {e}")
            return JSONResponse({
                "code": 500,
                "msg": f"任务启动失败: {str(e)}"
            })
    
    async def handle_kill_task(self, request: Request) -> JSONResponse:
        """处理任务终止请求"""
        try:
            data = await request.json()
            log_id = str(data.get("logId", ""))
            
            logger.info(f"接收到任务终止请求: logId={log_id}")
            
            if log_id in self.running_tasks:
                task = self.running_tasks[log_id]
                if not task.done():
                    task.cancel()
                    logger.info(f"任务终止成功: {log_id}")
                    return JSONResponse({
                        "code": 200,
                        "msg": "任务终止成功"
                    })
                else:
                    return JSONResponse({
                        "code": 200,
                        "msg": "任务已完成"
                    })
            else:
                return JSONResponse({
                    "code": 500,
                    "msg": "任务不存在"
                })
                
        except Exception as e:
            logger.error(f"处理任务终止请求失败: {e}")
            return JSONResponse({
                "code": 500,
                "msg": f"任务终止失败: {str(e)}"
            })
    
    async def handle_log_request(self, request: Request) -> JSONResponse:
        """处理日志查询请求"""
        try:
            data = await request.json()
            log_datetime = data.get("logDateTim", 0)
            log_id = str(data.get("logId", ""))
            from_line_num = data.get("fromLineNum", 0)
            
            logger.debug(f"接收到日志查询请求: logId={log_id}, fromLine={from_line_num}")
            
            # 构建日志文件路径
            log_file = os.path.join(
                config.xxl_job_executor_log_path,
                f"{log_id}.log"
            )
            
            log_content = ""
            to_line_num = from_line_num
            is_end = True
            
            try:
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if from_line_num < len(lines):
                            log_content = ''.join(lines[from_line_num:])
                            to_line_num = len(lines)
                            is_end = log_id not in self.running_tasks or self.running_tasks[log_id].done()
            except Exception as e:
                logger.error(f"读取日志文件失败: {e}")
            
            return JSONResponse({
                "code": 200,
                "msg": "",
                "content": {
                    "fromLineNum": from_line_num,
                    "toLineNum": to_line_num,
                    "logContent": log_content,
                    "isEnd": is_end
                }
            })
            
        except Exception as e:
            logger.error(f"处理日志查询请求失败: {e}")
            return JSONResponse({
                "code": 500,
                "msg": f"日志查询失败: {str(e)}"
            })
    
    async def handle_beat_request(self, request: Request) -> JSONResponse:
        """处理心跳检测请求"""
        try:
            logger.debug("接收到心跳检测请求")
            return JSONResponse({
                "code": 200,
                "msg": "心跳正常"
            })
        except Exception as e:
            logger.error(f"处理心跳检测请求失败: {e}")
            return JSONResponse({
                "code": 500,
                "msg": f"心跳检测失败: {str(e)}"
            })
    
    async def _execute_task(self, log_id: str, executor_params: str, executor_timeout: int):
        """执行具体任务"""
        log_file = os.path.join(config.xxl_job_executor_log_path, f"{log_id}.log")
        
        try:
            # 创建日志文件
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] 任务开始执行: {log_id}\\n")
                f.write(f"[{datetime.now()}] 任务参数: {executor_params}\\n")
            
            # 执行SSH采集任务
            result = await ssh_collection_handler.execute_ssh_collection(executor_params)
            
            # 记录执行结果
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] 任务执行完成\\n")
                f.write(f"[{datetime.now()}] 执行结果: {json.dumps(result, ensure_ascii=False)}\\n")
            
            logger.info(f"任务执行完成: {log_id}")
            
        except asyncio.CancelledError:
            # 任务被取消
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] 任务被取消\\n")
            logger.info(f"任务被取消: {log_id}")
            raise
            
        except Exception as e:
            # 任务执行失败
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] 任务执行失败: {str(e)}\\n")
            logger.error(f"任务执行失败: {log_id}, 错误: {e}")
            
        finally:
            # 清理任务记录
            if log_id in self.running_tasks:
                del self.running_tasks[log_id]


# 全局执行器实例
xxl_job_executor = XXLJobExecutor()
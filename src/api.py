"""
FastAPI接口模块
提供简单采集任务的API接口
"""
from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import uuid

from .config import settings
from .utils import logger, CollectorException, system_monitor
from .ssh_core import SimpleSSHCollector, SSHCredentials, SSHCommand
from .registration import registration_manager
from .database import get_task_record, get_task_history, get_statistics


# API数据模型
class SSHCredentialsRequest(BaseModel):
    """SSH凭据请求模型"""
    host: str = Field(..., description="目标主机IP或域名")
    port: int = Field(22, description="SSH端口", ge=1, le=65535)
    username: str = Field(..., description="SSH用户名")
    password: Optional[str] = Field(None, description="SSH密码")
    private_key: Optional[str] = Field(None, description="SSH私钥")
    device_type: str = Field("linux", description="设备类型")
    
    @validator('device_type')
    def validate_device_type(cls, v):
        """验证设备类型"""
        allowed_types = [
            'linux', 'cisco_ios', 'cisco_xe', 'cisco_nxos', 'cisco_asa',
            'juniper', 'arista_eos', 'hp_comware', 'huawei', 'huawei_vrp',
            'fortinet', 'paloalto_panos', 'dell_force10', 'extreme', 'alcatel_sros'
        ]
        if v not in allowed_types:
            raise ValueError(f'设备类型必须是以下之一: {", ".join(allowed_types)}')
        return v
    
    @validator('password')
    def validate_auth(cls, v, values):
        """验证认证信息"""
        if not v and not values.get('private_key'):
            raise ValueError('必须提供密码或私钥')
        return v


class SSHCommandRequest(BaseModel):
    """SSH命令请求模型"""
    command: str = Field(..., description="要执行的命令")
    expect_string: Optional[str] = Field(None, description="期望的返回字符串")
    delay_factor: float = Field(1.0, description="延迟因子", ge=0.1, le=10.0)
    max_loops: int = Field(500, description="最大循环次数", ge=1, le=2000)


class SimpleCollectionRequest(BaseModel):
    """简单采集请求模型"""
    credentials: SSHCredentialsRequest
    commands: List[SSHCommandRequest] = Field(..., min_items=1, max_items=50)
    timeout: int = Field(300, description="超时时间（秒）", ge=30, le=3600)
    
    class Config:
        schema_extra = {
            "example": {
                "credentials": {
                    "host": "192.168.1.100",
                    "port": 22,
                    "username": "admin",
                    "password": "password123",
                    "device_type": "linux"
                },
                "commands": [
                    {
                        "command": "show version",
                        "delay_factor": 1.0
                    },
                    {
                        "command": "show interfaces",
                        "delay_factor": 2.0
                    }
                ],
                "timeout": 300
            }
        }


class CollectionResponse(BaseModel):
    """采集响应模型"""
    success: bool
    task_id: str
    timestamp: datetime
    execution_time: float
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "task_id": "task_123456789",
                "timestamp": "2024-01-01T12:00:00Z",
                "execution_time": 5.23,
                "data": {
                    "commands": [
                        {
                            "command": "show version",
                            "output": "Cisco IOS Software...",
                            "success": True
                        }
                    ]
                },
                "error": None
            }
        }


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str
    timestamp: datetime
    collector_id: str
    version: str
    uptime: float
    system_info: Dict[str, Any]
    registration_status: str


# 创建FastAPI应用
app = FastAPI(
    title="SSH采集器API",
    description="基于netmiko的SSH设备采集器API接口",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 依赖注入
async def get_collector_status():
    """获取采集器状态"""
    return {
        "collector_id": settings.collector_id,
        "registered": registration_manager.is_registered(),
        "system_info": system_monitor.get_system_info()
    }


# API路由
@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径"""
    return {
        "service": "SSH采集器",
        "version": settings.app_version,
        "status": "运行中"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(status: Dict = Depends(get_collector_status)):
    """健康检查接口"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        collector_id=status["collector_id"],
        version=settings.app_version,
        uptime=system_monitor.get_uptime(),
        system_info=status["system_info"],
        registration_status="registered" if status["registered"] else "unregistered"
    )


@app.post("/collect", response_model=CollectionResponse)
async def simple_collect(request: SimpleCollectionRequest):
    """
    简单采集接口
    
    执行SSH采集任务并返回结果
    """
    task_id = f"api_{uuid.uuid4().hex[:8]}"
    start_time = datetime.now()
    
    try:
        logger.info(f"开始处理API采集任务: {task_id}")
        
        # 转换请求数据
        credentials = SSHCredentials(
            host=request.credentials.host,
            port=request.credentials.port,
            username=request.credentials.username,
            password=request.credentials.password,
            private_key=request.credentials.private_key,
            device_type=request.credentials.device_type
        )
        
        commands = [
            SSHCommand(
                command=cmd.command,
                expect_string=cmd.expect_string,
                delay_factor=cmd.delay_factor,
                max_loops=cmd.max_loops
            )
            for cmd in request.commands
        ]
        
        # 执行采集
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            SimpleSSHCollector.execute_commands,
            credentials,
            commands,
            request.timeout
        )
        
        # 计算执行时间
        execution_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"API采集任务 {task_id} 完成，成功: {result['success']}")
        
        return CollectionResponse(
            success=result["success"],
            task_id=task_id,
            timestamp=start_time,
            execution_time=execution_time,
            data=result.get("data"),
            error=result.get("error")
        )
        
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        error_msg = f"采集任务执行失败: {str(e)}"
        logger.error(f"API采集任务 {task_id} 失败: {error_msg}")
        
        return CollectionResponse(
            success=False,
            task_id=task_id,
            timestamp=start_time,
            execution_time=execution_time,
            error=error_msg
        )


@app.get("/status", response_model=Dict[str, Any])
async def get_status(status: Dict = Depends(get_collector_status)):
    """获取采集器状态"""
    return {
        "collector_id": status["collector_id"],
        "version": settings.app_version,
        "registration_status": "registered" if status["registered"] else "unregistered",
        "system_info": status["system_info"],
        "timestamp": datetime.now()
    }


@app.post("/test-connection")
async def test_ssh_connection(credentials: SSHCredentialsRequest):
    """
    测试SSH连接
    
    仅测试连接，不执行命令
    """
    try:
        ssh_creds = SSHCredentials(
            host=credentials.host,
            port=credentials.port,
            username=credentials.username,
            password=credentials.password,
            private_key=credentials.private_key,
            device_type=credentials.device_type
        )
        
        # 执行连接测试
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            SimpleSSHCollector.test_connection,
            ssh_creds
        )
        
        return {
            "success": result["success"],
            "message": result.get("message", "连接测试完成"),
            "error": result.get("error"),
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        error_msg = f"连接测试失败: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": "连接测试失败",
            "error": error_msg,
            "timestamp": datetime.now()
        }


@app.get("/supported-devices")
async def get_supported_devices():
    """获取支持的设备类型列表"""
    return {
        "supported_devices": [
            {"type": "linux", "description": "Linux服务器"},
            {"type": "cisco_ios", "description": "Cisco IOS设备"},
            {"type": "cisco_xe", "description": "Cisco IOS-XE设备"},
            {"type": "cisco_nxos", "description": "Cisco NX-OS设备"},
            {"type": "cisco_asa", "description": "Cisco ASA防火墙"},
            {"type": "juniper", "description": "Juniper设备"},
            {"type": "arista_eos", "description": "Arista EOS设备"},
            {"type": "hp_comware", "description": "HP Comware设备"},
            {"type": "huawei", "description": "华为设备"},
            {"type": "fortinet", "description": "Fortinet设备"},
            {"type": "paloalto_panos", "description": "Palo Alto PAN-OS"},
            {"type": "dell_force10", "description": "Dell Force10设备"},
            {"type": "extreme", "description": "Extreme Networks设备"},
            {"type": "alcatel_sros", "description": "Alcatel-Lucent SR OS"}
        ]
    }


# 数据库查询接口
@app.get("/tasks/{task_id}")
async def get_task_detail(task_id: str):
    """获取任务详情"""
    try:
        task_record = get_task_record(task_id)
        if not task_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"任务 {task_id} 不存在"
            )
        
        return {
            "success": True,
            "data": task_record,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"获取任务详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务详情失败: {str(e)}"
        )


@app.get("/tasks")
async def get_task_list(
    limit: int = Query(100, ge=1, le=1000, description="返回记录数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    status: Optional[str] = Query(None, description="任务状态过滤"),
    host: Optional[str] = Query(None, description="主机过滤")
):
    """获取任务历史列表"""
    try:
        tasks = get_task_history(limit=limit, offset=offset, status=status, host=host)
        
        return {
            "success": True,
            "data": {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset,
                "filters": {
                    "status": status,
                    "host": host
                }
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务列表失败: {str(e)}"
        )


@app.get("/statistics")
async def get_collector_statistics(
    days: int = Query(7, ge=1, le=365, description="统计天数")
):
    """获取采集器统计信息"""
    try:
        stats = get_statistics(days=days)
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )


# 异常处理器
@app.exception_handler(CollectorException)
async def collector_exception_handler(request, exc: CollectorException):
    """采集器异常处理器"""
    logger.error(f"采集器异常: {exc.message}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": exc.message,
            "error_code": exc.error_code,
            "details": exc.details,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """HTTP异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """通用异常处理器"""
    logger.error(f"未处理的异常: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "内部服务器错误",
            "timestamp": datetime.now().isoformat()
        }
    )


# 启动和关闭事件
@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("FastAPI应用启动")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("FastAPI应用关闭")
"""
SSH采集核心逻辑模块
基于netmiko库实现SSH连接和命令执行
支持多线程并发采集
"""
import time
from typing import Dict, Any, List, Optional, Union
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from pydantic import BaseModel, Field
from .utils import logger, handle_exception, SSHConnectionException, TaskExecutionException, format_ssh_result, validate_ssh_params
from .config import settings
from .database import create_task_record, update_task_status, complete_task
from .thread_pool_manager import thread_pool_manager

# 导入插件管理器
try:
    from ..addone.plugin_manager import plugin_manager
except ImportError:
    logger.warning("插件管理器导入失败，将使用默认配置")
    plugin_manager = None


class SSHCredentials(BaseModel):
    """SSH连接凭据"""
    host: str = Field(..., description="目标主机IP或域名")
    port: int = Field(default=22, description="SSH端口")
    username: str = Field(..., description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    private_key: Optional[str] = Field(default=None, description="私钥内容")
    device_type: str = Field(default="linux", description="设备类型")
    timeout: int = Field(default=30, description="连接超时时间")


class SSHCommand(BaseModel):
    """SSH命令"""
    command: str = Field(..., description="要执行的命令")
    expect_string: Optional[str] = Field(default=None, description="期望的返回字符串")
    delay_factor: float = Field(default=1.0, description="延迟因子")
    max_loops: int = Field(default=500, description="最大循环次数")


class CollectionTask(BaseModel):
    """采集任务"""
    task_id: str = Field(..., description="任务ID")
    credentials: SSHCredentials = Field(..., description="SSH连接凭据")
    commands: List[SSHCommand] = Field(..., description="要执行的命令列表")
    timeout: int = Field(default=300, description="任务超时时间")
    retry_count: int = Field(default=3, description="重试次数")


class SSHCollector:
    """SSH采集器核心类"""
    
    def __init__(self):
        self.connection = None
        self.current_host = None
        self.device_type = None
    
    def _apply_plugin_command_params(self, ssh_command: SSHCommand, device_type: str) -> SSHCommand:
        """应用插件的命令参数"""
        if not plugin_manager or not plugin_manager.has_plugin(device_type):
            return ssh_command
        
        device_config = plugin_manager.get_device_config(device_type)
        if not device_config:
            return ssh_command
        
        # 创建命令副本以避免修改原始对象
        command_dict = ssh_command.dict()
        
        # 应用通用命令参数
        if 'command_params' in device_config:
            plugin_params = device_config['command_params']
            
            # 只在用户未指定时应用插件默认值
            if ssh_command.expect_string is None and 'expect_string' in plugin_params:
                command_dict['expect_string'] = plugin_params['expect_string']
            
            if ssh_command.delay_factor == 1.0 and 'delay_factor' in plugin_params:
                command_dict['delay_factor'] = plugin_params['delay_factor']
            
            if ssh_command.max_loops == 500 and 'max_loops' in plugin_params:
                command_dict['max_loops'] = plugin_params['max_loops']
        
        # 检查是否有特定命令的配置
        if 'commands' in device_config:
            command_configs = device_config['commands']
            command_name = ssh_command.command.strip().lower()
            
            # 尝试匹配命令配置
            for config_key, config_value in command_configs.items():
                if config_value.get('command', '').strip().lower() == command_name:
                    logger.info(f"应用命令特定配置: {config_key}")
                    # 应用特定命令配置，但不覆盖用户明确指定的参数
                    if ssh_command.expect_string is None and 'expect_string' in config_value:
                        command_dict['expect_string'] = config_value['expect_string']
                    if ssh_command.delay_factor == 1.0 and 'delay_factor' in config_value:
                        command_dict['delay_factor'] = config_value['delay_factor']
                    if ssh_command.max_loops == 500 and 'max_loops' in config_value:
                        command_dict['max_loops'] = config_value['max_loops']
                    break
        
        return SSHCommand(**command_dict)
    
    @handle_exception
    def connect(self, credentials: SSHCredentials) -> bool:
        """建立SSH连接"""
        try:
            # 验证连接参数
            if not validate_ssh_params(
                credentials.host, 
                credentials.username, 
                credentials.password, 
                credentials.private_key
            ):
                raise SSHConnectionException(
                    "SSH连接参数不完整",
                    host=credentials.host,
                    details={"missing_params": "host, username, and (password or private_key) are required"}
                )
            
            # 构建基础连接参数
            connection_params = {
                'device_type': credentials.device_type,
                'host': credentials.host,
                'port': credentials.port,
                'username': credentials.username,
                'timeout': credentials.timeout,
                'session_timeout': credentials.timeout,
                'auth_timeout': credentials.timeout,
                'banner_timeout': credentials.timeout,
                'read_timeout_override': 60,  # 默认读取超时时间
                'global_delay_factor': 2,     # 默认全局延迟因子
            }
            
            # 从插件获取设备特定配置
            if plugin_manager and plugin_manager.has_plugin(credentials.device_type):
                device_config = plugin_manager.get_device_config(credentials.device_type)
                if device_config and 'connection_params' in device_config:
                    plugin_params = device_config['connection_params']
                    logger.info(f"应用插件配置 {credentials.device_type}: {plugin_params}")
                    connection_params.update(plugin_params)
            else:
                # 保留原有的华为设备特殊配置作为后备
                if credentials.device_type in ['huawei', 'huawei_vrpv8']:
                    connection_params.update({
                        'global_delay_factor': 3,
                        'read_timeout_override': 90,
                        'session_timeout': 120,
                    })
            
            # 添加认证方式
            if credentials.password:
                connection_params['password'] = credentials.password
            
            if credentials.private_key:
                connection_params['use_keys'] = True
                connection_params['key_file'] = credentials.private_key
            
            logger.info(f"正在连接到设备: {credentials.host}:{credentials.port}")
            
            # 建立连接
            self.connection = ConnectHandler(**connection_params)
            self.current_host = credentials.host
            self.device_type = credentials.device_type  # 保存设备类型
            
            logger.info(f"成功连接到设备: {credentials.host}")
            return True
            
        except NetmikoAuthenticationException as e:
            error_msg = f"SSH认证失败: {str(e)}"
            logger.error(error_msg)
            raise SSHConnectionException(
                error_msg,
                host=credentials.host,
                details={"auth_error": str(e)}
            )
        
        except NetmikoTimeoutException as e:
            error_msg = f"SSH连接超时: {str(e)}"
            logger.error(error_msg)
            raise SSHConnectionException(
                error_msg,
                host=credentials.host,
                details={"timeout_error": str(e)}
            )
        
        except Exception as e:
            error_msg = f"SSH连接失败: {str(e)}"
            logger.error(error_msg)
            raise SSHConnectionException(
                error_msg,
                host=credentials.host,
                details={"connection_error": str(e)}
            )
    
    @handle_exception
    def execute_command(self, ssh_command: SSHCommand) -> Dict[str, Any]:
        """执行单个SSH命令"""
        if not self.connection:
            raise SSHConnectionException("SSH连接未建立")
        
        # 应用插件参数
        if self.device_type:
            ssh_command = self._apply_plugin_command_params(ssh_command, self.device_type)
        
        try:
            logger.debug(f"执行命令: {ssh_command.command}")
            
            # 执行命令
            if ssh_command.expect_string:
                output = self.connection.send_command(
                    ssh_command.command,
                    expect_string=ssh_command.expect_string,
                    delay_factor=ssh_command.delay_factor,
                    max_loops=ssh_command.max_loops,
                    read_timeout=120  # 增加读取超时时间
                )
            else:
                # 对于华为设备，尝试自动检测提示符
                output = self.connection.send_command(
                    ssh_command.command,
                    delay_factor=max(ssh_command.delay_factor, 3.0),  # 最小延迟因子为3
                    max_loops=max(ssh_command.max_loops, 1000),       # 最小循环次数为1000
                    read_timeout=120,                                 # 增加读取超时时间
                    auto_find_prompt=True,                           # 自动查找提示符
                    strip_prompt=False,                              # 保留提示符
                    strip_command=False                              # 保留命令
                )
            
            logger.debug(f"命令执行成功，输出长度: {len(output)}")
            
            return {
                "command": ssh_command.command,
                "output": output,
                "success": True,
                "host": self.current_host
            }
            
        except Exception as e:
            error_msg = f"命令执行失败: {str(e)}"
            logger.error(error_msg)
            return {
                "command": ssh_command.command,
                "output": "",
                "success": False,
                "error": error_msg,
                "host": self.current_host
            }
    
    @handle_exception
    def execute_commands(self, commands: List[SSHCommand]) -> List[Dict[str, Any]]:
        """批量执行SSH命令"""
        if not self.connection:
            raise SSHConnectionException("SSH连接未建立")
        
        results = []
        
        for i, command in enumerate(commands):
            logger.info(f"执行命令 {i+1}/{len(commands)}: {command.command}")
            
            result = self.execute_command(command)
            results.append(result)
            
            # 如果命令执行失败，记录但继续执行后续命令
            if not result["success"]:
                logger.warning(f"命令执行失败，继续执行后续命令: {result['error']}")
        
        return results
    
    def disconnect(self):
        """断开SSH连接"""
        if self.connection:
            try:
                self.connection.disconnect()
                logger.info(f"已断开与设备 {self.current_host} 的连接")
            except Exception as e:
                logger.warning(f"断开连接时发生错误: {str(e)}")
            finally:
                self.connection = None
                self.current_host = None
    
    @handle_exception
    def collect_with_retry(self, task: CollectionTask) -> Dict[str, Any]:
        """带重试机制的采集任务执行"""
        start_time = time.time()
        last_error = None
        
        # 创建任务记录
        try:
            task_data = {
                "task_id": task.task_id,
                "task_type": "collection",
                "credentials": {
                    "host": task.credentials.host,
                    "port": task.credentials.port,
                    "device_type": task.credentials.device_type
                },
                "commands": [cmd.command for cmd in task.commands],
                "timeout": task.timeout,
                "retry_count": task.retry_count
            }
            create_task_record(task_data)
            update_task_status(task.task_id, "running", started_at=start_time)
        except Exception as e:
            logger.warning(f"创建任务记录失败: {e}")
        
        for attempt in range(task.retry_count):
            try:
                logger.info(f"开始执行采集任务 {task.task_id}，第 {attempt + 1} 次尝试")
                
                # 建立连接
                if not self.connect(task.credentials):
                    raise SSHConnectionException("无法建立SSH连接")
                
                # 执行命令
                results = self.execute_commands(task.commands)
                
                # 统计执行结果
                success_count = sum(1 for r in results if r["success"])
                total_count = len(results)
                
                # 断开连接
                self.disconnect()
                
                # 计算执行时间
                execution_time = time.time() - start_time
                
                # 构建结果数据
                result_data = {
                    "task_id": task.task_id,
                    "host": task.credentials.host,
                    "total_commands": total_count,
                    "success_commands": success_count,
                    "failed_commands": total_count - success_count,
                    "results": results,
                    "attempt": attempt + 1,
                    "execution_time": execution_time
                }
                
                # 更新任务完成状态
                try:
                    complete_task(
                        task.task_id, 
                        success=True, 
                        result_data=result_data,
                        execution_time=execution_time
                    )
                except Exception as e:
                    logger.warning(f"更新任务完成状态失败: {e}")
                
                # 返回结果
                return format_ssh_result(success=True, data=result_data)
                
            except Exception as e:
                last_error = e
                logger.error(f"采集任务第 {attempt + 1} 次尝试失败: {str(e)}")
                
                # 确保连接被断开
                self.disconnect()
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < task.retry_count - 1:
                    wait_time = settings.ssh_retry_delay * (attempt + 1)
                    logger.info(f"等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)
        
        # 所有重试都失败
        execution_time = time.time() - start_time
        error_msg = f"采集任务 {task.task_id} 执行失败，已重试 {task.retry_count} 次"
        logger.error(error_msg)
        
        # 更新任务失败状态
        try:
            complete_task(
                task.task_id, 
                success=False, 
                error_message=f"{error_msg}: {str(last_error)}",
                execution_time=execution_time
            )
        except Exception as e:
            logger.warning(f"更新任务失败状态失败: {e}")
        
        return format_ssh_result(
            success=False,
            error=f"{error_msg}: {str(last_error)}"
        )


class SimpleSSHCollector:
    """简单SSH采集器（用于API接口）"""
    
    @staticmethod
    @handle_exception
    def test_connection(credentials: SSHCredentials) -> Dict[str, Any]:
        """测试SSH连接"""
        collector = SSHCollector()
        
        try:
            # 建立连接
            success = collector.connect(credentials)
            
            if success:
                return format_ssh_result(
                    success=True,
                    data={"message": f"成功连接到 {credentials.host}:{credentials.port}"},
                    error=None
                )
            else:
                return format_ssh_result(
                    success=False,
                    data=None,
                    error="连接失败"
                )
                
        except Exception as e:
            return format_ssh_result(
                success=False,
                data=None,
                error=str(e)
            )
        finally:
            collector.disconnect()
    
    @staticmethod
    @handle_exception
    def execute_commands(
        credentials: SSHCredentials,
        commands: List[SSHCommand],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """执行多个SSH命令"""
        collector = SSHCollector()
        
        try:
            # 建立连接
            collector.connect(credentials)
            
            # 执行命令
            results = collector.execute_commands(commands)
            
            return format_ssh_result(
                success=True,
                data={"commands": results},
                error=None
            )
            
        except Exception as e:
            return format_ssh_result(
                success=False,
                data=None,
                error=str(e)
            )
        finally:
            collector.disconnect()
    
    @staticmethod
    @handle_exception
    def execute_simple_command(
        host: str,
        username: str,
        password: str,
        command: str,
        port: int = 22,
        device_type: str = "linux",
        timeout: int = 30
    ) -> Dict[str, Any]:
        """执行简单SSH命令"""
        
        collector = SSHCollector()
        
        try:
            # 创建凭据
            credentials = SSHCredentials(
                host=host,
                port=port,
                username=username,
                password=password,
                device_type=device_type,
                timeout=timeout
            )
            
            # 创建命令
            ssh_command = SSHCommand(command=command)
            
            # 建立连接
            collector.connect(credentials)
            
            # 执行命令
            result = collector.execute_command(ssh_command)
            
            return format_ssh_result(
                success=result["success"],
                data=result if result["success"] else None,
                error=result.get("error") if not result["success"] else None
            )
            
        finally:
            collector.disconnect()


class MultiThreadSSHCollector:
    """多线程SSH采集器"""
    
    @staticmethod
    def _execute_single_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个采集任务（用于多线程）
        
        Args:
            task_data: 任务数据，包含task_id, credentials, commands等
            
        Returns:
            任务执行结果
        """
        task_id = task_data.get('task_id', 'unknown')
        start_time = time.time()
        
        try:
            # 创建任务对象
            task = CollectionTask(**task_data)
            
            # 使用独立的采集器实例（避免线程间冲突）
            collector = SSHCollector()
            result = collector.collect_with_retry(task)
            
            logger.info(f"多线程任务完成: {task_id}, 耗时: {time.time() - start_time:.2f}s")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"多线程任务执行失败: {task_id}, 错误: {e}, 耗时: {execution_time:.2f}s")
            
            return {
                "task_id": task_id,
                "host": task_data.get('credentials', {}).get('host', 'unknown'),
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
                "total_commands": len(task_data.get('commands', [])),
                "success_commands": 0,
                "failed_commands": len(task_data.get('commands', [])),
                "results": []
            }
    
    @staticmethod
    @handle_exception
    def execute_batch_tasks(tasks: List[Dict[str, Any]], 
                          max_workers: Optional[int] = None,
                          enable_threading: Optional[bool] = None) -> Dict[str, Any]:
        """
        批量执行采集任务（支持多线程）
        
        Args:
            tasks: 任务列表，每个任务包含完整的任务数据
            max_workers: 最大并发线程数，默认使用配置值
            enable_threading: 是否启用多线程，默认使用配置值
            
        Returns:
            批量执行结果
        """
        start_time = time.time()
        total_tasks = len(tasks)
        
        # 确定是否使用多线程
        use_threading = enable_threading if enable_threading is not None else settings.enable_threading
        workers = max_workers or settings.max_concurrent_threads
        
        logger.info(f"开始批量执行 {total_tasks} 个采集任务，多线程: {use_threading}, 最大并发: {workers}")
        
        if use_threading and total_tasks > 1:
            # 使用线程池管理器并行执行
            results = thread_pool_manager.execute_tasks_parallel(
                tasks=tasks,
                task_func=MultiThreadSSHCollector._execute_single_task,
                max_workers=workers
            )
        else:
            # 串行执行
            logger.info("使用串行模式执行任务")
            results = []
            for task_data in tasks:
                result = MultiThreadSSHCollector._execute_single_task(task_data)
                results.append(result)
        
        # 统计结果
        execution_time = time.time() - start_time
        success_tasks = sum(1 for r in results if r.get("success", False))
        failed_tasks = total_tasks - success_tasks
        
        # 统计命令执行情况
        total_commands = sum(r.get("total_commands", 0) for r in results)
        success_commands = sum(r.get("success_commands", 0) for r in results)
        failed_commands = sum(r.get("failed_commands", 0) for r in results)
        
        batch_result = {
            "success": True,
            "batch_id": f"batch_{int(start_time)}",
            "execution_time": execution_time,
            "threading_enabled": use_threading,
            "max_workers": workers if use_threading else 1,
            "summary": {
                "total_tasks": total_tasks,
                "success_tasks": success_tasks,
                "failed_tasks": failed_tasks,
                "total_commands": total_commands,
                "success_commands": success_commands,
                "failed_commands": failed_commands
            },
            "task_results": results
        }
        
        logger.info(f"批量任务执行完成 - 总任务: {total_tasks}, 成功: {success_tasks}, "
                   f"失败: {failed_tasks}, 耗时: {execution_time:.2f}s")
        
        return batch_result
    
    @staticmethod
    @handle_exception
    def execute_multi_host_commands(hosts_credentials: List[SSHCredentials],
                                  commands: List[SSHCommand],
                                  max_workers: Optional[int] = None,
                                  timeout: int = 300,
                                  retry_count: int = 3) -> Dict[str, Any]:
        """
        对多个主机执行相同的命令集（多线程）
        
        Args:
            hosts_credentials: 主机凭据列表
            commands: 要执行的命令列表
            max_workers: 最大并发线程数
            timeout: 任务超时时间
            retry_count: 重试次数
            
        Returns:
            多主机执行结果
        """
        # 构建任务列表
        tasks = []
        for i, credentials in enumerate(hosts_credentials):
            task_data = {
                "task_id": f"multi_host_task_{i}_{credentials.host}_{int(time.time())}",
                "credentials": credentials.dict(),
                "commands": [cmd.dict() for cmd in commands],
                "timeout": timeout,
                "retry_count": retry_count
            }
            tasks.append(task_data)
        
        logger.info(f"准备对 {len(hosts_credentials)} 个主机执行 {len(commands)} 个命令")
        
        # 执行批量任务
        return MultiThreadSSHCollector.execute_batch_tasks(
            tasks=tasks,
            max_workers=max_workers
        )


# 全局采集器实例
ssh_collector = SSHCollector()
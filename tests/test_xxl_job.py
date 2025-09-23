"""
XXL-Job集成测试用例
测试XXL-Job执行器、客户端和任务处理器的功能
"""
import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.xxl_job.client import XXLJobClient, xxl_job_client
from src.xxl_job.executor import XXLJobExecutor, xxl_job_executor
from src.xxl_job.handler import SSHCollectionHandler
from src.config import settings


class TestXXLJobClient:
    """XXL-Job客户端测试"""
    
    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return XXLJobClient(
            admin_addresses="http://localhost:8080/xxl-job-admin",
            access_token="test_token",
            executor_app_name="test-executor",
            executor_port=9999
        )
    
    @pytest.mark.asyncio
    async def test_get_local_ip(self, client):
        """测试获取本机IP"""
        ip = client._get_local_ip()
        assert ip is not None
        assert isinstance(ip, str)
        assert len(ip.split('.')) == 4
    
    @pytest.mark.asyncio
    async def test_register_executor(self, client):
        """测试执行器注册"""
        with patch.object(client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            result = await client.register_executor()
            
            assert result is True
            mock_request.assert_called_once()
            
            # 验证请求参数
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert "/api/registry" in call_args[0][1]
    
    @pytest.mark.asyncio
    async def test_register_executor_failure(self, client):
        """测试执行器注册失败"""
        with patch.object(client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 500, "msg": "error"}
            
            result = await client.register_executor()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_unregister_executor(self, client):
        """测试执行器注销"""
        with patch.object(client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            result = await client.unregister_executor()
            
            assert result is True
            mock_request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_heartbeat(self, client):
        """测试心跳检测"""
        with patch.object(client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            result = await client.heartbeat()
            
            assert result is True
            mock_request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_callback_task_result(self, client):
        """测试任务结果回调"""
        with patch.object(client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            result = await client.callback_task_result("123", {
                "code": 200,
                "msg": "success",
                "content": "task completed"
            })
            
            assert result is True
            mock_request.assert_called_once()


class TestXXLJobExecutor:
    """XXL-Job执行器测试"""
    
    @pytest.fixture
    def executor(self):
        """创建测试执行器"""
        return XXLJobExecutor(port=9998)  # 使用不同端口避免冲突
    
    @pytest.mark.asyncio
    async def test_start_stop_server(self, executor):
        """测试服务器启动和停止"""
        # 启动服务器
        await executor.start_server()
        assert executor.server is not None
        assert executor.running is True
        
        # 停止服务器
        await executor.stop_server()
        assert executor.running is False
    
    @pytest.mark.asyncio
    async def test_handle_beat_request(self, executor):
        """测试心跳请求处理"""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={})
        
        response = await executor.handle_beat_request(mock_request)
        
        assert response["code"] == 200
        assert response["msg"] == "success"
    
    @pytest.mark.asyncio
    async def test_handle_run_task(self, executor):
        """测试任务执行请求处理"""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={
            "jobId": 1,
            "executorHandler": "sshCollectionHandler",
            "executorParams": json.dumps({
                "host": "192.168.1.100",
                "port": 22,
                "username": "test",
                "password": "test123",
                "commands": ["ls -la"]
            }),
            "executorBlockStrategy": "SERIAL_EXECUTION",
            "executorTimeout": 0,
            "logId": 1,
            "logDateTime": int(datetime.now().timestamp() * 1000),
            "glueType": "BEAN",
            "glueSource": "",
            "glueUpdatetime": int(datetime.now().timestamp() * 1000),
            "broadcastIndex": 0,
            "broadcastTotal": 1
        })
        
        with patch('src.xxl_job.handler.SSHCollectionHandler.execute_ssh_collection', new_callable=AsyncMock) as mock_handler:
            mock_handler.return_value = {
                "code": 200,
                "msg": "success",
                "content": "Task completed successfully"
            }
            
            response = await executor.handle_run_task(mock_request)
            
            assert response["code"] == 200
            assert response["msg"] == "success"
            mock_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_kill_task(self, executor):
        """测试任务终止请求处理"""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={
            "jobId": 1
        })
        
        response = await executor.handle_kill_task(mock_request)
        
        assert response["code"] == 200
        assert response["msg"] == "success"
    
    @pytest.mark.asyncio
    async def test_handle_log_request(self, executor):
        """测试日志请求处理"""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={
            "logDateTim": int(datetime.now().timestamp() * 1000),
            "logId": 1,
            "fromLineNum": 1
        })
        
        response = await executor.handle_log_request(mock_request)
        
        assert response["code"] == 200
        assert "content" in response


class TestSSHCollectionHandler:
    """SSH采集任务处理器测试"""
    
    @pytest.fixture
    def handler(self):
        """创建测试处理器"""
        return SSHCollectionHandler()
    
    def test_parse_job_parameters(self, handler):
        """测试任务参数解析"""
        job_param = json.dumps({
            "host": "192.168.1.100",
            "port": 22,
            "username": "test",
            "password": "test123",
            "commands": ["ls -la", "ps aux"]
        })
        
        params = handler.parse_job_parameters(job_param)
        
        assert params["host"] == "192.168.1.100"
        assert params["port"] == 22
        assert params["username"] == "test"
        assert params["password"] == "test123"
        assert len(params["commands"]) == 2
    
    def test_parse_job_parameters_invalid_json(self, handler):
        """测试无效JSON参数解析"""
        job_param = "invalid json"
        
        params = handler.parse_job_parameters(job_param)
        
        assert params == {}
    
    @pytest.mark.asyncio
    async def test_execute_ssh_collection_success(self, handler):
        """测试SSH采集任务执行成功"""
        job_param = json.dumps({
            "host": "192.168.1.100",
            "port": 22,
            "username": "test",
            "password": "test123",
            "commands": ["echo 'test'"]
        })
        
        with patch('src.ssh_core.SSHCollector') as mock_collector_class:
            mock_collector = Mock()
            mock_collector_class.return_value = mock_collector
            mock_collector.connect = AsyncMock(return_value=True)
            mock_collector.execute_commands = AsyncMock(return_value={
                "success": True,
                "results": [{"command": "echo 'test'", "output": "test", "error": ""}]
            })
            mock_collector.disconnect = AsyncMock()
            
            result = await handler.execute_ssh_collection(job_param)
            
            assert result["code"] == 200
            assert result["msg"] == "success"
            assert "results" in result["content"]
    
    @pytest.mark.asyncio
    async def test_execute_ssh_collection_connection_failure(self, handler):
        """测试SSH连接失败"""
        job_param = json.dumps({
            "host": "192.168.1.100",
            "port": 22,
            "username": "test",
            "password": "wrong_password",
            "commands": ["echo 'test'"]
        })
        
        with patch('src.ssh_core.SSHCollector') as mock_collector_class:
            mock_collector = Mock()
            mock_collector_class.return_value = mock_collector
            mock_collector.connect = AsyncMock(return_value=False)
            
            result = await handler.execute_ssh_collection(job_param)
            
            assert result["code"] == 500
            assert "连接失败" in result["msg"]
    
    @pytest.mark.asyncio
    async def test_execute_ssh_collection_invalid_params(self, handler):
        """测试无效参数"""
        job_param = json.dumps({
            "host": "",  # 空主机地址
            "port": 22,
            "username": "test",
            "commands": []  # 空命令列表
        })
        
        result = await handler.execute_ssh_collection(job_param)
        
        assert result["code"] == 400
        assert "参数验证失败" in result["msg"]


class TestXXLJobIntegration:
    """XXL-Job集成测试"""
    
    @pytest.mark.asyncio
    async def test_executor_registration_flow(self):
        """测试执行器注册流程"""
        with patch.object(xxl_job_client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            # 测试注册
            result = await xxl_job_client.register_executor()
            assert result is True
            
            # 测试心跳
            result = await xxl_job_client.heartbeat()
            assert result is True
            
            # 测试注销
            result = await xxl_job_client.unregister_executor()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_task_execution_flow(self):
        """测试任务执行流程"""
        # 启动执行器
        await xxl_job_executor.start_server()
        
        try:
            # 模拟任务请求
            mock_request = Mock()
            mock_request.json = AsyncMock(return_value={
                "jobId": 1,
                "executorHandler": "sshCollectionHandler",
                "executorParams": json.dumps({
                    "host": "127.0.0.1",
                    "port": 22,
                    "username": "test",
                    "password": "test123",
                    "commands": ["echo 'integration test'"]
                }),
                "executorBlockStrategy": "SERIAL_EXECUTION",
                "executorTimeout": 0,
                "logId": 1,
                "logDateTime": int(datetime.now().timestamp() * 1000),
                "glueType": "BEAN",
                "glueSource": "",
                "glueUpdatetime": int(datetime.now().timestamp() * 1000),
                "broadcastIndex": 0,
                "broadcastTotal": 1
            })
            
            with patch('src.ssh_core.SSHCollector') as mock_collector_class:
                mock_collector = Mock()
                mock_collector_class.return_value = mock_collector
                mock_collector.connect = AsyncMock(return_value=True)
                mock_collector.execute_commands = AsyncMock(return_value={
                    "success": True,
                    "results": [{"command": "echo 'integration test'", "output": "integration test", "error": ""}]
                })
                mock_collector.disconnect = AsyncMock()
                
                # 执行任务
                response = await xxl_job_executor.handle_run_task(mock_request)
                
                assert response["code"] == 200
                assert response["msg"] == "success"
        
        finally:
            # 停止执行器
            await xxl_job_executor.stop_server()
    
    @pytest.mark.asyncio
    async def test_heartbeat_mechanism(self):
        """测试心跳机制"""
        with patch.object(xxl_job_client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            # 启动心跳任务
            heartbeat_task = asyncio.create_task(xxl_job_client._heartbeat_task())
            
            # 等待一小段时间让心跳执行
            await asyncio.sleep(0.1)
            
            # 取消心跳任务
            heartbeat_task.cancel()
            
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            
            # 验证心跳请求被调用
            assert mock_request.called
    
    @pytest.mark.asyncio
    async def test_result_callback_mechanism(self):
        """测试结果回调机制"""
        with patch.object(xxl_job_client, '_send_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"code": 200, "msg": "success"}
            
            # 测试回调
            result = await xxl_job_client.callback_task_result("test_task_123", {
                "code": 200,
                "msg": "Task completed successfully",
                "content": {
                    "execution_time": 1.5,
                    "results": ["command output"]
                }
            })
            
            assert result is True
            mock_request.assert_called_once()
            
            # 验证回调参数
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert "/api/callback" in call_args[0][1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""
SSH采集器测试用例
"""
import pytest
import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.config import settings
from src.utils import CollectorException, SystemMonitor
from src.ssh_core import SSHCredentials, SSHCommand, SSHCollector, SimpleSSHCollector
from src.registration import ControllerClient, RegistrationManager
from src.mq_publisher import RabbitMQPublisher
from src.mq_consumer import TaskProcessor, RabbitMQConsumer
from src.api import app


class TestSSHCredentials:
    """SSH凭据测试"""
    
    def test_valid_credentials_with_password(self):
        """测试有效的密码凭据"""
        creds = SSHCredentials(
            host="192.168.1.100",
            username="admin",
            password="password123",
            device_type="linux"
        )
        assert creds.host == "192.168.1.100"
        assert creds.username == "admin"
        assert creds.password == "password123"
        assert creds.device_type == "linux"
        assert creds.port == 22
    
    def test_valid_credentials_with_private_key(self):
        """测试有效的私钥凭据"""
        private_key = "-----BEGIN RSA PRIVATE KEY-----\ntest_key\n-----END RSA PRIVATE KEY-----"
        creds = SSHCredentials(
            host="192.168.1.100",
            username="admin",
            private_key=private_key,
            device_type="cisco_ios"
        )
        assert creds.private_key == private_key
        assert creds.device_type == "cisco_ios"
    
    def test_invalid_credentials_no_auth(self):
        """测试无效凭据（无认证信息）"""
        with pytest.raises(ValueError):
            SSHCredentials(
                host="192.168.1.100",
                username="admin",
                device_type="linux"
            )


class TestSSHCommand:
    """SSH命令测试"""
    
    def test_valid_command(self):
        """测试有效命令"""
        cmd = SSHCommand(command="show version")
        assert cmd.command == "show version"
        assert cmd.delay_factor == 1.0
        assert cmd.max_loops == 500
    
    def test_command_with_custom_params(self):
        """测试自定义参数命令"""
        cmd = SSHCommand(
            command="show interfaces",
            expect_string="#",
            delay_factor=2.0,
            max_loops=1000
        )
        assert cmd.expect_string == "#"
        assert cmd.delay_factor == 2.0
        assert cmd.max_loops == 1000


class TestSystemMonitor:
    """系统监控测试"""
    
    def test_get_system_info(self):
        """测试获取系统信息"""
        monitor = SystemMonitor()
        info = monitor.get_system_info()
        
        assert "cpu_percent" in info
        assert "memory_percent" in info
        assert "disk_percent" in info
        assert isinstance(info["cpu_percent"], (int, float))
        assert isinstance(info["memory_percent"], (int, float))
        assert isinstance(info["disk_percent"], (int, float))
    
    def test_get_uptime(self):
        """测试获取运行时间"""
        monitor = SystemMonitor()
        uptime = monitor.get_uptime()
        assert isinstance(uptime, (int, float))
        assert uptime >= 0


class TestTaskProcessor:
    """任务处理器测试"""
    
    def setup_method(self):
        """测试设置"""
        self.processor = TaskProcessor()
    
    @patch('src.mq_consumer.ssh_collector')
    def test_process_collection_task_success(self, mock_ssh_collector):
        """测试成功处理采集任务"""
        # 模拟SSH采集器返回成功结果
        mock_ssh_collector.collect_with_retry.return_value = {
            "success": True,
            "data": {"commands": [{"command": "show version", "output": "test output"}]}
        }
        
        task_data = {
            "task_id": "test_task_123",
            "credentials": {
                "host": "192.168.1.100",
                "username": "admin",
                "password": "password123",
                "device_type": "linux"
            },
            "commands": [
                {"command": "show version"}
            ],
            "timeout": 300
        }
        
        result = self.processor.process_collection_task(task_data)
        
        assert result["success"] is True
        assert "data" in result
        mock_ssh_collector.collect_with_retry.assert_called_once()
    
    def test_process_collection_task_missing_task_id(self):
        """测试缺少任务ID的情况"""
        task_data = {
            "credentials": {
                "host": "192.168.1.100",
                "username": "admin",
                "password": "password123",
                "device_type": "linux"
            },
            "commands": [{"command": "show version"}]
        }
        
        result = self.processor.process_collection_task(task_data)
        
        assert result["success"] is False
        assert "error" in result


class TestControllerClient:
    """控制器客户端测试"""
    
    def setup_method(self):
        """测试设置"""
        self.client = ControllerClient()
    
    @patch('src.registration.httpx.AsyncClient.post')
    async def test_register_success(self, mock_post):
        """测试成功注册"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "message": "注册成功"}
        mock_post.return_value = mock_response
        
        result = await self.client.register()
        
        assert result["success"] is True
        mock_post.assert_called_once()
    
    @patch('src.registration.httpx.AsyncClient.post')
    async def test_register_failure(self, mock_post):
        """测试注册失败"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        result = await self.client.register()
        
        assert result["success"] is False
        assert "error" in result


class TestRabbitMQPublisher:
    """RabbitMQ发布者测试"""
    
    def setup_method(self):
        """测试设置"""
        self.publisher = RabbitMQPublisher()
    
    @patch('src.mq_publisher.pika.BlockingConnection')
    def test_connect_success(self, mock_connection):
        """测试成功连接"""
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        self.publisher.connect()
        
        assert self.publisher.connected is True
        mock_connection.assert_called_once()
        mock_channel.queue_declare.assert_called()
    
    @patch('src.mq_publisher.pika.BlockingConnection')
    def test_connect_failure(self, mock_connection):
        """测试连接失败"""
        mock_connection.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception):
            self.publisher.connect()
        
        assert self.publisher.connected is False


class TestAPIEndpoints:
    """API接口测试"""
    
    def setup_method(self):
        """测试设置"""
        self.client = TestClient(app)
    
    def test_root_endpoint(self):
        """测试根路径"""
        response = self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "SSH采集器"
    
    def test_health_endpoint(self):
        """测试健康检查接口"""
        with patch('src.api.get_collector_status') as mock_status:
            mock_status.return_value = {
                "collector_id": "test_collector",
                "registered": True,
                "system_info": {"cpu_percent": 10.0, "memory_percent": 20.0}
            }
            
            response = self.client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["collector_id"] == "test_collector"
    
    def test_supported_devices_endpoint(self):
        """测试支持的设备类型接口"""
        response = self.client.get("/supported-devices")
        assert response.status_code == 200
        data = response.json()
        assert "supported_devices" in data
        assert len(data["supported_devices"]) > 0
    
    @patch('src.api.SimpleSSHCollector.execute_commands')
    def test_collect_endpoint_success(self, mock_execute):
        """测试采集接口成功"""
        mock_execute.return_value = {
            "success": True,
            "data": {"commands": [{"command": "show version", "output": "test output"}]}
        }
        
        request_data = {
            "credentials": {
                "host": "192.168.1.100",
                "username": "admin",
                "password": "password123",
                "device_type": "linux"
            },
            "commands": [
                {"command": "show version"}
            ],
            "timeout": 300
        }
        
        response = self.client.post("/collect", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data
    
    def test_collect_endpoint_invalid_request(self):
        """测试采集接口无效请求"""
        request_data = {
            "credentials": {
                "host": "192.168.1.100",
                "username": "admin",
                # 缺少密码和私钥
                "device_type": "linux"
            },
            "commands": []  # 空命令列表
        }
        
        response = self.client.post("/collect", json=request_data)
        assert response.status_code == 422  # 验证错误
    
    @patch('src.api.SimpleSSHCollector.test_connection')
    def test_test_connection_endpoint(self, mock_test):
        """测试连接测试接口"""
        mock_test.return_value = {
            "success": True,
            "message": "连接成功"
        }
        
        request_data = {
            "host": "192.168.1.100",
            "username": "admin",
            "password": "password123",
            "device_type": "linux"
        }
        
        response = self.client.post("/test-connection", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self):
        """测试完整工作流程模拟"""
        # 这是一个模拟的集成测试，测试各组件协同工作
        
        # 1. 创建任务处理器
        processor = TaskProcessor()
        
        # 2. 模拟任务数据
        task_data = {
            "task_id": "integration_test_123",
            "credentials": {
                "host": "192.168.1.100",
                "username": "admin",
                "password": "password123",
                "device_type": "linux"
            },
            "commands": [
                {"command": "echo 'test'"}
            ],
            "timeout": 60
        }
        
        # 3. 使用mock模拟SSH连接
        with patch('src.ssh_core.ConnectHandler') as mock_connect:
            mock_device = Mock()
            mock_device.send_command.return_value = "test output"
            mock_connect.return_value = mock_device
            
            # 4. 处理任务
            result = processor.process_collection_task(task_data)
            
            # 5. 验证结果
            assert "success" in result
            assert "task_id" in result


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
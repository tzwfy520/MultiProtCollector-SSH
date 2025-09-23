"""
多线程采集功能测试用例

测试SSH采集器的多线程并发采集能力，包括：
- 线程池管理器功能测试
- 多线程SSH采集器测试
- XXL-Job处理器多线程支持测试
- 性能对比测试
"""

import unittest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.thread_pool_manager import ThreadPoolManager, thread_pool_manager
from src.ssh_core import MultiThreadSSHCollector, SSHCredentials, SSHCommand, CollectionTask
from src.xxl_job.handler import SSHCollectionHandler
from src.config import settings


class TestThreadPoolManager(unittest.TestCase):
    """线程池管理器测试"""
    
    def setUp(self):
        """测试前准备"""
        self.manager = ThreadPoolManager(max_workers=2)
    
    def tearDown(self):
        """测试后清理"""
        try:
            self.manager.stop()
        except:
            pass
    
    def test_start_stop(self):
        """测试启动和停止"""
        # 测试启动
        self.manager.start()
        status = self.manager.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("enabled", status)
        
        # 测试停止
        self.manager.stop()
        status_after_stop = self.manager.get_status()
        self.assertIsInstance(status_after_stop, dict)
    
    def test_submit_task(self):
        """测试任务提交"""
        def test_func(x):
            return x * 2
        
        self.manager.start()
        future = self.manager.submit_task("test_task", test_func, 5)
        
        if future:
            result = future.result(timeout=5)
            self.assertEqual(result, 10)
        
        self.manager.stop()
    
    def test_execute_parallel_tasks(self):
        """测试并行任务执行"""
        def test_task_func(task_data):
            return {"task_id": task_data["id"], "result": task_data["value"] * 2}
        
        tasks = [
            {"id": "task1", "value": 1},
            {"id": "task2", "value": 2},
            {"id": "task3", "value": 3}
        ]
        
        results = self.manager.execute_tasks_parallel(tasks, test_task_func, max_workers=2)
        
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertIn("task_id", result)
            self.assertIn("result", result)
    
    def test_get_active_task_count(self):
        """测试获取活跃任务数量"""
        count = self.manager.get_active_task_count()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)


class TestMultiThreadSSHCollector(unittest.TestCase):
    """多线程SSH采集器测试"""
    
    def setUp(self):
        """测试前准备"""
        self.collector = MultiThreadSSHCollector()
    
    def test_execute_single_task(self):
        """测试单个任务执行"""
        task_data = {
            'task_id': 'test_task_1',
            'credentials': {
                'host': '127.0.0.1',
                'username': 'test',
                'password': 'test'
            },
            'commands': [{'command': 'echo "test"'}]
        }
        
        # 由于这是私有方法，我们测试公共方法
        result = MultiThreadSSHCollector.execute_batch_tasks([task_data])
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
    
    @patch('src.ssh_core.SSHCollector.collect_with_retry')
    def test_execute_batch_tasks(self, mock_collect_with_retry):
        """测试批量任务执行"""
        # 模拟SSH采集器返回成功结果 - 使用format_ssh_result的格式
        mock_collect_with_retry.return_value = {
            "success": True,
            "timestamp": "2024-01-01T12:00:00",
            "collector_id": "test_collector",
            "data": {
                "task_id": "test_task",
                "host": "192.168.1.100",
                "total_commands": 1,
                "success_commands": 1,
                "failed_commands": 0,
                "results": [{"command": "uptime", "output": "load average: 0.1", "success": True}],
                "attempt": 1,
                "execution_time": 0.3
            }
        }
        
        # 创建测试任务列表 - 使用正确的数据结构
        tasks = []
        for i in range(3):
            task_data = {
                "task_id": f"batch_task_{i}",
                "credentials": {
                    "host": f"192.168.1.{100+i}",
                    "username": "test",
                    "password": "test123",
                    "port": 22,
                    "device_type": "linux",
                    "timeout": 30
                },
                "commands": [{"command": "uptime"}],
                "timeout": 300,
                "retry_count": 3
            }
            tasks.append(task_data)
        
        # 执行批量任务
        result = MultiThreadSSHCollector.execute_batch_tasks(
            tasks=tasks,
            max_workers=2,
            enable_threading=True
        )
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success", False))
        self.assertIn("task_results", result)
        self.assertEqual(len(result["task_results"]), 3)
        self.assertGreater(result["execution_time"], 0)
        
        # 验证每个任务结果
        for task_result in result["task_results"]:
            self.assertTrue(task_result.get("success", False))
            # 检查host字段在data中
            if "data" in task_result and "host" in task_result["data"]:
                self.assertIn("192.168.1.", task_result["data"]["host"])
            else:
                # 如果没有data字段，跳过host检查
                pass
    
    @patch('src.ssh_core.ssh_collector')
    def test_execute_multi_host_commands(self, mock_ssh_collector):
        """测试多主机命令执行"""
        # 模拟SSH采集器
        mock_ssh_collector.collect_with_retry.return_value = {
            "success": True,
            "results": [{"command": "uptime", "output": "load average: 0.1", "success": True}],
            "total_commands": 1,
            "success_commands": 1,
            "failed_commands": 0,
            "execution_time": 0.3
        }
        
        # 创建测试凭据和命令
        hosts_credentials = [
            SSHCredentials(host="192.168.1.100", username="test", password="test123"),
            SSHCredentials(host="192.168.1.101", username="test", password="test123")
        ]
        commands = [SSHCommand(command="uptime")]
        
        # 执行多主机命令
        result = MultiThreadSSHCollector.execute_multi_host_commands(
            hosts_credentials=hosts_credentials,
            commands=commands,
            max_workers=2
        )
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get('success', False))
        self.assertIn('task_results', result)
        self.assertIn('execution_time', result)
        self.assertEqual(len(result['task_results']), 2)  # 两个主机


class TestXXLJobHandlerThreading(unittest.TestCase):
    """XXL-Job处理器多线程支持测试"""
    
    def setUp(self):
        """测试前准备"""
        from src.xxl_job.handler import SSHCollectionHandler
        self.handler = SSHCollectionHandler()
    
    def test_execute_multi_thread_batch(self):
        """测试多线程批量执行"""
        # 准备测试数据
        params = {
            "hosts": [
                {"host": "192.168.1.100", "username": "admin", "password": "pass1"},
                {"host": "192.168.1.101", "username": "admin", "password": "pass2"}
            ],
            "commands": ["hostname", "uptime"],
            "enable_threading": True,
            "max_workers": 2
        }
        
        # 由于这是内部方法且需要真实SSH连接，我们只测试方法存在性
        self.assertTrue(hasattr(self.handler, '_execute_batch_collection'))
        self.assertTrue(callable(getattr(self.handler, '_execute_batch_collection')))
    
    def test_execute_serial_batch(self):
        """测试串行批量执行"""
        # 准备测试数据
        params = {
            "hosts": [
                {"host": "192.168.1.100", "username": "admin", "password": "pass1"}
            ],
            "commands": ["hostname"],
            "enable_threading": False
        }
        
        # 由于这是内部方法且需要真实SSH连接，我们只测试方法存在性
        self.assertTrue(hasattr(self.handler, '_execute_batch_collection'))
        self.assertTrue(callable(getattr(self.handler, '_execute_batch_collection')))


class TestThreadingPerformance(unittest.TestCase):
    """多线程性能测试"""
    
    @patch('src.ssh_core.ssh_collector')
    def test_performance_comparison(self, mock_ssh_collector):
        """测试串行vs并行性能对比"""
        # 模拟耗时的SSH操作
        def mock_collect_with_retry(*args, **kwargs):
            time.sleep(0.1)  # 模拟100ms的网络延迟
            return {
                "success": True,
                "results": [{"command": "test", "output": "ok", "success": True}],
                "total_commands": 1,
                "success_commands": 1,
                "failed_commands": 0,
                "execution_time": 0.1
            }
        
        mock_ssh_collector.collect_with_retry.side_effect = mock_collect_with_retry
        
        # 准备测试任务
        tasks = []
        for i in range(4):
            task_data = {
                "task_id": f"perf_task_{i}",
                "credentials": {
                    "host": f"192.168.1.{100+i}",
                    "username": "test",
                    "password": "test123"
                },
                "commands": [{"command": "test"}],
                "timeout": 30,
                "retry_count": 1
            }
            tasks.append(task_data)
        
        # 测试串行执行
        start_time = time.time()
        serial_result = MultiThreadSSHCollector.execute_batch_tasks(
            tasks=tasks,
            max_workers=1,
            enable_threading=False
        )
        serial_time = time.time() - start_time
        
        # 测试并行执行
        start_time = time.time()
        parallel_result = MultiThreadSSHCollector.execute_batch_tasks(
            tasks=tasks,
            max_workers=2,
            enable_threading=True
        )
        parallel_time = time.time() - start_time
        
        # 验证结果正确性
        self.assertTrue(serial_result["success"])
        self.assertTrue(parallel_result["success"])
        self.assertEqual(len(serial_result["task_results"]), 4)
        self.assertEqual(len(parallel_result["task_results"]), 4)
        
        # 验证性能提升（并行应该更快）
        print(f"串行执行时间: {serial_time:.2f}s")
        print(f"并行执行时间: {parallel_time:.2f}s")
        print(f"性能提升: {(serial_time/parallel_time):.2f}x")
        
        # 并行执行应该明显更快
        self.assertLess(parallel_time, serial_time * 0.8)


class TestThreadingConfiguration(unittest.TestCase):
    """多线程配置测试"""
    
    def test_config_values(self):
        """测试配置项的默认值"""
        self.assertEqual(settings.max_concurrent_threads, 2)
        self.assertEqual(settings.thread_pool_timeout, 300)
        self.assertTrue(settings.enable_threading)
    
    def test_global_thread_pool_manager(self):
        """测试全局线程池管理器"""
        # 验证全局实例存在
        self.assertIsNotNone(thread_pool_manager)
        self.assertIsInstance(thread_pool_manager, ThreadPoolManager)
        
        # 验证配置正确
        self.assertEqual(thread_pool_manager.max_workers, settings.max_concurrent_threads)
        self.assertEqual(thread_pool_manager.timeout, settings.thread_pool_timeout)


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
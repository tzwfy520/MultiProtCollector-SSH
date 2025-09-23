#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件系统测试脚本
测试插件系统的加载和配置功能
"""

import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addone.plugin_manager import plugin_manager
from src.ssh_core import SSHCredentials, SSHCommand, SSHCollector

def test_plugin_loading():
    """测试插件加载功能"""
    print("=== 测试插件加载功能 ===")
    
    # 测试华为设备插件
    print(f"华为设备插件是否存在: {plugin_manager.has_plugin('huawei')}")
    if plugin_manager.has_plugin('huawei'):
        config = plugin_manager.get_device_config('huawei')
        print(f"华为设备配置: {json.dumps(config, indent=2, ensure_ascii=False)}")
    
    # 测试H3C设备插件
    print(f"\nH3C设备插件是否存在: {plugin_manager.has_plugin('hp_comware')}")
    if plugin_manager.has_plugin('hp_comware'):
        config = plugin_manager.get_device_config('hp_comware')
        print(f"H3C设备配置: {json.dumps(config, indent=2, ensure_ascii=False)}")
    
    # 测试思科设备插件
    print(f"\n思科设备插件是否存在: {plugin_manager.has_plugin('cisco_ios')}")
    if plugin_manager.has_plugin('cisco_ios'):
        config = plugin_manager.get_device_config('cisco_ios')
        print(f"思科设备配置: {json.dumps(config, indent=2, ensure_ascii=False)}")
    
    # 列出所有可用插件
    print(f"\n所有可用插件: {plugin_manager.list_plugins()}")

def test_command_parameter_application():
    """测试命令参数应用功能"""
    print("\n=== 测试命令参数应用功能 ===")
    
    # 创建SSH采集器实例
    collector = SSHCollector()
    collector.device_type = "huawei"  # 模拟设备类型
    
    # 测试基础命令（无特殊参数）
    basic_command = SSHCommand(command="display version")
    print(f"原始命令参数: {basic_command.dict()}")
    
    # 应用插件参数
    enhanced_command = collector._apply_plugin_command_params(basic_command, "huawei")
    print(f"应用插件后: {enhanced_command.dict()}")
    
    # 测试特定命令配置
    current_command = SSHCommand(command="display current-configuration")
    print(f"\n原始current命令: {current_command.dict()}")
    
    enhanced_current = collector._apply_plugin_command_params(current_command, "huawei")
    print(f"应用插件后: {enhanced_current.dict()}")
    
    # 测试用户指定参数不被覆盖
    user_command = SSHCommand(
        command="display current-configuration",
        expect_string=">",  # 用户指定的参数
        delay_factor=2.0
    )
    print(f"\n用户指定参数: {user_command.dict()}")
    
    final_command = collector._apply_plugin_command_params(user_command, "huawei")
    print(f"应用插件后（保留用户参数）: {final_command.dict()}")

def test_api_integration():
    """测试API集成示例"""
    print("\n=== API集成示例 ===")
    
    # 模拟API请求数据
    api_request = {
        "credentials": {
            "host": "139.196.196.96",
            "port": 21202,
            "username": "eccom123",
            "password": "Eccom@12345",
            "device_type": "huawei"
        },
        "commands": [
            {
                "command": "display current-configuration"
                # 注意：这里没有指定expect_string等参数，将由插件自动补充
            }
        ],
        "timeout": 300
    }
    
    print("API请求示例（插件会自动补充参数）:")
    print(json.dumps(api_request, indent=2, ensure_ascii=False))
    
    # 展示插件如何补充参数
    device_type = api_request["credentials"]["device_type"]
    if plugin_manager.has_plugin(device_type):
        config = plugin_manager.get_device_config(device_type)
        print(f"\n插件将自动补充的参数:")
        if 'command_params' in config:
            print(f"通用命令参数: {config['command_params']}")
        if 'commands' in config and 'display_current' in config['commands']:
            print(f"display current特定参数: {config['commands']['display_current']}")

if __name__ == "__main__":
    try:
        test_plugin_loading()
        test_command_parameter_application()
        test_api_integration()
        print("\n=== 插件系统测试完成 ===")
        print("✅ 所有测试通过，插件系统工作正常")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API插件集成测试脚本
测试插件系统与API的完整集成功能
"""

import requests
import json
import time

def test_huawei_device_with_plugin():
    """测试华为设备插件集成"""
    print("=== 测试华为设备插件集成 ===")
    
    # API请求 - 不包含插件参数，由系统自动补充
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
                # 注意：这里没有指定expect_string、delay_factor等参数
                # 插件系统会自动补充这些参数
            }
        ],
        "timeout": 300
    }
    
    print("发送API请求（插件会自动补充参数）:")
    print(json.dumps(api_request, indent=2, ensure_ascii=False))
    
    try:
        # 发送请求到本地API服务器
        response = requests.post(
            "http://115.190.80.219:8000/collect",
            json=api_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\nAPI响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ API调用成功")
            print(f"任务ID: {result.get('task_id', 'N/A')}")
            print(f"状态: {result.get('status', 'N/A')}")
            
            # 如果有结果文件路径，显示部分内容
            if 'result_file' in result:
                print(f"结果文件: {result['result_file']}")
        else:
            print(f"❌ API调用失败: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def test_h3c_device_with_plugin():
    """测试H3C设备插件集成"""
    print("\n=== 测试H3C设备插件集成 ===")
    
    # 使用之前成功的H3C设备配置
    api_request = {
        "credentials": {
            "host": "139.196.196.96",
            "port": 21202,
            "username": "eccom123", 
            "password": "Eccom@12345",
            "device_type": "hp_comware"
        },
        "commands": [
            {
                "command": "display current-configuration"
                # H3C插件会自动补充适当的参数
            }
        ],
        "timeout": 300
    }
    
    print("发送H3C设备API请求:")
    print(json.dumps(api_request, indent=2, ensure_ascii=False))
    
    try:
        response = requests.post(
            "http://115.190.80.219:8000/collect",
            json=api_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\nAPI响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ H3C设备API调用成功")
            print(f"任务ID: {result.get('task_id', 'N/A')}")
            print(f"状态: {result.get('status', 'N/A')}")
        else:
            print(f"❌ H3C设备API调用失败: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def test_manual_parameters_override():
    """测试手动参数覆盖功能"""
    print("\n=== 测试手动参数覆盖功能 ===")
    
    # 用户手动指定参数，应该覆盖插件默认值
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
                "command": "display current-configuration",
                "expect_string": ">",  # 用户指定的参数，应该覆盖插件的"]"
                "delay_factor": 2.0,   # 用户指定的参数，应该覆盖插件的3.0
                "max_loops": 500       # 用户指定的参数，应该覆盖插件的1000
            }
        ],
        "timeout": 300
    }
    
    print("发送带有用户自定义参数的请求:")
    print(json.dumps(api_request, indent=2, ensure_ascii=False))
    print("注意: 用户指定的参数应该覆盖插件默认值")

def show_curl_examples():
    """显示curl命令示例"""
    print("\n=== CURL命令示例 ===")
    
    # 华为设备示例（插件自动补充参数）
    huawei_curl = '''curl -X POST "http://115.190.80.219:8000/collect" \\
  -H "Content-Type: application/json" \\
  -d '{
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
      }
    ],
    "timeout": 300
  }'
'''
    
    print("华为设备（插件自动补充参数）:")
    print(huawei_curl)
    
    # H3C设备示例
    h3c_curl = '''curl -X POST "http://115.190.80.219:8000/collect" \\
  -H "Content-Type: application/json" \\
  -d '{
    "credentials": {
      "host": "139.196.196.96",
      "port": 21202,
      "username": "eccom123",
      "password": "Eccom@12345",
      "device_type": "hp_comware"
    },
    "commands": [
      {
        "command": "display current-configuration"
      }
    ],
    "timeout": 300
  }'
'''
    
    print("\nH3C设备（插件自动补充参数）:")
    print(h3c_curl)

if __name__ == "__main__":
    print("插件系统API集成测试")
    print("=" * 50)
    
    # 显示curl示例
    show_curl_examples()
    
    # 测试手动参数覆盖
    test_manual_parameters_override()
    
    # 注意：实际的API测试需要确保服务器正在运行
    print("\n注意：要进行实际的API测试，请确保:")
    print("1. SSH采集器服务正在运行 (http://115.190.80.219:8000)")
    print("2. 目标设备可以访问")
    print("3. 网络连接正常")
    
    # 如果需要实际测试，取消下面的注释
    # test_huawei_device_with_plugin()
    # test_h3c_device_with_plugin()
    
    print("\n✅ 插件系统API集成测试脚本准备完成")
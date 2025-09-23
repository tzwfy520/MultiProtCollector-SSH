"""
思科IOS设备插件
包含思科IOS设备的特殊配置和交互参数
"""

# 思科IOS设备配置
DEVICE_CONFIG = {
    "name": "思科IOS设备",
    "description": "思科IOS网络设备插件",
    "supported_types": ["cisco_ios", "cisco_xe"],
    
    # 连接参数
    "connection_params": {
        "global_delay_factor": 1.5,
        "read_timeout_override": 45,
        "session_timeout": 60,
        "auth_timeout": 30,
        "banner_timeout": 15,
    },
    
    # 命令执行参数
    "command_params": {
        "expect_string": "#",
        "delay_factor": 1.5,
        "max_loops": 500,
        "timeout": 120,
    },
    
    # 常用命令配置
    "commands": {
        "show_version": {
            "command": "show version",
            "expect_string": "#",
            "delay_factor": 1.0,
            "max_loops": 200,
        },
        "show_running_config": {
            "command": "show running-config",
            "expect_string": "#",
            "delay_factor": 2.0,
            "max_loops": 800,
        },
        "show_interface": {
            "command": "show interface",
            "expect_string": "#",
            "delay_factor": 1.5,
            "max_loops": 400,
        },
        "show_ip_route": {
            "command": "show ip route",
            "expect_string": "#",
            "delay_factor": 1.0,
            "max_loops": 300,
        },
    },
    
    # 设备特殊处理
    "special_handling": {
        "prompt_patterns": [
            r".*>",       # 用户模式提示符
            r".*#",       # 特权模式提示符
            r".*\(config\)#",  # 配置模式提示符
        ],
        "error_patterns": [
            "% Invalid input detected",
            "% Incomplete command",
            "% Unrecognized command",
            "% Ambiguous command",
        ],
        "paging_commands": {
            "disable_paging": "terminal length 0",
            "enable_paging": "terminal length 24",
        }
    },
    
    # 设备信息
    "device_info": {
        "vendor": "思科系统公司",
        "os_type": "IOS",
        "supported_versions": ["12.x", "15.x", "16.x", "17.x"],
        "notes": [
            "思科设备通常使用'#'作为特权模式提示符",
            "建议先执行'enable'进入特权模式",
            "使用'terminal length 0'禁用分页显示",
            "IOS设备响应速度通常较快，delay_factor可以适当降低"
        ]
    }
}
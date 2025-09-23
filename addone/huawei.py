"""
华为设备插件
包含华为设备的特殊配置和交互参数
"""

# 华为设备配置
DEVICE_CONFIG = {
    "name": "华为设备",
    "description": "华为网络设备插件，支持VRP系统",
    "supported_types": ["huawei", "huawei_vrp", "huawei_vrpv8"],
    
    # 连接参数
    "connection_params": {
        "global_delay_factor": 3.0,
        "read_timeout_override": 90,
        "session_timeout": 120,
        "auth_timeout": 60,
        "banner_timeout": 30,
    },
    
    # 命令执行参数
    "command_params": {
        "expect_string": "]",
        "delay_factor": 3.0,
        "max_loops": 1000,
        "timeout": 300,
    },
    
    # 常用命令配置
    "commands": {
        "display_version": {
            "command": "display version",
            "expect_string": "]",
            "delay_factor": 2.0,
            "max_loops": 500,
        },
        "display_current": {
            "command": "display current",
            "expect_string": "]",
            "delay_factor": 3.0,
            "max_loops": 1000,
        },
        "display_current_configuration": {
            "command": "display current-configuration",
            "expect_string": "]",
            "delay_factor": 3.0,
            "max_loops": 2000,
        },
        "display_interface": {
            "command": "display interface",
            "expect_string": "]",
            "delay_factor": 2.0,
            "max_loops": 800,
        },
        "display_ip_routing": {
            "command": "display ip routing-table",
            "expect_string": "]",
            "delay_factor": 2.0,
            "max_loops": 500,
        },
    },
    
    # 设备特殊处理
    "special_handling": {
        "prompt_patterns": [
            r"<.*>",      # 用户视图提示符
            r"\[.*\]",    # 系统视图提示符
            r".*#",       # 特权模式提示符
        ],
        "error_patterns": [
            "Error:",
            "Invalid command",
            "Unrecognized command",
            "Incomplete command",
        ],
        "paging_commands": {
            "disable_paging": "screen-length 0 temporary",
            "enable_paging": "undo screen-length",
        }
    },
    
    # 设备信息
    "device_info": {
        "vendor": "华为技术有限公司",
        "os_type": "VRP",
        "supported_versions": ["V200R003", "V200R005", "V200R010", "V200R019"],
        "notes": [
            "华为设备通常使用']'作为命令结束标识",
            "建议使用较大的delay_factor以确保命令执行完成",
            "对于配置命令，建议增加max_loops参数",
            "部分老版本设备可能需要调整expect_string"
        ]
    }
}
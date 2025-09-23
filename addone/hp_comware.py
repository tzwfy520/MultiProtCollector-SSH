"""
H3C/HP Comware设备插件
包含H3C设备的特殊配置和交互参数
"""

# H3C设备配置
DEVICE_CONFIG = {
    "name": "H3C设备",
    "description": "H3C/HP Comware网络设备插件",
    "supported_types": ["hp_comware", "h3c", "h3c_comware"],
    
    # 连接参数
    "connection_params": {
        "global_delay_factor": 2.0,
        "read_timeout_override": 60,
        "session_timeout": 90,
        "auth_timeout": 30,
        "banner_timeout": 20,
    },
    
    # 命令执行参数
    "command_params": {
        "expect_string": ">",
        "delay_factor": 2.0,
        "max_loops": 500,
        "timeout": 180,
    },
    
    # 常用命令配置
    "commands": {
        "display_version": {
            "command": "display version",
            "expect_string": ">",
            "delay_factor": 1.5,
            "max_loops": 300,
        },
        "display_current_configuration": {
            "command": "display current-configuration",
            "expect_string": ">",
            "delay_factor": 2.0,
            "max_loops": 1000,
        },
        "display_interface": {
            "command": "display interface",
            "expect_string": ">",
            "delay_factor": 2.0,
            "max_loops": 600,
        },
        "display_ip_routing": {
            "command": "display ip routing-table",
            "expect_string": ">",
            "delay_factor": 1.5,
            "max_loops": 400,
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
            "% Unrecognized command",
            "% Incomplete command",
            "% Invalid input",
            "Error:",
        ],
        "paging_commands": {
            "disable_paging": "screen-length disable",
            "enable_paging": "undo screen-length disable",
        }
    },
    
    # 设备信息
    "device_info": {
        "vendor": "新华三技术有限公司",
        "os_type": "Comware",
        "supported_versions": ["V5", "V7"],
        "notes": [
            "H3C设备通常使用'>'作为命令结束标识",
            "Comware系统命令格式与华为类似但有差异",
            "建议使用适中的delay_factor以平衡性能和稳定性",
            "支持screen-length disable命令禁用分页"
        ]
    }
}
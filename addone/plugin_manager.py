"""
插件管理器
负责加载和管理设备类型插件
"""

import os
import importlib.util
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugin_dir: str = None):
        """
        初始化插件管理器
        
        Args:
            plugin_dir: 插件目录路径，默认为当前目录下的addone目录
        """
        if plugin_dir is None:
            # 获取当前文件所在目录
            current_dir = Path(__file__).parent
            self.plugin_dir = current_dir
        else:
            self.plugin_dir = Path(plugin_dir)
        
        self._plugins = {}
        self._load_plugins()
    
    def _load_plugins(self):
        """加载所有插件"""
        if not self.plugin_dir.exists():
            logger.warning(f"插件目录不存在: {self.plugin_dir}")
            return
        
        # 遍历插件目录中的所有.py文件
        for plugin_file in self.plugin_dir.glob("*.py"):
            if plugin_file.name.startswith("__"):
                continue
            
            device_type = plugin_file.stem  # 文件名（不含扩展名）
            try:
                # 动态加载插件模块
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{device_type}", plugin_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # 检查插件是否有必要的配置
                    if hasattr(module, 'DEVICE_CONFIG'):
                        self._plugins[device_type] = module.DEVICE_CONFIG
                        logger.info(f"成功加载插件: {device_type}")
                    else:
                        logger.warning(f"插件 {device_type} 缺少 DEVICE_CONFIG 配置")
                        
            except Exception as e:
                logger.error(f"加载插件 {device_type} 失败: {str(e)}")
    
    def get_device_config(self, device_type: str) -> Optional[Dict[str, Any]]:
        """
        获取设备类型的配置信息
        
        Args:
            device_type: 设备类型
            
        Returns:
            设备配置字典，如果不存在则返回None
        """
        return self._plugins.get(device_type)
    
    def get_supported_devices(self) -> list:
        """获取所有支持的设备类型"""
        return list(self._plugins.keys())
    
    def has_plugin(self, device_type: str) -> bool:
        """检查是否存在指定设备类型的插件"""
        return device_type in self._plugins
    
    def list_plugins(self) -> list:
        """列出所有可用的插件"""
        return list(self._plugins.keys())
    
    def reload_plugins(self):
        """重新加载所有插件"""
        self._plugins.clear()
        self._load_plugins()
    
    def get_plugin_info(self) -> Dict[str, Dict[str, Any]]:
        """获取所有插件的信息"""
        return self._plugins.copy()


# 全局插件管理器实例
plugin_manager = PluginManager()
import os
import importlib
import pkgutil
import inspect
from tools.base import ToolRegistry
from utils.logger import logger
import streamlit as st

# 单例实例
tool_registry = ToolRegistry

def autodiscover():
    """
    自动发现机制：
    扫描 tools/ 目录下的所有 .py 文件，并自动 import 它们。
    """
    package_dir = os.path.dirname(__file__)
    package_name = "tools"
    
    # 遍历目录下的所有模块
    for _, name, _ in pkgutil.iter_modules([package_dir]):
        if name not in ["base", "registry", "__init__"]:
            try:
                importlib.import_module(f"{package_name}.{name}")
            except Exception as e:
                error_msg = f"❌ 严重错误: 工具模块 [{name}] 加载失败! 原因: {e}"
                logger.error(error_msg)
                print(error_msg)
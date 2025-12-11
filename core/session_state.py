import streamlit as st
from core.config_handler import ConfigHandler

def init_session():
    """
    初始化 Session State。
    逻辑：优先读取 Settings.json 的值，确保刷新页面后状态不丢失。
    """
    if "init_done" in st.session_state: return

    config = ConfigHandler.load()
    g_conf = config.get("global", {})

    # 1. 基础变量
    defaults = {
        "messages": [],
        "current_file": None,
        "processed_files": set(),
        "session_id": None,
        "cached_mcp_tools": [],
        "file_uploader_key": 0,  # === 新增：用于强制重置文件上传组件 ===
        "use_plan_solve": False  # === Plan-and-Solve 默认状态 ===
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

    # 2. 从配置恢复功能开关
    legacy_mcp = g_conf.get("use_mcp", False)
    st.session_state['use_custom_tools'] = g_conf.get("use_custom_tools", legacy_mcp)
    st.session_state['use_mcp_protocol'] = g_conf.get("use_mcp_protocol", False)
    st.session_state['use_rag'] = g_conf.get("use_rag", False)
    st.session_state['use_rerank'] = g_conf.get("use_rerank", False)
    st.session_state['system_prompt'] = g_conf.get("system_prompt", "")
    
    # === 恢复 Plan-and-Solve 配置 ===
    st.session_state['use_plan_solve'] = g_conf.get("use_plan_solve", False)
    st.session_state['planning_template'] = g_conf.get("planning_template", "")
    
    # 恢复具体工具的开关
    tools_state = g_conf.get("tools_state", {})
    for t_name, state in tools_state.items():
        st.session_state[f"tool_enabled_{t_name}"] = state

    st.session_state.init_done = True

def sync_setting(key, config_path):
    """回调函数：当 UI 变化时，立即写入 Config"""
    val = st.session_state[key]
    ConfigHandler.update(config_path, val)
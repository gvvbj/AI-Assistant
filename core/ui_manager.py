import streamlit as st
import os
import json
from core.config_handler import ConfigHandler
from core.session_state import sync_setting
from utils.llm_factory import LLMFactory
from tools.registry import tool_registry
from tools.knowledge import knowledge_tool
from core.mcp_manager import McpManager

def render_sidebar():
    config = ConfigHandler.load()
    
    with st.sidebar:
        st.header("🎮 控制台")

        # === 1. 模型选择 ===
        st.subheader("🧠 对话模型")
        c1, c2 = st.columns([0.85, 0.15])
        with c2:
            if st.button("🔄", help="刷新模型列表", key="refresh_models"):
                LLMFactory.get_all_models.clear()
                LLMFactory.get_embedding_models.clear()
                st.rerun()
        with c1:
            all_models = LLMFactory.get_all_models(config)
            curr_idx = 0
            if "selected_model_full" in st.session_state and st.session_state.selected_model_full in all_models:
                curr_idx = all_models.index(st.session_state.selected_model_full)
            
            sel = st.selectbox("选择模型", all_models, index=curr_idx, key="selected_model_full", label_visibility="collapsed")
            if "/" in sel:
                p, m = sel.split("/", 1)
                st.session_state.selected_provider = p
                st.session_state.selected_model = m
            else:
                st.session_state.selected_provider = "Unknown"
                st.session_state.selected_model = sel

        st.divider()

        # === 2. 能力扩展 ===
        st.subheader("🛠️ 能力扩展")

        custom_on_state = st.session_state.get("use_custom_tools", False)
        mcp_on_state = st.session_state.get("use_mcp_protocol", False)
        rag_on_state = st.session_state.get("use_rag", False)
        plan_solve_state = st.session_state.get("use_plan_solve", False)

        if custom_on_state or mcp_on_state or rag_on_state or plan_solve_state:
            st.number_input(
                "🔗 最大连续思考步数", 
                min_value=1, 
                max_value=20, 
                value=5, 
                key="max_tool_steps", 
                help="决定 Agent 自主调用工具的最大循环次数。"
            )
        
        # --- A. 规划模式 (Plan-and-Solve) ---
        st.toggle("📋 规划模式 (Plan-and-Solve)", key="use_plan_solve", on_change=lambda: sync_setting("use_plan_solve", "global.use_plan_solve"))

        # --- B. 本地自定义工具 ---
        custom_on = st.toggle("🧰 自定义工具箱 (Local)", key="use_custom_tools", on_change=lambda: sync_setting("use_custom_tools", "global.use_custom_tools"))
        
        if custom_on:
            st.checkbox("🐍 代码解释器 (Docker)", value=st.session_state.get("tool_enabled_python_interpreter", True),
                        key="tool_enabled_python_interpreter")

            with st.expander("📊 Excel 工具", expanded=False):
                st.checkbox("启用读取", value=st.session_state.get("tool_enabled_excel_read", True), key="tool_enabled_excel_read")
                st.checkbox("启用删除数据", value=st.session_state.get("tool_enabled_excel_delete", True), key="tool_enabled_excel_delete")
                st.checkbox("启用写入数据", value=st.session_state.get("tool_enabled_excel_write", True), key="tool_enabled_excel_write")

        # --- C. MCP 协议集成 ---
        mcp_on = st.toggle("🔌 MCP 协议集成 (Beta)", key="use_mcp_protocol", on_change=lambda: sync_setting("use_mcp_protocol", "global.use_mcp_protocol"))
        
        if mcp_on:
            st.info("管理外部 MCP 服务器及其提供的工具。")
            col_m1, col_m2 = st.columns([1, 1])
            with col_m1:
                if st.button("🔄 刷新工具", use_container_width=True):
                    with st.spinner("连接中..."):
                        tools = McpManager.get_all_tools(force_refresh=True)
                        st.session_state['cached_mcp_tools'] = tools
                        st.success(f"已加载 {len(tools)} 个工具")
            with col_m2:
                st.link_button("应用市场 ↗", "https://glama.ai/mcp/servers", use_container_width=True)

            cached_tools = st.session_state.get('cached_mcp_tools', [])
            servers = config.get("mcp_servers", {})

            if servers:
                for name, conf in servers.items():
                    server_tools = [t for t in cached_tools if t.get('x_mcp_server') == name]
                    with st.expander(f"📦 {name} ({len(server_tools)} tools)", expanded=False):
                        c_en, c_del = st.columns([0.8, 0.2])
                        with c_en:
                            is_active = conf.get('enabled', True)
                            if st.checkbox("启用服务", value=is_active, key=f"mcp_en_{name}"):
                                if not is_active: ConfigHandler.toggle_mcp_server(name, True)
                            else:
                                if is_active: ConfigHandler.toggle_mcp_server(name, False)
                        with c_del:
                            if st.button("🗑️", key=f"del_mcp_{name}"):
                                ConfigHandler.remove_mcp_server(name)
                                st.rerun()
                        st.caption(f"Cmd: `{conf.get('command')} {' '.join(conf.get('args', []))}`")
            else:
                st.caption("暂无服务器")

            with st.expander("➕ 添加新服务器", expanded=False):
                with st.form("add_mcp_server"):
                    s_name = st.text_input("名称 (ID)", placeholder="例如: db_sales")
                    s_cmd = st.text_input("命令", placeholder="uvx")
                    s_args = st.text_input("参数", placeholder="mcp-server-sqlite --db-path data.db")
                    s_env = st.text_area("环境变量 (JSON)", value="{}")
                    
                    if st.form_submit_button("添加"):
                        if s_name and s_cmd:
                            try:
                                args_list = [x.strip() for x in s_args.split(" ") if x.strip()]
                                env_dict = json.loads(s_env) if s_env.strip() else {}
                                ConfigHandler.add_mcp_server(s_name, s_cmd, args_list, env_dict)
                                st.success("添加成功")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.error("名称和命令必填")

        # --- D. RAG 知识库 ---
        rag_on = st.toggle("📚 知识库 RAG", key="use_rag", on_change=lambda: sync_setting("use_rag", "global.use_rag"))

        if rag_on:
            with st.expander("⚙️ RAG 参数设置", expanded=True):
                ollama_url = config.get("providers", {}).get("Ollama", {}).get("base_url", "http://127.0.0.1:11434")
                embed_models = LLMFactory.get_embedding_models(ollama_url)
                st.selectbox("嵌入模型 (Ollama)", embed_models, key="selected_embed_model")
                rerank_on = st.toggle("启用重排序", key="use_rerank", on_change=lambda: sync_setting("use_rerank", "global.use_rerank"))
                if rerank_on:
                    local_models = LLMFactory.get_local_rerank_models()
                    st.selectbox("重排序模型", local_models, key="selected_rerank_model")

            with st.expander("📂 已索引文件列表", expanded=False):
                curr_embed = st.session_state.get("selected_embed_model", "nomic-embed-text")
                files = knowledge_tool.get_files(curr_embed)
                if not files: st.caption(f"当前库为空")
                else:
                    for f in files:
                        c1, c2 = st.columns([0.8, 0.2])
                        c1.text(f)
                        if c2.button("🗑️", key=f"del_{f}"):
                            knowledge_tool.delete_file(f, curr_embed)
                            st.rerun()

        st.divider()

        # === 3. 历史记录 (关键修复：状态重置) ===
        st.subheader("🗄️ 历史会话")
        history_dir = "history"
        os.makedirs(history_dir, exist_ok=True)
        files = sorted([f for f in os.listdir(history_dir) if f.endswith(".json")], reverse=True)
        sel_hist = st.selectbox("历史", ["新对话"] + files, label_visibility="collapsed")
        
        c1, c2 = st.columns([1, 1])
        with c1:
            # “加载”或“新对话”按钮
            if st.button("📂 加载", use_container_width=True):
                # 无论加载旧对话还是新对话，都强制重置文件上传组件
                st.session_state.file_uploader_key += 1
                
                if sel_hist != "新对话":
                    should_rerun = False
                    try:
                        with open(os.path.join(history_dir, sel_hist), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            st.session_state.messages = data
                            st.session_state.session_id = sel_hist
                            st.session_state.current_file = None # 加载历史时不自动关联文件，防止混乱
                            should_rerun = True
                    except Exception as e:
                        st.error(f"加载失败: {e}")
                    
                    if should_rerun:
                        st.rerun()
                else:
                    # 新对话：彻底清空状态
                    st.session_state.messages = []
                    st.session_state.session_id = None
                    st.session_state.current_file = None 
                    st.session_state.processed_files = set()
                    st.rerun()
        with c2:
            if st.button("🗑️ 删除", use_container_width=True):
                st.session_state.file_uploader_key += 1
                if sel_hist != "新对话":
                    os.remove(os.path.join(history_dir, sel_hist))
                    st.rerun()

def render_settings():
    st.title("⚙️ 全局设置")
    config = ConfigHandler.load()
    
    st.subheader("📝 System Prompt")
    sp = st.text_area("提示词", value=st.session_state.get("system_prompt", ""), height=100)
    if st.button("💾 保存提示词"):
        ConfigHandler.update("global.system_prompt", sp)
        st.session_state.system_prompt = sp
        st.toast("已保存")

    st.divider()
    
    # === Plan-and-Solve 设置 ===
    st.subheader("📋 规划模式配置")
    plan_on = st.session_state.get("use_plan_solve", False)
    
    if plan_on:
        st.caption("Plan-and-Solve 已在侧边栏启用。请在此处编辑生成计划的 Prompt 模板。")
        plan_template = st.text_area(
            "规划提示词模板 (必须包含 {prompt} 占位符)",
            value=st.session_state.get("planning_template", config["global"].get("planning_template", "")),
            height=150,
            key="setting_plan_template"
        )
        if st.button("💾 保存规划模板"):
            if "{prompt}" not in plan_template:
                st.error("❌ 错误：模板必须包含 {prompt} 占位符")
            else:
                ConfigHandler.update("global.planning_template", plan_template)
                st.session_state.planning_template = plan_template
                st.toast("规划模板已保存")
    else:
        st.info("请先在侧边栏启用 '规划模式 (Plan-and-Solve)' 以配置模板。")

    st.divider()

    st.subheader("🔌 API 管理")
    
    for name, conf in config.get("providers", {}).items():
        with st.expander(f"{'🟢' if conf.get('enabled') else '⚪'} {name}", expanded=False):
            c1, c2 = st.columns([3, 1])
            with c1: en = st.checkbox("启用", value=conf.get("enabled", False), key=f"en_{name}")
            with c2: 
                if name != "Ollama" and st.button("🗑️", key=f"del_{name}"):
                    ConfigHandler.remove_provider(name)
                    st.rerun()
            
            url = st.text_input("URL", value=conf.get("base_url", ""), key=f"url_{name}")
            kv = conf.get("api_key", "")
            key = st.text_input("Key", value=kv, type="password", key=f"k_{name}", placeholder="保持不变" if kv else "")
            mods = st.text_area("Models", value=",".join(conf.get("models", [])), key=f"m_{name}")
            
            if st.button("更新", key=f"upd_{name}"):
                ConfigHandler.update(f"providers.{name}.enabled", en)
                ConfigHandler.update(f"providers.{name}.base_url", url)
                if key: ConfigHandler.update(f"providers.{name}.api_key", key)
                ConfigHandler.update(f"providers.{name}.models", [m.strip() for m in mods.split(",") if m.strip()])
                LLMFactory.get_all_models.clear()
                st.rerun()

    with st.expander("➕ 添加服务商"):
        with st.form("add_p"):
            n = st.text_input("名称")
            u = st.text_input("URL")
            k = st.text_input("Key", type="password")
            m = st.text_input("Models (逗号分隔)")
            if st.form_submit_button("添加") and n and u:
                ConfigHandler.add_provider(n, u, k, m)
                LLMFactory.get_all_models.clear()
                st.rerun()
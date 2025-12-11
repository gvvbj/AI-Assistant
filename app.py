import os
import sys

os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"

import streamlit as st
from core.session_state import init_session
from core.ui_manager import render_sidebar, render_settings
from core.workflow import process_chat
from tools.knowledge import knowledge_tool
from utils.stream_parser import StreamParser
# 引入工具
from utils.file_utils import is_image_file
from utils.video_utils import is_video_file # 新增

os.makedirs("models", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

init_session()

st.set_page_config(page_title="AI Assistant Pro", layout="wide", page_icon="🤖")

page = st.sidebar.radio("导航", ["💬 对话", "⚙️ 设置"], label_visibility="collapsed")
render_sidebar()

if page == "⚙️ 设置":
    render_settings()
else:
    st.title("🤖 AI 助手 Pro")
    
    with st.expander("📂 文件上传 (RAG/Excel)", expanded=False):
        uploader_key = f"file_uploader_{st.session_state.get('file_uploader_key', 0)}"
        uploaded_files = st.file_uploader("拖拽文件", accept_multiple_files=True, key=uploader_key)
        
        if not uploaded_files:
            st.session_state.current_file = None
        
        if uploaded_files:
            first_file = uploaded_files[0]
            st.session_state.current_file = os.path.join("uploads", first_file.name)
            
            for f in uploaded_files:
                path = os.path.join("uploads", f.name)
                with open(path, "wb") as w: w.write(f.getbuffer())
                
                is_excel = f.name.endswith(".xlsx") or f.name.endswith(".xls")
                
                if is_excel:
                    st.caption(f"📊 Excel 已就绪: {f.name} (可使用工具读取/分析)")
                
                if st.session_state.use_rag:
                    if not is_excel: 
                        current_embed = st.session_state.get("selected_embed_model", "nomic-embed-text")
                        with st.spinner(f"正在索引 {f.name}..."):
                            msg = knowledge_tool.add_document(path, current_embed)
                            if "失败" in msg or "不支持" in msg: 
                                st.warning(msg) 
                            else: 
                                st.toast(msg)

    # === 历史消息渲染 ===
    for msg in st.session_state.messages:
        role = msg["role"]
        
        if role == "user":
            with st.chat_message("user"):
                # 处理多模态历史显示
                content = msg["content"]
                # 兼容旧版本 History (Context File 是拼接到 string 的)
                # 也要兼容新版本 (Context File 只是一个标记)
                # 最简单的做法：直接渲染内容，如果包含 [Context File: xxx]，解析并显示媒体
                
                # 这里的 content 无论是 list 还是 string，在 workflow.py 保存时都转成了 string
                # 所以我们只需正则提取路径进行显示增强
                
                display_text = str(content)
                file_path = None
                
                if "[Context File:" in display_text:
                    import re
                    match = re.search(r"\[Context File: (.*?)\]", display_text)
                    if match:
                        file_path = match.group(1)
                        # 从显示文本中移除这个标记，或者保留它作为引用
                        # 这里我们选择保留，但额外在下方渲染媒体
                
                st.markdown(display_text)
                
                if file_path and os.path.exists(file_path):
                    fname = os.path.basename(file_path)
                    if is_image_file(file_path):
                        st.image(file_path, caption=fname, width=300)
                    elif is_video_file(file_path):
                        st.video(file_path)
                        st.caption(f"📹 {fname}")
        
        elif role == "assistant":
            with st.chat_message("assistant"):
                content = msg.get("content")
                if content:
                    thought, main_text = StreamParser.extract_think_static(content)
                    if thought:
                        with st.status("💡 思考过程", expanded=False, state="complete"):
                            st.markdown(thought)
                    if main_text:
                        st.markdown(main_text)

        elif role == "tool":
            tool_name = msg.get("name", "Unknown")
            is_kb = tool_name == "kb_search"
            
            with st.expander(f"🛠️ 工具结果: {tool_name}", expanded=False):
                if is_kb:
                    st.markdown(msg.get("content"))
                else:
                    st.code(msg.get("content")[:2000])

    if prompt := st.chat_input("输入问题..."):
        process_chat(prompt)
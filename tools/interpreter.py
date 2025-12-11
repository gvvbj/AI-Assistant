import streamlit as st
import os
import re
from tools.registry import tool_registry
from tools.sandbox import DockerSandbox
from utils.error_handling import safe_execute

# 确保沙箱实例存在
if "sandbox_instance" not in st.session_state:
    st.session_state["sandbox_instance"] = None

# === 新增：初始化文件同步状态字典 ===
# 用于存储 { "filename": last_modified_timestamp }
if "uploaded_file_stats" not in st.session_state:
    st.session_state["uploaded_file_stats"] = {}

def get_sandbox():
    session_id = st.session_state.get("session_id", "default_session")
    if not session_id: session_id = "temp_session"
    
    if "sandbox_instance" not in st.session_state:
        st.session_state["sandbox_instance"] = None

    if st.session_state["sandbox_instance"] is None:
        st.session_state["sandbox_instance"] = DockerSandbox(session_id)
        
    return st.session_state["sandbox_instance"]

def _clean_markdown_code(code: str) -> str:
    if not code: return ""
    code = re.sub(r"^```(python)?\s*\n", "", code.strip(), flags=re.IGNORECASE | re.MULTILINE)
    code = re.sub(r"\n\s*```\s*$", "", code, flags=re.MULTILINE)
    return code.strip()

@tool_registry.register(
    name="python_interpreter",
    description="Python Code Interpreter. Use this to analyze data, plot charts, or process files. \n"
                "The user's file is ALREADY in the current directory '/workspace'. \n"
                "IMPORTANT: If you modify a file, please save it with a NEW filename ending in '_new' or '_processed' (e.g., 'data_new.xlsx') instead of overwriting the original file. This helps the user distinguish the output.",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The python code to execute."
            }
        },
        "required": ["code"]
    }
)
@safe_execute("代码执行失败")
def run_python_code(code):
    sb = get_sandbox()
    
    # 1. 清洗代码
    code = _clean_markdown_code(code)
    
    # 2. 文件同步 (智能同步逻辑)
    current_file = st.session_state.get("current_file")
    
    if current_file and os.path.exists(current_file):
        file_name = os.path.basename(current_file)
        
        try:
            # 获取本地文件的最后修改时间
            local_mtime = os.path.getmtime(current_file)
            
            # 获取上次上传记录的时间
            last_upload_mtime = st.session_state["uploaded_file_stats"].get(file_name)
            
            # === 核心判断：只有时间戳变了，或者没传过，才执行上传 ===
            if last_upload_mtime != local_mtime:
                sb.copy_to_container(current_file)
                # 更新状态
                st.session_state["uploaded_file_stats"][file_name] = local_mtime
            else:
                # 文件未修改，跳过上传，避免日志刷屏和IO浪费
                pass 
                
        except Exception as e:
            return f"文件同步失败: {str(e)}"
        
        # 3. 路径修复 (保持原有的暴力清洗逻辑)
        clean_current_path = current_file.replace("\\", "/")
        
        # A. 替换具体文件名
        code = code.replace(current_file, file_name)       
        code = code.replace(clean_current_path, file_name) 
        
        # B. 暴力移除 uploads 前缀
        code = code.replace("uploads/", "").replace("uploads\\", "")
        
        # C. 替换相对路径
        code = code.replace(f"/{file_name}", file_name)
        code = code.replace(f"./{file_name}", file_name)
        
        # D. 处理目录前缀
        dir_name = os.path.dirname(current_file)
        if dir_name:
            full_path_str = os.path.join(dir_name, file_name)
            code = code.replace(full_path_str, file_name)
            if "\\" in full_path_str:
                code = code.replace(full_path_str.replace("\\", "\\\\"), file_name)

    # 4. 执行代码
    output, files = sb.execute_code(code)
    
    # 5. 结果格式化
    res_msg = f"Output:\n{output}"
    
    if files:
        res_msg += "\nGenerated Files:\n"
        for f in files:
            res_msg += f"[FILE_GENERATED]:{f}\n"
            
    if not output and not files:
        return "Code executed successfully (No output)."
        
    return res_msg
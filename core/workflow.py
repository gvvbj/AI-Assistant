import streamlit as st
import json
import datetime
import os
import uuid
import re
import time
import tools.excel 
import tools.interpreter
from utils.llm_factory import LLMFactory
from tools.registry import tool_registry, autodiscover
autodiscover()
from core.config_handler import ConfigHandler
from utils.logger import logger
from utils.stream_parser import StreamParser
from core.mcp_manager import McpManager

def save_history():
    if not st.session_state.messages: return
    msgs = st.session_state.messages
    
    if not st.session_state.session_id:
        first_q = "new_chat"
        for m in msgs:
            if m['role'] == 'user':
                raw_content = str(m['content'])
                if "\n[Context File:" in raw_content:
                    raw_content = raw_content.split("\n[Context File:")[0]
                clean_name = re.sub(r'[\\/*?:"<>|\n\r\t]', "", raw_content)
                clean_name = clean_name.strip().replace(" ", "_")[:20]
                if clean_name:
                    first_q = clean_name
                break
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.session_id = f"{timestamp}_{first_q}.json"
    
    os.makedirs("history", exist_ok=True)
    path = os.path.join("history", st.session_state.session_id)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存历史失败: {e}")

def _normalize_tool_calls(raw_tool_calls):
    normalized = []
    if not raw_tool_calls: return normalized

    for tc in raw_tool_calls:
        tc_id = None
        if hasattr(tc, 'id'): tc_id = tc.id
        elif isinstance(tc, dict): tc_id = tc.get('id')
        if not tc_id: tc_id = f"call_{uuid.uuid4().hex[:8]}"

        name = ""
        arguments = "{}"
        
        if hasattr(tc, 'function'):
            name = tc.function.name
            arguments = tc.function.arguments
        elif isinstance(tc, dict):
            func = tc.get('function', {})
            name = func.get('name', '')
            arguments = func.get('arguments', '{}')

        if isinstance(arguments, dict): arguments = json.dumps(arguments)

        if name:
            normalized.append({
                "id": tc_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments
                }
            })
    return normalized

def process_chat(prompt):
    config = ConfigHandler.load()
    base_sys_prompt = st.session_state.get("system_prompt", "You are a helpful AI assistant.")
    
    # 1. 上下文文件处理
    context_suffix = ""
    if st.session_state.get("current_file") and os.path.exists(st.session_state.current_file):
        context_suffix = f"\n[Context File: {st.session_state.current_file}]"
    
    st.session_state.messages.append({"role": "user", "content": prompt + context_suffix})
    
    with st.chat_message("user"): 
        display_text = prompt
        if st.session_state.get("current_file"):
            display_text += f" `📎 {os.path.basename(st.session_state.current_file)}`"
        st.markdown(display_text)

    # 2. System Prompt
    final_sys_prompt = base_sys_prompt 

    provider = st.session_state.get("selected_provider", "Ollama")
    model = st.session_state.get("selected_model", "qwen2.5:3b")
    p_conf = config["providers"].get(provider, {})

    # === 3. Plan-and-Solve 逻辑 (新增) ===
    # 动态获取配置的模板和开关状态
    plan_template = st.session_state.get("planning_template") or config["global"].get("planning_template")
    use_plan_solve = st.session_state.get("use_plan_solve", False)

    if use_plan_solve and plan_template:
        # 只在当前是新的一轮对话时执行规划（防止重绘导致的重复调用逻辑问题，不过这里是 process_chat 入口，通常每次点击发送才会调用）
        with st.status("📋 正在规划执行步骤...", expanded=True) as status:
            try:
                # 构造规划专用的提示词
                # 兼容 Prompt 中可能不存在占位符的情况
                if "{prompt}" in plan_template:
                    final_plan_prompt = plan_template.replace("{prompt}", prompt)
                else:
                    final_plan_prompt = f"{plan_template}\n\nUser request: {prompt}"

                # 创建临时的 Client 进行一次性规划调用 (非流式)
                client = LLMFactory.create_client(provider, p_conf)
                plan_msgs = [{"role": "user", "content": final_plan_prompt}]
                
                resp = client.chat.completions.create(
                    model=model,
                    messages=plan_msgs,
                    temperature=0.7 # 规划需要一点创造性
                )
                plan_content = resp.choices[0].message.content
                
                if plan_content and "No plan needed" not in plan_content and len(plan_content) > 5:
                    status.markdown(plan_content)
                    status.update(label="✅ 计划已生成", state="complete", expanded=True)
                    
                    # 将计划注入到 System Prompt 中，指导接下来的 ReAct 循环
                    final_sys_prompt += f"\n\n[APPROVED PLAN]\n{plan_content}\n\nInstruction: Follow the plan above step by step. Use tools to execute each step."
                else:
                    status.update(label="ℹ️ 无需复杂规划", state="complete", expanded=False)
                    
            except Exception as e:
                # 规划失败不应阻断主流程，记录错误并降级回普通模式
                logger.error(f"Plan generation failed: {e}")
                status.update(label="⚠️ 规划生成失败，切换回普通模式", state="error", expanded=False)

    # === 4. 工具加载逻辑 (保持原有) ===
    tools = []
    local_tool_map = {} 
    
    if st.session_state.get("use_custom_tools", False):
        raw_schemas, mapping = tool_registry.get_openai_tools()
        for t in raw_schemas:
            if t['function']['name'] != 'kb_search':
                tools.append(t)
        local_tool_map.update(mapping)

    if st.session_state.get("use_rag", False):
        rag_schema = tool_registry.get_rag_schema()
        tools.append(rag_schema)

    if st.session_state.get("use_mcp_protocol", False):
        try:
            mcp_tools = McpManager.get_all_tools()
            if mcp_tools:
                if tools is None: tools = []
                tools.extend(mcp_tools)
        except Exception as e:
            logger.error(f"MCP工具加载失败: {e}")

    if not tools: tools = None

    with st.expander("🔧 DEBUG: 发送给模型的工具列表", expanded=False):
        if tools:
            names = [t['function']['name'] for t in tools]
            st.write(f"当前激活: {names}")
        else:
            st.warning("当前无激活工具")

    max_steps = st.session_state.get("max_tool_steps", 5)

    with st.chat_message("assistant"):
        step_counter = 1 
        loop_count = 0
        final_response_generated = False 

        while loop_count < max_steps:
            loop_count += 1
            
            msgs_for_llm = [{"role": "system", "content": final_sys_prompt}] + \
                           [m for m in st.session_state.messages if m["role"] != "system"][-20:]

            status_container = None
            thought_placeholder = None
            content_placeholder = st.empty()
            
            parser = StreamParser() 
            tool_calls_chunks = []  
            full_final_content = "" 
            
            try:
                stream = LLMFactory.chat_stream(provider, p_conf, model, msgs_for_llm, tools)
            except Exception as e:
                st.error(f"API请求失败: {e}")
                break

            last_update_time = 0
            update_interval = 0.05 

            for chunk in stream:
                if isinstance(chunk, dict) and "error" in chunk:
                    content_placeholder.error(chunk['error'])
                    full_final_content = chunk['error']
                    break

                delta = None
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                
                if not delta: continue

                is_thought, text_chunk = parser.parse(delta)
                
                current_time = time.time()
                should_update = (current_time - last_update_time > update_interval)

                if is_thought:
                    if text_chunk:
                        if status_container is None:
                            status_container = st.status("🤔 深度思考中...", expanded=True)
                            with status_container:
                                thought_placeholder = st.empty()
                        
                        if should_update and thought_placeholder:
                            thought_placeholder.markdown(parser.thought_content + "▌")
                            last_update_time = current_time
                else:
                    if text_chunk:
                        full_final_content += text_chunk
                        if should_update:
                            if status_container and parser.thought_content:
                                thought_placeholder.markdown(parser.thought_content) 
                                status_container.update(label="💡 思考完成", state="complete", expanded=False)
                                status_container = None 
                            
                            content_placeholder.markdown(full_final_content + "▌")
                            last_update_time = current_time

                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        if len(tool_calls_chunks) <= tc_chunk.index:
                            tool_calls_chunks.append({
                                "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                            })
                        if tc_chunk.id:
                            tool_calls_chunks[tc_chunk.index]["id"] += tc_chunk.id
                        if tc_chunk.function.name:
                            tool_calls_chunks[tc_chunk.index]["function"]["name"] += tc_chunk.function.name
                        if tc_chunk.function.arguments:
                            tool_calls_chunks[tc_chunk.index]["function"]["arguments"] += tc_chunk.function.arguments

            # 循环内的渲染收尾
            if status_container and parser.thought_content:
                thought_placeholder.markdown(parser.thought_content)
                status_container.update(label="💡 思考完成", state="complete", expanded=False)
            
            if full_final_content:
                content_placeholder.markdown(full_final_content)
            elif not tool_calls_chunks:
                content_placeholder.empty()

            if not tool_calls_chunks:
                final_msg_content = full_final_content
                if parser.thought_content:
                    final_msg_content = f"<think>{parser.thought_content}</think>\n{full_final_content}"
                st.session_state.messages.append({"role": "assistant", "content": final_msg_content})
                final_response_generated = True
                break 

            saved_content = full_final_content
            if parser.thought_content:
                saved_content = f"<think>{parser.thought_content}</think>\n{full_final_content}"

            assistant_msg = {
                "role": "assistant", 
                "content": saved_content if saved_content else None,
                "tool_calls": tool_calls_chunks
            }
            st.session_state.messages.append(assistant_msg)

            # 执行工具
            clean_tool_calls = _normalize_tool_calls(tool_calls_chunks)
            for tc in clean_tool_calls:
                tc_id = tc['id']
                func_name = tc['function']['name']
                args_str = tc['function']['arguments']
                try: args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except: args = {}

                status_label = f"Step {step_counter}: 执行 {func_name}"
                with st.status(status_label, state="running") as s:
                    try:
                        res = ""
                        if func_name == "kb_search":
                            from tools.knowledge import knowledge_tool
                            embed_model = st.session_state.get("selected_embed_model", "nomic-embed-text")
                            rerank_model = st.session_state.get("selected_rerank_model") if st.session_state.get("use_rerank") else None
                            res = knowledge_tool.search(args.get("query"), embed_model, rerank_model)
                            s.update(label=f"✅ Step {step_counter}: 检索完成", state="complete")
                            with st.expander("📚 引用内容", expanded=False):
                                st.markdown(str(res))
                        
                        elif func_name in local_tool_map:
                            res = tool_registry.execute(func_name, args)
                            res_str = str(res)
                            
                            # === 修复：恢复下载按钮逻辑 ===
                            if "[FILE_GENERATED]:" in res_str or "[IMAGE_GENERATED]:" in res_str:
                                s.update(label=f"✅ Step {step_counter}: 文件/图表生成成功", state="complete")
                                
                                lines = res_str.split('\n')
                                clean_lines = []
                                for line in lines:
                                    if "[IMAGE_GENERATED]:" in line:
                                        img_path = line.split(":", 1)[1].strip()
                                        if os.path.exists(img_path):
                                            st.image(img_path, caption=os.path.basename(img_path))
                                    elif "[FILE_GENERATED]:" in line:
                                        # 关键：这里要解析路径并显示下载按钮
                                        f_path = line.split(":", 1)[1].strip()
                                        f_name = os.path.basename(f_path)
                                        if os.path.exists(f_path):
                                            with open(f_path, "rb") as f:
                                                st.download_button(
                                                    label=f"⬇️ 下载 {f_name}",
                                                    data=f,
                                                    file_name=f_name,
                                                    key=f"dl_{f_name}_{uuid.uuid4()}"
                                                )
                                    else:
                                        clean_lines.append(line)
                                
                                st.code("\n".join(clean_lines)[:1000])
                            else:
                                s.update(label=f"✅ Step {step_counter}: {func_name} (Local) 完成", state="complete")
                                st.code(str(res)[:800])

                        else:
                            res = McpManager.execute_tool(func_name, args)
                            s.update(label=f"✅ Step {step_counter}: {func_name} (MCP) 完成", state="complete")
                            st.code(str(res)[:1000])

                        st.session_state.messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": func_name,
                            "content": str(res)
                        })
                    except Exception as e:
                        s.update(label=f"❌ Step {step_counter}: {func_name} 失败", state="error")
                        st.error(str(e))
                        st.session_state.messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": func_name,
                            "content": f"Error: {str(e)}"
                        })
                step_counter += 1
            
            continue 
        
        # === 5. (优化版V2) 强制交互式总结 ===
        # 逻辑：如果循环结束（max_steps）但模型还停留在 tool 阶段，
        # 我们**伪造一条用户消息**（Fake User Message），强迫模型回答。
        # 这种方式比 System Prompt 有效得多，因为模型必须响应用户的“最新指令”。
        if not final_response_generated and st.session_state.messages[-1]["role"] == "tool":
            st.info(f"⚠️ 已达到设置的最大步数 ({max_steps})，正在尝试生成总结...")
            
            # 伪造的用户指令，不加入历史记录 st.session_state.messages，只传给模型
            fake_user_instruction = {
                "role": "user", 
                "content": f"System Alert: The maximum tool execution limit ({max_steps}) has been reached. Please STOP using tools immediately. Based on the information you have gathered so far, provide a final summary or answer to my original request."
            }
            
            # 构造临时的消息列表
            summary_msgs = [{"role": "system", "content": final_sys_prompt}] + \
                           [m for m in st.session_state.messages if m["role"] != "system"][-20:] + \
                           [fake_user_instruction]
            
            content_placeholder = st.empty()
            full_final_content = ""
            try:
                # 关键：传入 tools=None，物理禁止工具调用
                stream = LLMFactory.chat_stream(provider, p_conf, model, summary_msgs, tools=None)
                for chunk in stream:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_final_content += delta.content
                            content_placeholder.markdown(full_final_content + "▌")
                
                content_placeholder.markdown(full_final_content)
                # 将这条强制生成的回复加入历史，作为 Assistant 的最终回答
                st.session_state.messages.append({"role": "assistant", "content": full_final_content})
            except Exception as e:
                st.error(f"最终回答生成失败: {e}")

    save_history()
import functools
import streamlit as st
import traceback

class ToolRegistry:
    _tools = {}

    @classmethod
    def register(cls, name, description, parameters):
        def decorator(func):
            cls._tools[name] = {
                "func": func,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters
                    }
                }
            }
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator

    @classmethod
    def execute(cls, name, args):
        """
        执行工具，包含增强的错误处理和参数验证机制 (Robustness)
        """
        if name not in cls._tools:
            available = list(cls._tools.keys())
            return f"Error: Tool '{name}' not found. Available tools: {available}"
        
        func = cls._tools[name]["func"]
        
        try:
            # 尝试直接执行
            return func(**args)
        except TypeError as e:
            # === 核心修复：参数不匹配时的自愈提示 ===
            # 如果 LLM 传错了参数名，捕获错误并返回提示，让 LLM 在下一步重试
            error_msg = str(e)
            if "required positional argument" in error_msg or "unexpected keyword argument" in error_msg:
                # 获取函数签名的真实参数名
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                return f"Error: Arguments mismatch for tool '{name}'. The function expects parameters: {params}. You provided: {list(args.keys())}. Error details: {error_msg}"
            
            # 其他 TypeError 直接抛出或返回
            traceback.print_exc()
            return f"Execution Error: {error_msg}"
        except Exception as e:
            traceback.print_exc()
            return f"Execution Error: {str(e)}"

    @classmethod
    def get_openai_tools(cls):
        enabled_tools = []
        mapping = {}
        for name, data in cls._tools.items():
            if st.session_state.get(f"tool_enabled_{name}", True): 
                enabled_tools.append(data["schema"])
                mapping[name] = data["func"]
        return enabled_tools, mapping

    @staticmethod
    def get_rag_schema():
        return {
            "type": "function",
            "function": {
                "name": "kb_search",
                "description": "Search the knowledge base.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query string"}
                    },
                    "required": ["query"]
                }
            }
        }
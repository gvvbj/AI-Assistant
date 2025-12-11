import asyncio
import os
import shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from core.config_handler import ConfigHandler
from utils.logger import logger
from utils.error_handling import safe_execute

class McpManager:
    """
    管理 MCP 服务器连接、工具发现与执行。
    为了适应 Streamlit 的同步环境，这里封装了 asyncio loop。
    """
    
    # 内存缓存
    _tool_cache = {} 
    _tool_to_server_map = {}

    @staticmethod
    def get_enabled_servers():
        config = ConfigHandler.load()
        servers = config.get("mcp_servers", {})
        return {k: v for k, v in servers.items() if v.get("enabled", True)}

    @staticmethod
    def clear_cache():
        McpManager._tool_cache = {}
        McpManager._tool_to_server_map = {}

    @staticmethod
    async def _list_tools_async(name, conf):
        """连接单个服务器并获取工具列表"""
        tools_schema = []
        
        env_vars = os.environ.copy()
        if conf.get("env"):
            env_vars.update(conf.get("env"))

        server_params = StdioServerParameters(
            command=conf["command"],
            args=conf.get("args", []),
            env=env_vars
        )
        
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    
                    for tool in result.tools:
                        # 构造 OpenAI 兼容的 Schema
                        schema = {
                            "type": "function",
                            "function": {
                                "name": tool.name, 
                                "description": tool.description,
                                "parameters": tool.inputSchema
                            },
                            # === 关键修改：注入服务器名称，用于 UI 分组 ===
                            "x_mcp_server": name 
                        }
                        tools_schema.append(schema)
                        
        except Exception as e:
            logger.error(f"[MCP] Server '{name}' list_tools failed: {e}")
            return [], name
            
        return tools_schema, name

    @staticmethod
    def get_all_tools(force_refresh=False):
        """获取所有启用的 MCP 服务器的工具（同步包装）"""
        if not force_refresh and McpManager._tool_cache:
            return list(McpManager._tool_cache.values())

        servers = McpManager.get_enabled_servers()
        if not servers: return []

        tasks = []
        for name, conf in servers.items():
            tasks.append(McpManager._list_tools_async(name, conf))
        
        if not tasks: return []

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(asyncio.gather(*tasks))
            loop.close()
            
            # 重置缓存
            McpManager._tool_cache = {}
            McpManager._tool_to_server_map = {}
            
            all_tools = []
            for tools, server_name in results:
                for tool in tools:
                    t_name = tool['function']['name']
                    McpManager._tool_cache[t_name] = tool
                    McpManager._tool_to_server_map[t_name] = server_name
                    all_tools.append(tool)
                    
            return all_tools
        except Exception as e:
            logger.error(f"[MCP] Get tools error: {e}")
            return []

    @staticmethod
    async def _execute_tool_async(server_name, tool_name, arguments):
        servers = McpManager.get_enabled_servers()
        conf = servers.get(server_name)
        if not conf:
            raise ValueError(f"MCP Server '{server_name}' not found or disabled.")

        env_vars = os.environ.copy()
        if conf.get("env"):
            env_vars.update(conf.get("env"))

        server_params = StdioServerParameters(
            command=conf["command"],
            args=conf.get("args", []),
            env=env_vars
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    # 调用 MCP 工具
                    result = await session.call_tool(tool_name, arguments)
                    
                    output = []
                    for content in result.content:
                        if content.type == 'text':
                            output.append(content.text)
                        elif content.type == 'image':
                            output.append(f"[Image Data: {content.mimeType}]") 
                        elif content.type == 'resource':
                            output.append(f"[Resource: {content.uri}]")
                    return "\n".join(output)
        except Exception as e:
            raise e

    @staticmethod
    def execute_tool(tool_name, arguments):
        """执行 MCP 工具（同步包装），自动查找所属服务器"""
        server_name = McpManager._tool_to_server_map.get(tool_name)
        
        if not server_name:
            McpManager.get_all_tools(force_refresh=True)
            server_name = McpManager._tool_to_server_map.get(tool_name)
            
        if not server_name:
            return f"Error: Tool '{tool_name}' not found in any active MCP server."

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(McpManager._execute_tool_async(server_name, tool_name, arguments))
            loop.close()
            return res
        except Exception as e:
            logger.error(f"[MCP] Execution failed: {e}")
            return f"MCP Execution Error: {str(e)}"
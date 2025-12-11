import json
import os
import copy
from utils.security import SecurityManager
from utils.logger import logger

SETTINGS_FILE = "settings.json"

DEFAULT_CONFIG = {
    "providers": {
        "Ollama": {"enabled": True, "base_url": "http://127.0.0.1:11434", "models": []},
        "OpenAI": {"enabled": False, "base_url": "https://api.openai.com/v1", "api_key": "", "models": ["gpt-4o", "gpt-3.5-turbo"]}
    },
    "global": {
        "system_prompt": "You are a helpful AI assistant.",
        "use_custom_tools": False,  # 原 use_mcp 改名，指代本地 Python 工具
        "use_mcp_protocol": False,  # 新增：真正的 MCP 协议开关
        "use_rag": False,
        "use_rerank": False,
        "tools_state": {},
        # === Plan-and-Solve 新增配置 ===
        "use_plan_solve": False,
        "planning_template": (
            "User request: {prompt}\n\n"
            "You are an expert Planner. Please create a comprehensive, step-by-step execution plan to fulfill the request using the available tools.\n"
            "Requirements:\n"
            "1. The plan must be a clear, numbered list.\n"
            "2. Do NOT execute any tools yet, just list the logical steps.\n"
            "3. If the request is trivial (e.g. 'hello'), reply with 'No plan needed'."
        )
    },
    "mcp_servers": {} # 新增：存储 MCP 服务器配置
}

class ConfigHandler:
    _config = None

    @classmethod
    def load(cls):
        if cls._config: return cls._config
        if not os.path.exists(SETTINGS_FILE):
            cls._config = copy.deepcopy(DEFAULT_CONFIG)
            cls.save()
        else:
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                cls._config = cls._merge(copy.deepcopy(DEFAULT_CONFIG), loaded)
                
                # 兼容性迁移：如果旧配置有 use_mcp，迁移到 use_custom_tools
                g = cls._config.get("global", {})
                if "use_mcp" in g:
                    if "use_custom_tools" not in g:
                        g["use_custom_tools"] = g["use_mcp"]
                    del g["use_mcp"]
                    cls.save()
                    
            except:
                cls._config = copy.deepcopy(DEFAULT_CONFIG)
        
        cls._decrypt_sensitive()
        return cls._config

    @classmethod
    def save(cls):
        to_save = cls._encrypt_sensitive(cls._config)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, indent=4, ensure_ascii=False)

    @classmethod
    def update(cls, key_path, value):
        keys = key_path.split('.')
        curr = cls._config
        for k in keys[:-1]:
            curr = curr.setdefault(k, {})
        curr[keys[-1]] = value
        cls.save()

    @classmethod
    def add_provider(cls, name, base_url, api_key, models):
        if "providers" not in cls._config:
            cls._config["providers"] = {}
        cls._config["providers"][name] = {
            "enabled": True,
            "base_url": base_url,
            "api_key": api_key,
            "models": [m.strip() for m in models.split(",") if m.strip()]
        }
        cls.save()

    @classmethod
    def remove_provider(cls, name):
        if "providers" in cls._config and name in cls._config["providers"]:
            del cls._config["providers"][name]
            cls.save()

    # === MCP Server 管理方法 ===
    @classmethod
    def add_mcp_server(cls, name, command, args, env=None):
        if "mcp_servers" not in cls._config:
            cls._config["mcp_servers"] = {}
        cls._config["mcp_servers"][name] = {
            "enabled": True,
            "command": command,
            "args": args, # list
            "env": env or {}
        }
        cls.save()

    @classmethod
    def remove_mcp_server(cls, name):
        if "mcp_servers" in cls._config and name in cls._config["mcp_servers"]:
            del cls._config["mcp_servers"][name]
            cls.save()
            
    @classmethod
    def toggle_mcp_server(cls, name, enabled):
        if "mcp_servers" in cls._config and name in cls._config["mcp_servers"]:
            cls._config["mcp_servers"][name]["enabled"] = enabled
            cls.save()

    @staticmethod
    def _merge(default, loaded):
        for k, v in loaded.items():
            if k in default and isinstance(default[k], dict) and isinstance(v, dict):
                ConfigHandler._merge(default[k], v)
            else:
                default[k] = v
        return default

    @classmethod
    def _decrypt_sensitive(cls):
        for p in cls._config["providers"].values():
            if "api_key" in p and isinstance(p["api_key"], str) and p["api_key"].startswith("encrypted:"):
                p["api_key"] = SecurityManager.decrypt(p["api_key"][10:])

    @classmethod
    def _encrypt_sensitive(cls, config):
        c = copy.deepcopy(config)
        for p in c["providers"].values():
            if "api_key" in p and p["api_key"] and isinstance(p["api_key"], str) and not p["api_key"].startswith("encrypted:"):
                p["api_key"] = f"encrypted:{SecurityManager.encrypt(p['api_key'])}"
        return c
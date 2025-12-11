import os
import ollama
from openai import OpenAI
from utils.logger import logger
import streamlit as st

class LLMFactory:
    @staticmethod
    def create_client(provider, config):
        base_url = config.get("base_url", "").strip()
        api_key = config.get("api_key", "")
        
        # === 关键修复：Ollama 也使用 OpenAI 客户端 ===
        if provider == "Ollama":
            # 确保 URL 指向 OpenAI 兼容端点 (/v1)
            if not base_url.endswith("/v1"):
                base_url = f"{base_url.rstrip('/')}/v1"
            # Ollama 的 key 可以随意填
            return OpenAI(base_url=base_url, api_key="ollama")
        else:
            return OpenAI(base_url=base_url, api_key=api_key or "dummy")

    @staticmethod
    @st.cache_data(ttl=600) 
    def get_all_models(config, _force_refresh=False):
        """获取对话模型列表 (带缓存)"""
        model_options = []
        providers = config.get("providers", {})

        # Ollama (仅用于列表获取，仍使用原生库因为方便)
        ollama_conf = providers.get("Ollama", {})
        if ollama_conf.get("enabled"):
            try:
                base_url = ollama_conf.get("base_url")
                # 原生库列出模型更稳
                client = ollama.Client(host=base_url)
                res = client.list() 
                if res:
                    for m in res.get('models', []):
                        model_options.append(f"Ollama/{m['model']}")
            except Exception as e:
                logger.error(f"Ollama 连接失败: {e}")

        # Other Providers
        for p_name, p_conf in providers.items():
            if p_name == "Ollama": continue
            if p_conf.get("enabled"):
                for m in p_conf.get("models", []):
                    model_options.append(f"{p_name}/{m}")
        
        if not model_options: model_options = ["Unknown/default"]
        return model_options

    @staticmethod
    @st.cache_data(ttl=600)
    def get_embedding_models(base_url):
        """动态获取 Ollama 嵌入模型"""
        embed_models = []
        try:
            client = ollama.Client(host=base_url)
            res = client.list()
            for m in res.get('models', []):
                name = m['model']
                if 'embed' in name or 'nomic' in name or 'bert' in name:
                    embed_models.append(name)
            if not embed_models and res:
                 embed_models = [m['model'] for m in res.get('models', [])]
        except: pass
        if not embed_models: embed_models = ["nomic-embed-text"]
        return embed_models

    @staticmethod
    def get_local_rerank_models(models_dir="models"):
        if not os.path.exists(models_dir): return []
        models = [d for d in os.listdir(models_dir) if os.path.isdir(os.path.join(models_dir, d))]
        if not models: return ["ms-marco-TinyBERT-L-2-v2 (Auto Download)"]
        return models

    @staticmethod
    def chat_stream(provider, config, model, messages, tools=None):
        """流式对话生成器，统一使用 OpenAI 协议"""
        try:
            client = LLMFactory.create_client(provider, config)
            # 统一使用 OpenAI SDK
            stream = client.chat.completions.create(
                model=model, messages=messages, tools=tools or None, stream=True, temperature=0.3
            )
            for chunk in stream:
                yield chunk

        except Exception as e:
            logger.error(f"LLM Stream Error: {e}")
            yield {"error": f"LLM API Error: {str(e)}"}
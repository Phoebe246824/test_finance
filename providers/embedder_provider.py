"""LLM提供商配置管理"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def get_embedder(model: str = "BAAI/bge-m3"):
    """根据提供商获取嵌入器实例"""
    provider = os.getenv("LLM_PROVIDER") or "openai"
    if provider in ("siliconflow", "openai"):
        embedder = {
            "provider": "openai",
            "config": {
                "api_key": os.getenv("EMBEDDER_API_KEY") or os.getenv("LLM_API_KEY") or "",
                "model_name": model,
                "api_base": os.getenv("EMBEDDER_API_BASE") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
            }
        }
        return embedder
    else:
        raise ValueError(f"不支持的LLM提供商: {provider}")

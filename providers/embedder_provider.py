"""LLM提供商配置管理"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def get_embedder(model=None):
    provider = os.getenv("LLM_PROVIDER", "siliconflow")
    if not model:
        model = "BAAI/bge-m3"
        # model = "Qwen/Qwen3-Embedding-8B"
    """根据提供商获取嵌入器实例"""
    if provider == "siliconflow":
        embedder = {
            "provider": "openai",
            "config": {
                "api_key": os.getenv("LLM_API_KEY"),
                "model_name": model,
                "api_base": "https://api.siliconflow.cn/v1",
            }
        }
        return embedder
    else:
        raise ValueError(f"不支持的LLM提供商: {provider}")

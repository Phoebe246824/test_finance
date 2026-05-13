"""LLM提供商配置管理"""
from crewai import LLM
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def get_siliconflow_llm(model=None, temperature=0.7):
    """获取硅基流动LLM实例"""
    # 确保模型名称不为空
    if not model:
        model = os.getenv("LLM_MODEL", "Pro/deepseek-ai/DeepSeek-V3.2")
    return LLM(
        model=model,
        # max_tokens=5120,
        max_completion_tokens=8192,
        top_p=0.85,
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        temperature=temperature,
        provider="openai"
    )

def get_llm(model=None, temperature=0.7):
    provider = os.getenv("LLM_PROVIDER", "siliconflow")
    """根据提供商获取LLM实例"""
    if provider == "siliconflow":
        return get_siliconflow_llm(model=model, temperature=temperature)
    else:
        raise ValueError(f"不支持的LLM提供商: {provider}")

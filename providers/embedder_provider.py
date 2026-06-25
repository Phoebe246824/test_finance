"""LLM提供商配置管理"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

RUNNABLE_MODEL_STATUS = "运行中"


def _settings_embedder_endpoint() -> str | None:
    try:
        from backend.app.services.settings_service import load_app_settings
        settings, _ = load_app_settings()
        services = settings.get("model_services") or []
        candidates = [
            s for s in services
            if s.get("type") == "向量模型" and s.get("status") == RUNNABLE_MODEL_STATUS
        ]
        if not candidates:
            return None
        default_svc = next((s for s in candidates if s.get("default")), candidates[0])
        return default_svc.get("endpoint") or None
    except Exception:
        return None


def get_embedder(model: str = "BAAI/bge-m3"):
    """根据提供商获取嵌入器实例"""
    provider = os.getenv("LLM_PROVIDER") or "openai"
    if provider in ("siliconflow", "openai"):
        api_base = (
            _settings_embedder_endpoint()
            or os.getenv("EMBEDDER_API_BASE")
            or os.getenv("LLM_BASE_URL")
            or "https://api.openai.com/v1"
        )
        embedder = {
            "provider": "openai",
            "config": {
                "api_key": os.getenv("EMBEDDER_API_KEY") or os.getenv("LLM_API_KEY") or "",
                "model_name": model,
                "api_base": api_base,
            }
        }
        return embedder
    else:
        raise ValueError(f"不支持的LLM提供商: {provider}")

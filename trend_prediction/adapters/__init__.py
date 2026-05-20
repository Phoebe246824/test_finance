"""领域适配器注册表"""

from trend_prediction.adapters.base import BaseAdapter
from trend_prediction.adapters.economy import EconomyAdapter
from trend_prediction.adapters.energy import EnergyAdapter
from trend_prediction.adapters.finance import FinanceAdapter
from trend_prediction.adapters.intl_politics import IntlPoliticsAdapter
from trend_prediction.adapters.public_health import PublicHealthAdapter
from trend_prediction.adapters.society import SocietyAdapter
from trend_prediction.adapters.tech import TechAdapter

_ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "intl_politics": IntlPoliticsAdapter,
    "tech": TechAdapter,
    "economy": EconomyAdapter,
    "society": SocietyAdapter,
    "public_health": PublicHealthAdapter,
    "energy": EnergyAdapter,
    "finance": FinanceAdapter,
}


def get_adapter(category: str) -> BaseAdapter:
    """
    获取指定类别的领域适配器。

    Args:
        category: 事件类别标识

    Returns:
        BaseAdapter: 对应的领域适配器实例

    Raises:
        ValueError: 如果类别没有注册的适配器
    """
    adapter_cls = _ADAPTER_REGISTRY.get(category)
    if adapter_cls is None:
        raise ValueError(f"No adapter registered for category: {category}")
    return adapter_cls()


def get_available_categories() -> list[str]:
    """获取所有已注册的类别标识"""
    return list(_ADAPTER_REGISTRY.keys())

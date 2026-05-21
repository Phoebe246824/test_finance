"""
Sentinel 工具函数
================
共享的工具函数，避免模块间循环导入。
"""

import re


def extract_subject_id_numbers(text: str) -> list[str]:
    """从事件文本中抽取主体 id_number，例如【P01# 小明】中的 P01。

    检索范围只使用稳定 id_number，不使用人名兜底，避免同名主体误召回。
    """
    id_numbers: list[str] = []
    seen: set[str] = set()

    for entity_id in re.findall(r"【\s*([A-Za-z]+\d+)\s*#\s*[^】]+?\s*】", text):
        normalized_id = entity_id.strip().upper()
        if normalized_id and normalized_id not in seen:
            id_numbers.append(normalized_id)
            seen.add(normalized_id)

    for entity_id in re.findall(r"\b([A-Za-z]+\d+)\b", text):
        normalized_id = entity_id.strip().upper()
        if normalized_id and normalized_id not in seen:
            id_numbers.append(normalized_id)
            seen.add(normalized_id)

    return id_numbers

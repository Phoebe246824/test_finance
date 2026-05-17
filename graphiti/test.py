import asyncio
import json
from datetime import datetime, timezone
import sys
sys.path.insert(0, "/Users/phoebe/project/zxy/test_Sentinel")
import graphiti_core.utils.maintenance.node_operations as nop
print("node_operations loaded from:", nop.__file__)

from graphiti_workflow import (
    add_event_to_graph,
    close_graph_client,
    hybrid_search,
    init_graph_client,
)
from graphiti_core.prompts import Message


async def answer_with_retrieval(
    graphiti,
    question: str,
    search_result: dict,
) -> str:
    evidence = []
    ranked_items = search_result.get("results", []) or []
    for item in ranked_items:
        item_type = item.get("type")
        if item_type not in {"edge", "episode"}:
            continue
        evidence.append({
            "type": item_type,
            "text": item.get("text"),
            "score": item.get("score"),
        })
    system_prompt = (
        "你是严谨的问答助手，只能基于检索到的内容作答。"
        "如果检索内容不足以回答，明确说明缺失信息。"
        "回答要简洁、直接、结构化。"
    )
    retrieved_payload = json.dumps({"evidence": evidence}, ensure_ascii=True, indent=2)
    user_prompt = (
        f"问题：\n{question}\n\n"
        "检索结果（JSON）：\n"
        f"{retrieved_payload}\n\n"
        "请基于检索结果回答问题：\n"
        "- 仅使用检索内容\n"
        "- 如有不确定，说明原因\n"
    )
    response = await graphiti.llm_client.generate_response(
        [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        prompt_name="graphiti.workflow.answer_with_retrieval",
    )
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        for key in ("answer", "content", "text", "summary"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(response).strip()


async def main():
    graphiti = await init_graph_client()
    try:
        text_items = [
            "2025 年 7 月 5 日，家长【P014# 张女士】发现为孩子报名的【C009# 启航少儿艺术中心】突然闭店，门口张贴 \“暂停营业\” 通知，联系【P015# 校区负责人李某】电话无人接听。",
            # "2025 年 7 月 6 日，【C009# 该机构】学员家长的【P016# 刘先生】联合 12 名家长维权，称 2 个月前刚为孩子预缴 15800 元的【T003# 全年艺术课程】，涉及未消费课程金额超 20 万元。",
            # "2025 年 7 月 8 日，【P014# 张女士】与【P016# 刘先生】等人前往【C010# 辖区市场监管局】投诉，工作人员表示已受理案件，正联系【C009# 启航少儿艺术中心】核实情况。",
            "2025 年 7 月 10 日，市民【P017# 张女士】在【L007# 社区超市】购买【T004# 真空包装熟食】，食用后出现腹泻症状，查看包装发现食品已过保质期 3 天。",
            # "2025 年 7 月 12 日，通勤族【P018# 郑先生】骑行【T005# 共享电动车】时，车辆突然刹车失灵，导致轻微摔伤，联系【C011# 共享出行平台】客服要求赔偿遭拒。",
            # "2025 年 7 月 13 日，市民【P020# 刘先生】在【L007# 社区超市】购买【T009# 水果】，切开发现里面是坏的，于是找负责人理赔，该负责人具不理会，并表示【P020# 刘先生】没有小票，不能证明是从该超市购买。",
            "2025 年 9 月 2 日，【A05# 小美】上午碰到【B12# 阿凯】的表姐【C08# 阿凯】，随后和【D17# 小美】、【E23# 阿凯】一起去公园散步。",
            "2025年8月12日，消费者【U032# 王先生】反映【O107# 优学教育】【O108# 优学教育】【O109# 优学教育】三家门店相继关停，联系区域经理【P041# 赵某某】始终无法取得有效沟通。",
            "2025年10月19日，【U032# 王先生】又和【B12# 阿凯】的妹妹【P22# 阿凯】去逛街"
            
        ]

        # 测试写入
        write_results = []
        for item in text_items:
            write_result = await add_event_to_graph(
                graphiti=graphiti,
                event_text=item,
                group_id="memory_event",
                source_description="测试输入",
                update_communities=False,
                summarize_before_extract=False,
            )
            write_results.append(write_result)

        print("add_event_to_graph result:")
        print(write_results)

        # 测试检索
        # question = "【P014# 张女士】遇到了哪些事件？"
        # search_result = await hybrid_search(
        #     graphiti=graphiti,
        #     query=question,
        #     group_id="memory_event",
        #     #global_top_k=3,
        #     num_results=6,
        # )
        # print("\nhybrid_search result:")
        # print(search_result)

        # answer = await answer_with_retrieval(
        #     graphiti=graphiti,
        #     question=question,
        #     search_result=search_result,
        # )
        # print("\nLLM answer:")
        # print(answer)

    finally:
        await close_graph_client(graphiti)


if __name__ == "__main__":
    asyncio.run(main())
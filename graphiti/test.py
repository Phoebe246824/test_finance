import asyncio
from datetime import datetime, timezone

from graphiti_workflow import (
    add_event_to_graph,
    close_graph_client,
    hybrid_search,
    init_graph_client,
)


async def main():
    graphiti = await init_graph_client()
    try:
        text = "2020年3月4日，武汉封城后，居家办公需求上升，DDR4内存价格开始上涨。"

        # 测试写入
        write_result = await add_event_to_graph(
            graphiti=graphiti,
            event_text=text,
            group_id="memory_event",
            update_communities=False,
            summarize_before_extract=True,  
        )

        print("add_event_to_graph result:")
        print(write_result)

        # 测试检索
        search_result = await hybrid_search(
            graphiti=graphiti,
            query="武汉封城后居家办公需求和DDR4价格有什么关系？",
            group_id="memory_event",
        )
        print("\nhybrid_search result:")
        print(search_result)

    finally:
        await close_graph_client(graphiti)


if __name__ == "__main__":
    asyncio.run(main())
"""按推荐顺序自动回放 blacklist/KV/filter 功能测试样例。"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reset_and_seed_blacklist import main as reset_blacklist_main

TEST_CASES = [
    {
        "title": "1. 无人员、无黑名单命中：应结束且不写 person KV",
        "text": "2026年5月20日 10:00 AM，【L17# 北京市海淀区】。【C11# 清河街道办事处】公告。【C11# 清河街道办事处】今日启动春季绿化养护周活动，组织社区志愿者对【L17# 北京市海淀区】辖区内12个小区的公共绿植进行修剪和补种。【C11# 清河街道办事处】表示，本次活动共有80余名居民报名参与，预计将持续一周。养护所需的花卉和苗木由【C12# 海淀区园林局】统一调配，居民无需承担费用。",
        "expect": [
            "不命中黑名单",
            "不进入构图",
            "不应写入 person:*",
        ],
    },
    {
        "title": "2. 含机构和地点，但只有一个人员：应只写人员 key",
        "text": "2026年5月21日 15:00 PM，【P04# 赵敏】前往【C23# 海淀区行政服务中心】办理业务，随后在【L24# 中关村创业大街】参加公开讲座。活动全程公开有序，未发现异常。",
        "expect": [
            "低风险、未命中黑名单",
            "只应写入 person:P04",
            "不应出现 person:C23 或 person:L24",
        ],
    },
    {
        "title": "3. 单人员、低风险：应写入 Redis KV，不构图",
        "text": "2026年5月21日 09:30 AM，【P01# 张三】在【L22# 北京市朝阳区】社区花园参加绿植认养活动，并与志愿者一起为新种植的月季浇水。活动由【C21# 朝阳社区服务中心】组织，共有30余名居民参与，现场秩序良好。",
        "expect": [
            "未命中黑名单",
            "写入 person:P01",
            "不进入构图",
        ],
    },
    {
        "title": "4. 多人员、低风险：应分别写入多个 person KV",
        "text": "2026年5月21日 14:10 PM，【P02# 李四】与【P03# 王五】在【L23# 上海市浦东新区】参加企业公益跑活动，活动由【C22# 浦东青年联合会】发起，现场共有200余人参与，未发生任何异常情况。",
        "expect": [
            "未命中黑名单",
            "写入 person:P02 和 person:P03",
            "可用于观察一条事件复制存储到多个 key",
        ],
    },
    {
        "title": "5. 敏感词命中：应 PASS 进入后续 pipeline",
        "text": "2026年5月22日 08:45 AM，市场传出某跨境贸易企业因涉嫌违反制裁规定，正在接受相关部门调查。多家合作方已暂停付款结算，内部员工对后续经营风险表示担忧。",
        "expect": [
            "命中敏感词 制裁",
            "blacklist PASS",
            "进入分类 / 构图 / 风险评估",
        ],
    },
    {
        "title": "6. 人员黑名单命中：应 PASS",
        "text": "2026年5月22日 11:20 AM，【P05# 孙强】被发现在【L25# 广州市天河区】多次出入不同写字楼，并与多名中介人员频繁接触。现场暂无公开冲突，但相关活动引起周边商户关注。",
        "expect": [
            "P05 命中人员黑名单",
            "blacklist PASS",
            "进入后续 pipeline",
        ],
    },
    {
        "title": "7A. 先存历史低风险事件 1",
        "text": "2026年5月18日 16:00 PM，【P06# 周凯】在【L26# 深圳市南山区】某仓储园区短暂停留后离开，期间与【P07# 陈某】有简短交流。现场未发生冲突，工作人员未报告异常。",
        "expect": [
            "若未命中黑名单则暂存",
            "写入 person:P06 和 person:P07",
        ],
    },
    {
        "title": "7B. 先存历史低风险事件 2",
        "text": "2026年5月19日 18:20 PM，【P06# 周凯】再次出现在【L27# 深圳市宝安区】物流园附近，并与两名陌生男子搬运多个封箱纸箱进入一辆无明显标识的厢式货车，随后离开现场。",
        "expect": [
            "继续写入 person:P06",
            "为后续 7C 回捞做准备",
        ],
    },
    {
        "title": "7C. 同一人员高风险触发回捞",
        "text": "2026年5月22日 21:30 PM，【P06# 周凯】在【L28# 深圳市福田区】地下停车场与他人发生激烈争执，现场发现疑似刀具与可燃液体容器，周边群众报警后迅速疏散。涉事人员行为具有明显危险性，警方已介入处置。",
        "expect": [
            "首次风险评估应偏中/高",
            "查询 person:P06 历史事件",
            "触发批量构图并在成功后删除对应 KV",
        ],
    },
    {
        "title": "8A. 多人员历史事件 1",
        "text": "2026年5月20日 09:10 AM，【P08# 刘波】与【P09# 马会】共同出现在【L29# 武汉市洪山区】某废弃厂房周边，二人停留约二十分钟后分别离开，未见明显异常。",
        "expect": [
            "写入 person:P08 和 person:P09",
        ],
    },
    {
        "title": "8B. 多人员历史事件 2",
        "text": "2026年5月21日 19:50 PM，【P08# 刘波】向【P09# 马会】发送多条加密聊天信息，随后两人分别前往【L30# 武汉市江夏区】同一停车场会合，停留时间较长。",
        "expect": [
            "继续写入 person:P08 和 person:P09",
        ],
    },
    {
        "title": "8C. 多人员高风险触发，观察重复回捞",
        "text": "2026年5月22日 23:15 PM，【P08# 刘波】与【P09# 马会】在【L31# 武汉市汉阳区】一处临时仓库内被发现大量危险化学品和疑似自制爆炸装置材料，现场情况紧急，警方和消防部门已到场处置。",
        "expect": [
            "高风险",
            "同时查询 person:P08 和 person:P09",
            "观察是否有重复历史事件被取回",
        ],
    },
    {
        "title": "9. 高危事件相似度命中",
        "text": "2026年5月23日 00:10 AM，【P10# 高林】在【L32# 成都市高新区】地下车库与他人争执，现场发现疑似管制刀具及装有刺激性液体的瓶罐，多名住户紧急报警撤离。",
        "expect": [
            "若 reranker 可用，应可能命中高危事件库",
            "blacklist PASS",
        ],
    },
    {
        "title": "10. 无人员但命中敏感词：仍应放行",
        "text": "2026年5月22日 13:40 PM，某工业园区仓库发生爆炸，现场火势迅速蔓延，多辆消防车赶赴处置，周边企业员工已紧急疏散，事故原因仍在调查中。",
        "expect": [
            "无 P 前缀人员编号",
            "命中敏感词 爆炸",
            "仍应 PASS，不走丢弃路径",
        ],
    },
]


def print_case(case: dict) -> None:
    separator = "=" * 100
    print(separator)
    print(case["title"])
    print("- 输入文本:")
    print(case["text"])
    print("- 预期检查点:")
    for item in case["expect"]:
        print(f"  - {item}")


def build_stdin_payload() -> str:
    lines: list[str] = []
    for case in TEST_CASES:
        lines.append(case["text"])
    lines.append("exit")
    return "\n".join(lines) + "\n"


async def main() -> None:
    print("[1/3] 先重置并预置 blacklist Redis 测试数据...\n")
    await reset_blacklist_main()

    print("\n[2/3] 输出本次自动回放的测试数据与检查点\n")
    for case in TEST_CASES:
        print_case(case)

    print("\n[3/3] 启动 main.py 并按顺序自动写入测试数据\n")
    payload = build_stdin_payload()
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    process = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "python",
        str(ROOT / "main.py"),
        cwd=str(ROOT),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    stdout, _ = await process.communicate(payload.encode("utf-8"))
    output = stdout.decode("utf-8", errors="replace") if stdout else ""
    print(output)

    if process.returncode != 0:
        raise RuntimeError(f"main.py exited with code {process.returncode}")

    print("=" * 100)
    print("自动回放完成，请结合日志与 Redis 检查结果")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())

"""
Agent 模式集成盲测脚本 —— ReAct 闭环全链路压测

验证范围:
  1. agent_compiled_graph 编译完整性
  2. HumanMessage → SystemPrompt 上下文注入
  3. Function Calling 决策 (tavily_search_tool / patch_resume_tool)
  4. tools_executor 自动解析 tool_calls JSON
  5. should_continue_loop 闭环路由
  6. astream 流式节点遍历

运行方式:
  source .venv/Scripts/activate && python tests/main_agent_test.py
"""

import os
import sys
import asyncio

# Windows GBK 终端强切 UTF-8，防止模型输出 emoji 导致 UnicodeEncodeError
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# 加载 .env 注入 API Keys
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(_PROJECT_ROOT, ".env"))

from langchain_core.messages import HumanMessage
from src.graphs.agent_graph import agent_compiled_graph


async def main():
    print("=" * 72)
    print("AI-Resume-Evolver 4.0 传统开放式 Agent 中央大脑启动盲测")
    print("=" * 72)

    # 1. 准备 mock 的原始简历底座（模拟周健恺的真实经历打底）
    mock_resume = (
        "# 周健恺 - 软件工程\n"
        "## 校园经历\n"
        "- 担任大学足球队队长，具备良好的团队协作能力。\n"
        "- 体育部项目经理，组织过多次校园联赛。"
    )

    # 2. 模拟用户输入一段需要大模型综合思考、联网、并局部精修的复杂刁钻指令
    user_query = (
        "帮我看看大厂招聘足球队队长这种经历时，更看重什么领导力特征？"
        "请先帮我联网查查大厂对这种管理经历的偏好，然后使用 patch_resume_tool 工具，"
        "帮我把'校园经历'这一段用标准的 STAR 原则和招聘黑话重新精修润色一下！"
    )

    # 3. 初始化全局状态机快照
    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "current_resume_markdown": mock_resume,
    }

    # 4. 配置持久化 thread_id（为后续双层存储并网打桩）
    config = {"configurable": {"thread_id": "test_zhou_001"}}

    print(f"\n[User Input]: {user_query}")
    print(f"\n[Resume Base]: {len(mock_resume)} 字符")
    print(f"[Thread ID]: {config['configurable']['thread_id']}")
    print(f"\n{'─' * 72}")
    print("大脑开始高频流式推理 (ReAct 环路点火)...")
    print(f"{'─' * 72}\n")

    node_count = 0

    # 5. 异步迭代流式打印状态机流转节点，肉眼审计大模型的
    #    Thought -> Action -> Observation 动线
    try:
        async for event in agent_compiled_graph.astream(initial_state, config):
            for node_name, node_output in event.items():
                node_count += 1
                print(f"\n{'=' * 60}")
                print(f"节点变更 #{node_count}: [{node_name}]")
                print(f"{'=' * 60}")

                if "messages" in node_output:
                    last_msg = node_output["messages"][-1]
                    msg_type = type(last_msg).__name__
                    print(f"消息类型: {msg_type}")

                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        print(f"\n[Function Calling 决策触发]")
                        for tc in last_msg.tool_calls:
                            print(f"  工具: {tc.get('name', '?')}")
                            args = tc.get("args", {})
                            for k, v in args.items():
                                val_str = str(v)
                                if len(val_str) > 120:
                                    val_str = val_str[:120] + "..."
                                print(f"    参数 [{k}]: {val_str}")
                    else:
                        content = last_msg.content
                        if isinstance(content, str):
                            display = content[:600]
                            if len(content) > 600:
                                display += f"\n... [截断, 全文 {len(content)} 字符]"
                            print(f"\n内容快照:\n{display}")
                        else:
                            print(f"\n内容: {content}")

        print(f"\n{'─' * 72}")
        print(f"ReAct 环路正常收敛 — 共经历 {node_count} 次节点变更")
        print(f"{'─' * 72}")

    except Exception as e:
        print(f"\n[盲测异常] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

import json
from uuid import UUID

from backend.app.services.agent_service import run_readonly_agent


# 手工运行只读 Agent，展示工具调用过程和最终回答。
# 在项目根目录执行：python -m scripts.try_readonly_agent
# repository_id 必须是已注册且已完成检索索引准备的仓库 ID。
def main() -> None:
    repository_id = UUID("81c498bc-19bb-4cee-91fa-144bb89247b2")

    # 最多执行 4 次工具调用；实际搜索、读取顺序由模型决定。
    result = run_readonly_agent(
        repository_id,
        question="保存新代码块之前，旧代码块是怎么处理的？请先搜索相关函数，再读取对应源码确认，并标明文件路径和行号。",
        max_tool_calls=4,
    )

    # None 表示仓库不存在，此时没有可展示的调用记录和回答。
    if result is None:
        print("仓库不存在，请检查 repository_id")
        return

    print("\n=== 工具调用记录 ===")
    if not result["tool_trace"]:
        print("本次没有工具调用记录。")

    for index, trace in enumerate(result["tool_trace"], start=1):
        print(f"\n第 {index} 次调用：{trace['tool_name']}")
        # arguments 是模型传入的原始 JSON 字符串；原样展示也能保留非法参数的证据。
        print(f"参数：{trace['arguments']}")
        # result 是字典，可能是搜索命中、源码内容或工具错误；格式化后便于查看。
        print("结果：")
        print(json.dumps(trace["result"], ensure_ascii=False, indent=2))

    print(result["answer"] or "模型未返回回答内容。")


if __name__ == "__main__":
    main()

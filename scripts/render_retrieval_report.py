import argparse
import json
from pathlib import Path


def render_report(report: dict) -> str:
    lines: list[str] = []

    # 1. 添加标题、空行和基本信息
    lines.append("# 代码检索评估报告")
    lines.append("")
    lines.append(f"- 数据集版本: {report.get('dataset_version', 'N/A')}")
    lines.append(f"- 仓库 Commit: {report.get('repository_commit', 'N/A')}")
    lines.append(f"- Embedding 模型: {report.get('embedding_model', 'N/A')}")
    lines.append(f"- 向量维度: {report.get('embedding_dimensions', 'N/A')}")
    lines.append(f"- 检索策略: {report.get('strategy', 'N/A')}")
    lines.append(f"- 评估时间: {report.get('evaluated_at', 'N/A')}")
    lines.append(f"- 用例总数: {report.get('case_count', 0)}")
    lines.append(f"- 异常数量: {report.get('error_count', 0)}")
    lines.append("")

    # 2. 添加 Recall 汇总表。
    lines.append("## Recall 汇总")
    lines.append("")
    lines.append("| 指标 | 得分 |")
    lines.append("| :--- | :--- |")
    lines.append(f"| Macro Recall@1 | {report.get('macro_recall_at_1'):.3f} |")
    lines.append(f"| Macro Recall@3 | {report.get('macro_recall_at_3'):.3f} |")
    lines.append(f"| Macro Recall@5 | {report.get('macro_recall_at_5'):.3f} |")
    lines.append("")

    # 3. 逐个展示用例。
    for case in report["cases"]:
        # 添加用例 ID、问题、status、三个 Recall 值。
        lines.append(f"### 用例: {case['id']}")
        lines.append(f"- 问题: {case['query']}")
        lines.append(f"- 状态: {case['status']}")
        lines.append(
            f"- Recall@1: {case.get('recall_at_1', 0.0):.3f} | "
            f"Recall@3: {case.get('recall_at_3', 0.0):.3f} | "
            f"Recall@5: {case.get('recall_at_5', 0.0):.3f}"
        )
        lines.append("- 预期目标排名:")

        # 4. 对每个预期目标，查找它在返回结果中的首次排名。
        for target in case["expected_targets"]:
            rank = None

            for position, hit in enumerate(case["hits"], start=1):
                chunk = hit["chunk"]

                # 同时比较 file_path 和 symbol_name。
                # 匹配时令 rank = position，然后 break。
                if chunk["file_path"] == target["file_path"] and chunk["symbol_name"] == target["symbol_name"]:
                    rank = position
                    break

            # 将目标路径、符号和排名添加到 lines。
            # rank 为 None 时写“未出现在返回结果中”。
            rank_text = f"第 {rank} 名" if rank is not None else "未出现在返回结果中"
            lines.append(f"  - {target['file_path']} :: {target['symbol_name']} -> {rank_text}")

        # 5. 展示第一名的路径、符号和距离。
        # 必须先检查 case["hits"] 非空。
        # 空列表时显示“无返回结果”。
        hits = case["hits"]
        if hits:
            top_chunk = hits[0]["chunk"]
            distance = hits[0].get("distance", "N/A")
            dist_str = f"{distance:.4f}" if isinstance(distance, (int, float)) else str(distance)
            lines.append(
                f"- Top 1 结果: {top_chunk['file_path']} :: {top_chunk['symbol_name']} (距离: {dist_str})"
            )
        else:
            lines.append("- Top 1 结果: 无返回结果")

        # 6. status 为 error 时，展示 case["error"]。
        if case["status"] == "error":
            lines.append(f"- 错误信息: {case.get('error', '未知错误')}")

        lines.append("")

    # 7. 添加解释：
    # 多目标用例的 Recall@1 小于 1 不一定是排序错误；
    # 指标仅反映当前数据集，不等于整体正确率。
    lines.append("## 说明")
    lines.append("")
    lines.append(
        "1. 多目标用例的 Recall@1 小于 1.0 不一定是排序错误（例如当用例包含 2 个预期目标时，Top 1 最多只能召回 1 个，此时 Recall@1 上限为 0.5）。"
    )
    lines.append(
        "2. 本报告指标仅反映当前测试数据集上的检索表现，不能完全等同于实际生产环境中的整体响应正确率。"
    )

    return "\n".join(lines) + "\n"

def main() -> None:
    parser = argparse.ArgumentParser()

    # 1. 增加必填 --report 参数，type=Path。
    parser.add_argument("--report", type=Path, required=True)

    args = parser.parse_args()

    # 2. 读取 args.report，并通过 json.loads 解析。
    args_json = json.loads(args.report.read_text(encoding="utf-8"))

    # 3. 调用 render_report，得到 Markdown 字符串。
    markdown_str = render_report(args_json)

    # 4. 生成同名 .md 路径。
    # 提示：args.report.with_suffix(".md")
    path = args.report.with_suffix(".md")

    # 5. 使用 write_text(..., encoding="utf-8") 保存并打印路径。
    path.write_text(markdown_str, encoding="utf-8")
    print(f"Report: {path}")

if __name__ == "__main__":
    main()
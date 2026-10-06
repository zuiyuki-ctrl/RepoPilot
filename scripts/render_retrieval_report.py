import argparse
import json
from pathlib import Path


def append_retrieval_diagnostics(
    lines: list[str],
    case: dict,
) -> None:
    lines.extend(["", "#### 混合检索诊断", ""])

    if case["status"] == "error":
        lines.append("执行失败，未获得完整诊断。")
        return

    diagnostics = case.get("retrieval_diagnostics")
    if diagnostics is None:
        lines.append("本报告未记录检索诊断。")
        return

    fields = (
        ("向量候选数", "vector_candidate_count"),
        ("关键词候选数", "keyword_candidate_count"),
        ("两路共同候选数", "overlap_count"),
        ("最终结果中有关键词贡献的条目数", "final_keyword_hit_count"),
    )
    for label, key in fields:
        lines.append(f"- {label}: {diagnostics[key]}")

    lines.append(
        "- 说明: 候选数是各路候选上限截取后的数量，不是全部匹配数量。"
    )

    keyword_candidate_count = diagnostics["keyword_candidate_count"]
    final_keyword_hit_count = diagnostics["final_keyword_hit_count"]
    if keyword_candidate_count == 0:
        lines.append("本次关键词检索未返回候选。")
    elif final_keyword_hit_count == 0:
        lines.append("关键词存在候选，但未进入最终返回结果。")
    else:
        lines.append(
            "关键词参与了部分最终结果的融合评分，"
            "不代表已经证明检索效果提升。"
        )


# 将已有检索评估报告整理成 Markdown，展示总体指标、逐题结果和未命中目标，不重新检索。
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
            top_hit = hits[0]
            top_chunk = top_hit["chunk"]

            if "rrf_score" in top_hit:
                rrf_score = top_hit["rrf_score"]
                score_text = (
                    f"{rrf_score:.4f}"
                    if isinstance(rrf_score, (int, float))
                    else str(rrf_score)
                )
                vector_rank = top_hit.get("vector_rank")
                keyword_rank = top_hit.get("keyword_rank")
                vector_rank_text = (
                    f"第 {vector_rank} 名"
                    if vector_rank is not None
                    else "未进入该路候选列表"
                )
                keyword_rank_text = (
                    f"第 {keyword_rank} 名"
                    if keyword_rank is not None
                    else "未进入该路候选列表"
                )
                lines.append(
                    f"- Top 1 结果: {top_chunk['file_path']} :: "
                    f"{top_chunk['symbol_name']} "
                    f"(RRF 分数: {score_text}; "
                    f"向量排名: {vector_rank_text}; "
                    f"关键词排名: {keyword_rank_text})"
                )
            else:
                distance = top_hit.get("distance", "N/A")
                dist_str = (
                    f"{distance:.4f}"
                    if isinstance(distance, (int, float))
                    else str(distance)
                )
                lines.append(
                    f"- Top 1 结果: {top_chunk['file_path']} :: "
                    f"{top_chunk['symbol_name']} (距离: {dist_str})"
                )
        else:
            lines.append("- Top 1 结果: 无返回结果")

        # 6. status 为 error 时，展示 case["error"]。
        if case["status"] == "error":
            lines.append(f"- 错误信息: {case.get('error', '未知错误')}")

        if report.get("strategy") == "hybrid_rrf_top5":
            append_retrieval_diagnostics(lines, case)

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


def render_comparison_report(report: dict) -> str:
    vector = report["reports"]["vector"]
    hybrid = report["reports"]["hybrid"]

    vector_cases = {
        case["id"]: case
        for case in vector["cases"]
    }
    hybrid_cases = {
        case["id"]: case
        for case in hybrid["cases"]
    }

    lines = [
        "# Vector / Hybrid 检索对比",
        "",
        f"- 数据集版本: {vector.get('dataset_version', 'N/A')}",
        f"- 仓库 ID: {vector.get('repository_id', 'N/A')}",
        f"- 仓库 Commit: {vector.get('repository_commit', 'N/A')}",
        f"- Embedding 模型: {vector.get('embedding_model', 'N/A')}",
        f"- 向量维度: {vector.get('embedding_dimensions', 'N/A')}",
        "- Vector 策略配置: "
        + json.dumps(vector.get("strategy_config", {}), ensure_ascii=False, sort_keys=True),
        "- Hybrid 策略配置: "
        + json.dumps(hybrid.get("strategy_config", {}), ensure_ascii=False, sort_keys=True),
        "",
        "## Recall 汇总",
        "",
        "| 指标 | Vector | Hybrid | 差值（Hybrid - Vector） |",
        "| :--- | ---: | ---: | ---: |",
    ]

    metrics = (
        ("Recall@1", "macro_recall_at_1", "recall_at_1"),
        ("Recall@3", "macro_recall_at_3", "recall_at_3"),
        ("Recall@5", "macro_recall_at_5", "recall_at_5"),
    )
    for label, report_key, delta_key in metrics:
        lines.append(
            f"| {label} | {vector[report_key]:.3f} | "
            f"{hybrid[report_key]:.3f} | "
            f"{report['macro_delta'][delta_key]:+.3f} |"
        )

    lines.extend([
        "",
        f"- Vector 异常数量: {vector.get('error_count', 0)}",
        f"- Hybrid 异常数量: {hybrid.get('error_count', 0)}",
        "",
        "## 逐例对比",
        "",
    ])

    def target_rank(case: dict, target: dict) -> str:
        if case["status"] == "error":
            return "执行失败"

        for position, hit in enumerate(case["hits"], start=1):
            chunk = hit["chunk"]
            if (
                chunk["file_path"] == target["file_path"]
                and chunk["symbol_name"] == target["symbol_name"]
            ):
                return f"第 {position} 名"

        return "未进入 Top 5"

    for comparison in report["case_comparisons"]:
        case_id = comparison["id"]
        vector_case = vector_cases[case_id]
        hybrid_case = hybrid_cases[case_id]

        lines.extend([
            f"### 用例: {case_id}",
            f"- 问题: {comparison['query']}",
            f"- Vector 状态: {comparison['vector_status']}",
            f"- Hybrid 状态: {comparison['hybrid_status']}",
            "",
            "| 指标 | Vector | Hybrid | 差值（Hybrid - Vector） |",
            "| :--- | ---: | ---: | ---: |",
        ])

        delta = comparison["delta"]
        for label, _, delta_key in metrics:
            delta_text = (
                f"{delta[delta_key]:+.3f}"
                if delta is not None
                else "执行异常，不比较排序差值"
            )
            lines.append(
                f"| {label} | {vector_case[delta_key]:.3f} | "
                f"{hybrid_case[delta_key]:.3f} | {delta_text} |"
            )

        if vector_case["status"] == "error":
            lines.append(f"- Vector 错误: {vector_case.get('error', '未知错误')}")
        if hybrid_case["status"] == "error":
            lines.append(f"- Hybrid 错误: {hybrid_case.get('error', '未知错误')}")

        lines.extend([
            "- 预期目标排名:",
            "",
            "| 目标 | Vector | Hybrid |",
            "| :--- | :--- | :--- |",
        ])
        for target in vector_case["expected_targets"]:
            target_name = f"{target['file_path']} :: {target['symbol_name']}"
            lines.append(
                f"| {target_name} | {target_rank(vector_case, target)} | "
                f"{target_rank(hybrid_case, target)} |"
            )

        append_retrieval_diagnostics(lines, hybrid_case)
        lines.append("")

    lines.extend([
        "## 说明",
        "",
        "1. 执行错误在宏平均中按零分计入。",
        "2. 本报告结果只代表当前数据集。",
        "3. Hybrid 检索不保证一定优于 Vector 检索。",
    ])

    return "\n".join(lines) + "\n"

# 读取命令行指定的 JSON 报告并生成同名 Markdown，供人工复盘检索效果。
def main() -> None:
    parser = argparse.ArgumentParser()

    # 1. 增加必填 --report 参数，type=Path。
    parser.add_argument("--report", type=Path, required=True)

    args = parser.parse_args()

    # 2. 读取 args.report，并通过 json.loads 解析。
    args_json = json.loads(args.report.read_text(encoding="utf-8"))

    # 3. 根据报告类型选择渲染函数，得到 Markdown 字符串。
    if args_json.get("report_type") == "retrieval_comparison":
        markdown_str = render_comparison_report(args_json)
    else:
        markdown_str = render_report(args_json)

    # 4. 生成同名 .md 路径。
    path = args.report.with_suffix(".md")

    # 5. 保存并打印路径。
    path.write_text(markdown_str, encoding="utf-8")
    print(f"Report: {path}")

if __name__ == "__main__":
    main()

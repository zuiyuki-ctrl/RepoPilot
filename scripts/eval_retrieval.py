from backend.app.schemas.code_chunk import CodeChunkSearchHit

import json
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone

from backend.app.core import config
from backend.app.services.repository_service import get_repository
from backend.app.services.retrieval_service import semantic_search

import argparse

Target = tuple[str, str]  # (file_path, symbol_name)

def recall_at_k(
    hits: list[CodeChunkSearchHit],
    expected_targets: set[Target],
    k: int,
) -> float:
    # 1. expected_targets 不允许为空，k 必须大于 0。
    # 否则抛出带说明的 ValueError。
    if not expected_targets or k <= 0:
        raise ValueError("expected_targets must not be empty and k must be positive")

    # 2. 先截取 hits[:k]。
    # 注意：必须先取前 K 条，再去重。
    hits = hits[:k]

    # 3. 创建 retrieved_targets 集合。
    # 遍历截取的结果，将以下元组加入集合：
    # (hit.chunk.file_path, hit.chunk.symbol_name)
    retrieved_targets = set()
    for hit in hits:
        retrieved_targets.add((hit.chunk.file_path, hit.chunk.symbol_name))

    # 4. 求 retrieved_targets 与 expected_targets 的交集。
    # 提示：集合 A & 集合 B。
    intersection = retrieved_targets & expected_targets

    # 5. 返回交集大小 / expected_targets 大小。
    return len(intersection) / len(expected_targets)

def load_dataset(path: Path) -> dict:
    # 1. path.read_text(encoding="utf-8") 读取文本。
    # 使用 json.loads(...) 解析成字典。
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(dataset, dict):
        raise ValueError("dataset must be a dict")

    # 2. 检查 dataset_version、repository_commit 非空。
    # 用 UUID(...) 验证 repository_id 格式。
    # cases 必须是非空列表。
    dataset_version = dataset.get("dataset_version")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("dataset_version must be a nonblank string")

    repository_commit = dataset.get("repository_commit")
    if not isinstance(repository_commit, str) or not repository_commit.strip():
        raise ValueError("repository_commit must be a nonblank string")

    repository_id = dataset.get("repository_id")
    if not isinstance(repository_id, str) or not repository_id.strip():
        raise ValueError("repository_id must be a nonblank string")

    UUID(repository_id)

    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")

    # 3. 遍历全部 cases，在任何检索开始前完成校验：
    # - id 和 query 都是非空字符串；
    # - id 不重复，可用 seen_ids 集合；
    # - expected_targets 是非空列表；
    # - 每个目标的 file_path、symbol_name 是非空字符串。
    # 不符合要求，抛带说明的 ValueError。
    seen_ids: set[str] = set()
    for case in cases:
        # 先检查 case 是 dict。
        # 再检查 id、query 是非空白字符串。
        if not isinstance(case, dict):
            raise ValueError("case must be a dict")

        _id = case.get("id")

        if not isinstance(_id, str) or not _id.strip():
            raise ValueError("id must be a nonblank string")

        query = case.get("query")

        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonblank string")

        # 5. 检查 case["id"] 是否已经在 seen_ids 中。
        # 重复则报错，否则加入集合。
        if case["id"] in seen_ids:
            raise ValueError("duplicate id")
        seen_ids.add(case["id"])

        targets = case.get("expected_targets")
        if not isinstance(targets, list) or not targets:
            raise ValueError("expected_targets must be a nonempty list")

        for target in targets:
            # 6. 检查 target 是 dict。
            # 再检查 file_path、symbol_name 是非空白字符串。
            if not isinstance(target, dict):
                raise ValueError("target must be a dict")

            file_path = target.get("file_path")
            if not isinstance(file_path, str) or not file_path.strip():
                raise ValueError("file_path must be a nonblank string")

            symbol_name = target.get("symbol_name")
            if not isinstance(symbol_name, str) or not symbol_name.strip():
                raise ValueError("symbol_name must be a nonblank string")

    # 4. 返回 dataset。
    return dataset

def run_evaluation(dataset: dict) -> dict:
    repository_id = UUID(dataset["repository_id"])

    # 1. 调用 get_repository(repository_id)。
    # 仓库不存在，或 commit_hash 与 repository_commit 不一致，
    # 抛 ValueError，阻止运行。
    repository = get_repository(repository_id)
    if repository is None:
        raise ValueError("Evaluation repository does not exist")

    if dataset["repository_commit"] != repository.commit_hash:
        raise ValueError("Repository commit does not match evaluation dataset")

    case_results = []

    for case in dataset["cases"]:
        # 2. 将 expected_targets 转成 set[Target]。
        # 每项是 (file_path, symbol_name)。
        expected_targets = set()
        for target in case["expected_targets"]:
            expected_targets.add((target["file_path"], target["symbol_name"]))

        try:
            # 3. 调用一次 semantic_search，top_k=5。
            # 只传 case["query"]，不要传预期答案。
            # 返回 None 时抛 RuntimeError，表示仓库已不存在。
            search_result = semantic_search(repository_id, query=case["query"], top_k=5)
            if search_result is None:
                raise RuntimeError("repository is not exist")

            # 4. 对同一份 hits 分别计算 Recall@1、@3、@5。
            # 组装本例结果：
            # id、query、expected_targets、status="ok"、
            #    recall_at_1、recall_at_3、recall_at_5、
            # hits、error=None。
            #
            # hits 可使用：
            # [hit.model_dump(mode="json") for hit in hits]
            recall_1 = recall_at_k(search_result, expected_targets, 1)
            recall_3 = recall_at_k(search_result, expected_targets, 3)
            recall_5 = recall_at_k(search_result, expected_targets, 5)

            case_result = {
                "id": case["id"],
                "query": case["query"],
                "expected_targets": case["expected_targets"],
                "status": "ok",
                "recall_at_1": recall_1,
                "recall_at_3": recall_3,
                "recall_at_5": recall_5,
                "hits": [],
                "error": None,
            }

            for hit in search_result:
                case_result["hits"].append(hit.model_dump(mode="json"))

        except Exception as exc:
            # 5. 本例执行失败仍加入 case_results：
            # status="error"，三个 recall 都为 0，hits=[]。
            # error 暂时保存 type(exc).__name__。
            # 不把请求头或密钥写进报告。
            case_result = {
                "id": case["id"],
                "query": case["query"],
                "expected_targets": case["expected_targets"],
                "status": "error",
                "recall_at_1": 0,
                "recall_at_3": 0,
                "recall_at_5": 0,
                "hits": [],
                "error": type(exc).__name__,
            }
        case_results.append(case_result)


    # 6. 分别计算三个指标的算术平均值。
    # 例如：
    # sum(item["recall_at_1"] for item in case_results) / len(case_results)
    # 分母包含失败用例
    macro_recall_1 = sum(item["recall_at_1"] for item in case_results) / len(case_results)
    macro_recall_3 = sum(item["recall_at_3"] for item in case_results) / len(case_results)
    macro_recall_5 = sum(item["recall_at_5"] for item in case_results) / len(case_results)
    error_num = sum(item["status"] == "error" for item in case_results)


    # 7. 返回报告字典，包含：
    # dataset_version、repository_id（字符串）、repository_commit、
    # embedding_model、embedding_dimensions、
    # strategy="vector_cosine_top5"、
    # evaluated_at（UTC ISO 字符串）、
    # case_count、error_count、
    # macro_recall_at_1、macro_recall_at_3、macro_recall_at_5、
    # cases=case_results。
    return {
        "dataset_version": dataset["dataset_version"],
        "repository_id": str(repository_id),
        "repository_commit": dataset["repository_commit"],
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dimensions": config.EMBEDDING_DIMENSIONS,
        "strategy": "vector_cosine_top5",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(case_results),
        "error_count": error_num,
        "macro_recall_at_1": macro_recall_1,
        "macro_recall_at_3": macro_recall_3,
        "macro_recall_at_5": macro_recall_5,
        "cases": case_results,
    }

def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    # 1. 创建命令行参数解析器。
    # 提示：parser = argparse.ArgumentParser(...)
    parser = argparse.ArgumentParser()

    # 2. 添加 --dataset 参数。
    # type=Path
    # 默认值为 project_root / "evals" / "retrieval_v1.json"
    parser.add_argument("--dataset", type=Path, default=project_root / "evals" / "retrieval_v1.json")

    # 3. 解析参数。
    # 提示：args = parser.parse_args()
    args = parser.parse_args()

    # 4. 使用 args.dataset 调用 load_dataset
    load_dataset(args.dataset)

    project_root = Path(__file__).resolve().parents[1]
    dataset_path = project_root / "evals" / "retrieval_v1.json"

    # 5. load_dataset，再调用 run_evaluation。
    dataset = load_dataset(dataset_path)
    result = run_evaluation(dataset)

    # 6. 在 evals/reports 下写报告。
    # mkdir(parents=True, exist_ok=True) 创建目录。
    # 文件名加入 UTC 时间，避免覆盖之前的报告。
    target_dir = project_root / "evals" / "reports"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = target_dir / f"retrieval_{timestamp}.json"

    # 7. json.dumps(report, ensure_ascii=False, indent=2)
    # 配合 write_text(..., encoding="utf-8") 保存。
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 8. 打印报告路径、三个汇总指标和错误数量。
    print(f"Recall@1: {result['macro_recall_at_1']:.3f}\n"
          f"Recall@3: {result['macro_recall_at_3']:.3f}\n"
          f"Recall@5: {result['macro_recall_at_5']:.3f}\n"
          f"Error: {result['error_count']}")

if __name__ == "__main__":
    main()
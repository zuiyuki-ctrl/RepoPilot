import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

from backend.app.schemas.experiment import ExperimentEditCandidate
from backend.app.services import experiment_execution_service as service
from scripts.plan_experiment import load_prepared_experiment
from scripts.export_task_report import export_report


def save_new_json(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")


def _validate_action_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    requirements = {
        "generate": (
            ("file_path", "--file-path"),
            ("allow_model", "--allow-model"),
        ),
        "apply": (
            ("candidate", "--candidate"),
            ("confirm_apply", "--confirm-apply"),
        ),
        "complete": (("test_run_id", "--test-run-id"),),
    }
    allowed = {
        "generate": {"file_path", "allow_model"},
        "apply": {"candidate", "confirm_apply"},
        "test": set(),
        "complete": {"test_run_id"},
        "report": set(),
    }
    option_names = {
        "file_path": "--file-path",
        "candidate": "--candidate",
        "test_run_id": "--test-run-id",
        "allow_model": "--allow-model",
        "confirm_apply": "--confirm-apply",
    }

    for attribute, option in requirements.get(args.action, ()):
        if not getattr(args, attribute):
            parser.error(f"{args.action} 操作要求提供 {option}")

    supplied = {
        "file_path": args.file_path is not None,
        "candidate": args.candidate is not None,
        "test_run_id": args.test_run_id is not None,
        "allow_model": args.allow_model,
        "confirm_apply": args.confirm_apply,
    }
    unsupported = [
        option_names[name]
        for name, was_supplied in supplied.items()
        if was_supplied and name not in allowed[args.action]
    ]
    if unsupported:
        parser.error(
            f"{args.action} 操作不接受参数：{', '.join(unsupported)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="分阶段执行实验，不自动批准或重试"
    )
    parser.add_argument(
        "action",
        choices=("generate", "apply", "test", "complete", "report"),
    )
    parser.add_argument("--preparation", required=True, type=Path)
    parser.add_argument("--file-path")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--test-run-id", type=UUID)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--confirm-apply", action="store_true")
    args = parser.parse_args()

    _validate_action_arguments(parser, args)

    preparation = None
    operation_id = None
    operation_dir = None
    stage = "读取实验准备记录"

    try:
        preparation = load_prepared_experiment(args.preparation)

        operation_id = uuid4()
        operation_dir = (
            args.preparation.resolve().parent
            / "operations"
            / str(operation_id)
        )
        stage = "创建操作目录"
        operation_dir.mkdir(parents=True, exist_ok=False)

        request_record = {
            "schema_version": 1,
            "operation_id": str(operation_id),
            "experiment_id": str(preparation.experiment_id),
            "task_id": str(preparation.task_id),
            "action": args.action,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.action == "generate":
            request_record["file_path"] = args.file_path
        elif args.action == "apply":
            request_record["candidate_path"] = str(args.candidate.resolve())
        elif args.action == "complete":
            request_record["test_run_id"] = str(args.test_run_id)

        stage = "保存请求记录"
        save_new_json(operation_dir / "request.json", request_record)

        common_record = {
            "experiment_id": str(preparation.experiment_id),
            "task_id": str(preparation.task_id),
            "operation_id": str(operation_id),
        }

        if args.action == "generate":
            stage = "生成候选修改"
            candidate = service.generate_experiment_file_edit(
                preparation,
                file_path=args.file_path,
            )
            artifact = ExperimentEditCandidate(
                experiment_id=preparation.experiment_id,
                created_at=datetime.now(timezone.utc),
                candidate=candidate,
            )

            candidate_path = operation_dir / "candidate.json"
            stage = "保存候选修改"
            save_new_json(
                candidate_path,
                artifact.model_dump(mode="json"),
            )

            print(f"候选文件：{candidate_path.resolve()}")
            print(f"修改目标：{candidate.proposal.file_path}")
            print(f"说明：{candidate.proposal.summary}")
            print("请打开候选文件检查完整内容；本操作尚未应用修改。")

        elif args.action == "apply":
            stage = "读取候选修改"
            artifact = ExperimentEditCandidate.model_validate_json(
                args.candidate.read_text(encoding="utf-8")
            )
            stage = "应用候选修改"
            result = service.apply_experiment_file_edit(
                preparation,
                artifact=artifact,
            )

            result_path = operation_dir / "apply-result.json"
            stage = "保存应用结果"
            save_new_json(
                result_path,
                {
                    **common_record,
                    "candidate_path": str(args.candidate.resolve()),
                    "result": asdict(result),
                },
            )

            print(f"应用结果：{result_path.resolve()}")
            print("实际执行事实请以数据库事件和工作区内容为准。")

        elif args.action == "test":
            stage = "运行实验测试"
            run = service.run_experiment_tests(preparation)

            result_path = operation_dir / "test-result.json"
            stage = "保存测试结果"
            save_new_json(
                result_path,
                {
                    **common_record,
                    "test_run": run.model_dump(mode="json"),
                },
            )

            print(f"测试运行 ID：{run.id}")
            print(f"测试结果：{result_path.resolve()}")
            print("完成任务时必须通过 --test-run-id 显式使用该 ID。")
            passed = (
                run.status == "finished"
                and run.exit_code == 0
                and run.timed_out is False
            )
            if not passed:
                print("测试正常结束，但未通过。", file=sys.stderr)
                raise SystemExit(1)

        elif args.action == "complete":
            stage = "完成实验任务"
            completed = service.complete_experiment(
                preparation,
                test_run_id=args.test_run_id,
            )

            result_path = operation_dir / "complete-result.json"
            stage = "保存完成结果"
            save_new_json(
                result_path,
                {
                    **common_record,
                    "test_run_id": str(args.test_run_id),
                    "result": completed.model_dump(mode="json"),
                },
            )

            print(f"完成结果：{result_path.resolve()}")
            print("下一步可执行 report，读取历史事实并导出报告。")

        else:
            stage = "读取实验报告"
            report = service.read_experiment_report(preparation)
            stage = "导出实验报告"
            json_path, markdown_path = export_report(
                report,
                output_dir=operation_dir,
            )

            result_path = operation_dir / "report-result.json"
            stage = "保存报告结果"
            save_new_json(
                result_path,
                {
                    **common_record,
                    "test_run_id": (
                        str(report.test_run.id)
                        if report.test_run is not None
                        else None
                    ),
                    "json_path": str(json_path.resolve()),
                    "markdown_path": str(markdown_path.resolve()),
                },
            )

            print(f"JSON 报告：{json_path.resolve()}")
            print(f"Markdown 报告：{markdown_path.resolve()}")
            print(f"报告结果记录：{result_path.resolve()}")

    except Exception as exc:
        if (
            preparation is not None
            and operation_id is not None
            and operation_dir is not None
        ):
            error_record = {
                "operation_id": str(operation_id),
                "action": args.action,
                "experiment_id": str(preparation.experiment_id),
                "task_id": str(preparation.task_id),
                "error_type": type(exc).__name__,
                "stage": stage,
            }
            try:
                save_new_json(operation_dir / "error.json", error_record)
            except Exception:
                pass

        print(
            f"实验操作失败：{type(exc).__name__}（阶段：{stage}）。",
            file=sys.stderr,
        )
        print(
            "请查询任务事件与测试记录确认实际状态；不会自动重新执行。",
            file=sys.stderr,
        )
        if args.action == "report":
            print(
                "报告导出失败时只重试 report，不要重新运行测试或完成操作。",
                file=sys.stderr,
            )
        elif args.action == "generate" and stage == "保存候选修改":
            print(
                "候选可能已经生成；不要自动再次调用模型，也不要回退任务状态。",
                file=sys.stderr,
            )
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

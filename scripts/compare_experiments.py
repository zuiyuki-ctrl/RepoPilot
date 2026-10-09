"""按显式清单离线汇总实验，不调用 API、数据库或模型。"""
import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.experiment_comparison_service import (
    build_comparison, render_comparison, summarize_run,
)


class RunArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["primary", "additional"] = "primary"
    preparation: str
    report: str | None = None
    evidence: str | None = None


class ComparisonManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    runs: list[RunArtifacts] = Field(min_length=1)


def load_comparison(manifest_path: Path) -> dict:
    manifest = ComparisonManifest.model_validate_json(manifest_path.read_bytes())
    rows = []
    for entry in manifest.runs:
        data, artifacts = {}, {}
        for name in ("preparation", "report", "evidence"):
            reference = getattr(entry, name)
            if reference is None:
                data[name] = artifacts[name] = None
                continue
            path = (manifest_path.resolve().parent / reference).resolve()
            content = path.read_bytes()
            data[name] = json.loads(content)
            artifacts[name] = {"path": str(path), "uri": path.as_uri(),
                               "sha256": hashlib.sha256(content).hexdigest()}
        row = summarize_run(**data)
        row.update(role=entry.role, artifacts=artifacts)
        rows.append(row)
    result = build_comparison(rows)
    result["manifest"] = str(manifest_path.resolve())
    return result


def export_comparison(report: dict, output_dir: Path) -> tuple[Path, Path]:
    directory = output_dir / f"comparison_{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    json_path, markdown_path = directory / "comparison.json", directory / "comparison.md"
    with json_path.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    with markdown_path.open("x", encoding="utf-8") as output:
        output.write(render_comparison(report))
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/comparisons"))
    args = parser.parse_args()
    try:
        report = load_comparison(args.manifest)
        paths = export_comparison(report, args.output_dir)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(1, f"对照汇总失败：{type(exc).__name__}: {exc}\n原实验文件未修改，无需重新运行实验。\n")
    print(f"配对用例：{len(report['pairs'])}；额外记录：{len(report['additional_attempts'])}")
    print(f"JSON：{paths[0].resolve()}")
    print(f"Markdown：{paths[1].resolve()}")


if __name__ == "__main__":
    main()

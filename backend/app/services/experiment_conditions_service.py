"""准备时采集索引及镜像身份。缺失项明确记录，不自动拉取镜像。"""
import json
import subprocess

from sqlalchemy import select

from ..core.runtime_conditions import capture_runtime_conditions, fingerprint
from ..core.test_profiles import get_test_profile
from ..core.exceptions import TaskStateConflictError
from ..db.session import SessionLocal
from ..db.models import CodeChunk


def capture_index_fingerprint(repository_id) -> str:
    with SessionLocal() as session:
        rows = session.execute(select(CodeChunk.file_path, CodeChunk.symbol_name,
            CodeChunk.start_line, CodeChunk.end_line, CodeChunk.content,
            CodeChunk.embedding_model, CodeChunk.embedding).where(CodeChunk.repository_id == repository_id)
            .order_by(CodeChunk.file_path, CodeChunk.start_line, CodeChunk.end_line, CodeChunk.id)).all()
        # 不依赖不同克隆的随机 chunk UUID；同时标识实际内容和向量。
        items = [list(row[:6]) + [None if row[6] is None else [float(v) for v in row[6]]] for row in rows]
    return fingerprint(items)


def require_index_fingerprint(repository_id, expected):
    if expected is not None and capture_index_fingerprint(repository_id) != expected:
        raise TaskStateConflictError("Repository index changed since experiment preparation")


def capture_experiment_conditions(repository_id, *, test_profile: str) -> dict:
    runtime = capture_runtime_conditions()
    image = get_test_profile(test_profile).image
    image_id, digests, image_error = None, [], None
    try:
        result = subprocess.run(["docker", "image", "inspect", image], capture_output=True,
                                text=True, timeout=10, check=True)
        details = json.loads(result.stdout)[0]
        image_id = details["Id"]
        digests = details.get("RepoDigests") or []
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, TypeError) as exc:
        image_error = type(exc).__name__
    return {"version": 1, "runtime": runtime, "runtime_fingerprint": fingerprint(runtime),
            "index_fingerprint": capture_index_fingerprint(repository_id),
            "test_image": {"tag": image, "id": image_id, "repo_digests": digests, "error_type": image_error}}

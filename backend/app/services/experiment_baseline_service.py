"""准备阶段的未修改代码测试证据；不占用任务执行轮次。"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .sandbox_snapshot_service import prepare_python_test_snapshot
from .docker_test_service import run_pytest_in_docker


def capture_baseline_test(preparation) -> dict:
    image = preparation.run_config.test_image_id
    if image is None:
        raise ValueError("Controlled baseline tests require a recorded image ID")
    with TemporaryDirectory(prefix="repopilot-baseline-") as directory:
        snapshot = prepare_python_test_snapshot(Path(preparation.workspace_path), Path(directory))
        result = run_pytest_in_docker(snapshot, image=image,
            timeout_seconds=preparation.definition.test_timeout_seconds)
        return {**asdict(result), "snapshot_hash": snapshot.snapshot_hash,
                "image": image, "timeout_seconds": preparation.definition.test_timeout_seconds,
                "repository_commit": preparation.case.repository_commit,
                "protected_test_file_hashes": dict(preparation.protected_test_file_hashes),
                "recorded_at": datetime.now(timezone.utc).isoformat()}

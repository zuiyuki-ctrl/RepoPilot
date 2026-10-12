"""非秘密运行条件；实现指纹用于发现漂移，不承诺供应商内部版本可复现。"""
import hashlib
import json
from pathlib import Path

from . import config
from .exceptions import TaskStateConflictError


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def capture_runtime_conditions() -> dict:
    from ..rag.generation import chat_parameters
    from ..rag.tool_chat import TOOL_DEFINITIONS
    from ..agent import policy
    root = Path(__file__).resolve().parents[1]
    files = ["rag/generation.py", "rag/embedding.py", "rag/prompts.py", "rag/tool_chat.py",
             "rag/fusion.py", "agent/policy.py", "agent/plan_generation.py", "agent/edit_generation.py",
             "agent/reflection_generation.py", "schemas/tools.py", "services/retrieval_service.py",
             "services/docker_test_service.py", "core/test_profiles.py", "agent/nodes.py", "services/tool_service.py"]
    return {
        "version": 1, "chat_model": config.CHAT_MODEL,
        "chat_endpoint_sha256": fingerprint(config.CHAT_BASE_URL),
        "embedding_model": config.EMBEDDING_MODEL, "embedding_dimensions": config.EMBEDDING_DIMENSIONS,
        "embedding_endpoint_sha256": fingerprint(config.EMBEDDING_ENDPOINT),
        "chat_parameters": chat_parameters(), "qa_parameters": chat_parameters(max_tokens=1500),
        "tool_definitions_sha256": fingerprint(TOOL_DEFINITIONS),
        "prompt_templates_sha256": {name: fingerprint(value) for name, value in vars(policy).items()
            if isinstance(value, str) and (name.endswith("PROMPT") or name.endswith("INSTRUCTION"))},
        "context_budget_chars": policy.MAX_TOOL_RESULT_CHARS,
        "implementation_sha256": {file: hashlib.sha256((root / file).read_text(encoding="utf-8").encode()).hexdigest() for file in files},
        "provider_internal_version": None,
    }


def require_runtime_conditions(run_config) -> None:
    expected = run_config.runtime_fingerprint
    if expected is not None and expected != fingerprint(capture_runtime_conditions()):
        raise TaskStateConflictError("Runtime conditions changed since experiment preparation")

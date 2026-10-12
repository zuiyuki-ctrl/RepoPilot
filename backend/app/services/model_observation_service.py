"""为图外的编辑/反思模型调用记录事件，HTTP 等待期间不持有事务。"""
from contextlib import contextmanager
import logging
from time import perf_counter
from uuid import UUID

from ..db.session import SessionLocal
from ..db.repositories import task_repo, task_event_repo
from ..core.exceptions import TaskExecutionError
from ..rag.model_observation import ModelObservation
from ..schemas.run_config import AgentRunConfig
from ..core.runtime_conditions import require_runtime_conditions

logger = logging.getLogger(__name__)


def _persist(task_id: UUID, phase: str, event_type: str, payload: dict):
    with SessionLocal.begin() as session:
        task = task_repo.get_task_for_update(session, task_id)
        if task is None:
            raise TaskExecutionError("Model observation task is missing")
        if event_type == "MODEL_CALL_STARTED":
            require_runtime_conditions(AgentRunConfig.model_validate(task.run_config or {}))
        task_event_repo.append_task_event(
            session, task_id=task_id, event_type=event_type, node_name=phase,
            message="Model operation observation", payload=payload,
        )


@contextmanager
def observe_task_model(task_id: UUID, *, phase: str):
    observation = ModelObservation()
    base = {"call_id": observation.call_id, "step_id": phase, "attempt": 1}
    # 开始事件失败就不调用模型。结束持久化失败向外暴露，不能自动重发模型请求。
    _persist(task_id, phase, "MODEL_CALL_STARTED", base)
    started = perf_counter()
    try:
        yield observation
    except Exception as exc:
        try:
            _persist(task_id, phase, "MODEL_CALL_FAILED", {
                **base, "duration_ms": int((perf_counter() - started) * 1000),
                "error_type": type(exc).__name__, "model_observation": observation.to_payload(exc),
            })
        except Exception:
            # 不记录原始异常文本，以免 HTTP/供应商错误携带请求信息。
            logger.error("Model failure observation was not persisted; call_id=%s", observation.call_id)
        raise
    else:
        _persist(task_id, phase, "MODEL_CALL_COMPLETED", {
            **base, "duration_ms": int((perf_counter() - started) * 1000),
            "response_type": phase, "tool_call_count": 0,
            "model_observation": observation.to_payload(),
        })

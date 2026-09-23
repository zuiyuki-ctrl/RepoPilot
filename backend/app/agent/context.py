from dataclasses import dataclass
from typing import Any, Protocol


class AgentEventSink(Protocol):
    """Agent 节点通过该接口发送事件，不关心事件如何持久化。"""

    def __call__(
        self,
        *,
        event_type: str,
        node_name: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        # Protocol 只声明接口，不编写实现。
        ...


@dataclass(frozen=True)
class AgentRunContext:
    """一次 Graph 运行期间不会变化的外部依赖。"""

    event_sink: AgentEventSink | None = None

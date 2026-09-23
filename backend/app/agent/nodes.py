# 三个节点及路由函数
import json
from time import perf_counter
from typing import Literal, Any
from uuid import uuid4

from langgraph.runtime import Runtime

from ..core import config
from .context import AgentRunContext
from .evidence import finish_answer, prepare_evidence
from ..agent.state import ReadonlyAgentState
from ..core.exceptions import RepositoryScanError, FileSkippedError
from ..rag.generation import request_tool_turn
from .policy import BUDGET_ERROR, MAX_TOOL_ERROR_CHARS
from ..services.tool_service import execute_readonly_tool

import logging

logger = logging.getLogger(__name__)

"""如果当前 Graph 运行提供了 Sink，就发送事件。"""
def emit_agent_event(
    runtime: Runtime[AgentRunContext],
    *,
    event_type: str,
    node_name: str,
    message: str,
    payload: dict[str, Any],
) -> None:

    # 从 runtime.context 取得 event_sink。
    event_sink = runtime.context.event_sink

    # 没有 sink 表示这次运行不属于持久化 Task，
    # 直接返回，不应报错。
    if event_sink is None:
        return None

    # 调用 event_sink，并完整传递四个命名参数。
    event_sink(
        event_type=event_type,
        node_name=node_name,
        message=message,
        payload=payload
    )

def model_node(
    state: ReadonlyAgentState,
    runtime: Runtime[AgentRunContext],
) -> dict:

    # 1.计算工具预算
    budget_error_size = len(
        json.dumps(BUDGET_ERROR, ensure_ascii=False)
    )

    allow_tools = (
        state["used_calls"] < state["max_tool_calls"]
        and not state["output_exhausted"]
        and state["remaining_chars"] >= budget_error_size
    )

    # 2.准备本次模型调用信息

    # 使用 uuid4() 创建唯一 call_id，并转成字符串。
    call_id = str(uuid4())

    # 如果 execution_info 存在，使用 node_attempt；
    # 否则默认使用 1。
    execution_info = runtime.execution_info
    attempt = execution_info.node_attempt if execution_info else 1

    # 3. 记录 MODEL_CALL_STARTED
    emit_agent_event(
        runtime,
        event_type="MODEL_CALL_STARTED",
        node_name="model",
        message="Model call started",
        payload={
            "call_id": call_id,
            "step_id": "model",
            "attempt": attempt,
            "allow_tools": allow_tools,
            "model": config.CHAT_MODEL,
        },
    )

    # 使用 perf_counter() 记录单调时钟开始时间。
    started_at = perf_counter()

    # 4.调用模型
    try:
        assistant_message = request_tool_turn(
            state["messages"],
            allow_tools=allow_tools,
        )

    except Exception as exc:
        # 计算 duration_ms：
        # int((perf_counter() - started_at) * 1000)
        duration_ms = int((perf_counter() - started_at) * 1000)

        try:
            emit_agent_event(
                runtime,
                event_type="MODEL_CALL_FAILED",
                node_name="model",
                message="Model call failed",
                payload={
                    "call_id": call_id,
                    "step_id": "model",
                    "attempt": attempt,
                    "duration_ms": duration_ms,

                    # 只记录异常类型名称，不记录 str(exc)。
                    "error_type": type(exc).__name__,
                },
            )
        except Exception:
            logger.exception(
                "Failed to persist model failure event; call_id=%s",
                call_id,
            )

        raise

    # 5.判断模型返回类型
    tool_calls = assistant_message.get("tool_calls") or []

    # 有 tool_calls 时为 "tool_calls"；
    # 否则为 "answer"。
    response_type = "tool_calls" if tool_calls else "answer"

    # 计算成功调用耗时。
    duration_ms = int((perf_counter() - started_at) * 1000)

    # 6. 记录 MODEL_CALL_COMPLETED
    emit_agent_event(
        runtime,
        event_type="MODEL_CALL_COMPLETED",
        node_name="model",
        message="Model call completed",
        payload={
            "call_id": call_id,
            "step_id": "model",
            "attempt": attempt,
            "duration_ms": duration_ms,
            "response_type": response_type,

            # 记录本次返回的工具调用数量。
            "tool_call_count": len(tool_calls),
        },
    )

    # 7. 返回 State 增量
    new_messages = list(state["messages"])
    new_messages.append(assistant_message)
    return {
        # 创建新列表，将 assistant_message 放在原 messages 后面。
        "messages": new_messages,
        "allow_tools": allow_tools,
    }


def route_after_model(
    state: ReadonlyAgentState,
) -> Literal["tools", "finish"]:
    last_message = state["messages"][-1]

    # 1. 检查 messages[-1] 中是否有非空 tool_calls。
    if last_message.get("tool_calls"):
        return "tools"

    # 2. 有则返回 tools，否则返回 finish。
    else:
        return "finish"



def tools_node(
        state: ReadonlyAgentState,
        runtime: Runtime[AgentRunContext]
) -> dict:
    # 1. 从最后一条 assistant 消息取出本批 tool_calls。
    tool_calls = state["messages"][-1]["tool_calls"]

    # 2. 将需要更新的列表复制到局部变量。
    messages = list(state["messages"])
    tool_trace = list(state["tool_trace"])
    sources = list(state["sources"])

    # 3. 保留调用前的 allow_tools 和整批错误消息预算检查。
    used_calls = state["used_calls"]
    remaining_chars = state["remaining_chars"]
    output_exhausted = state["output_exhausted"]

    budget_error_text = json.dumps(BUDGET_ERROR, ensure_ascii=False)
    budget_error_size = len(budget_error_text)

    if not state["allow_tools"]:
        raise ValueError("Model requested tools after the tool budget was exhausted")

    if remaining_chars < budget_error_size * len(tool_calls):
        execution_info = runtime.execution_info
        attempt = execution_info.node_attempt if execution_info else 1
        emit_agent_event(
            runtime,
            event_type="BUDGET_EXCEEDED",
            node_name="tools",
            message="Tool batch rejected due to budget",
            payload={
                "step_id": "tools",
                "attempt": attempt,
                "action": "reject_batch",
                "reason": "tool_result_chars",
                "attempted": False,
                "requested_calls": len(tool_calls),
                "required_chars": budget_error_size * len(tool_calls),
                "remaining_chars": remaining_chars,
            },
        )
        raise ValueError("Too many tool calls for the remaining tool-result budget")

    # 4. 搬入现有 for call_index, call in enumerate(tool_calls) 循环。
    for call_index, call in enumerate(tool_calls):
        function_name = call["function"]["name"]
        arguments_text = call["function"]["arguments"]

        # 本次工具调用的内部唯一编号。
        call_id = str(uuid4())

        # 取得当前节点执行次数，参考 model_node 的写法。
        execution_info = runtime.execution_info
        attempt = execution_info.node_attempt if execution_info else 1

        # 开始、成功、失败事件共享这些字段。
        base_payload = {
            "call_id": call_id,
            "tool_call_id": call["id"],
            "tool_name": function_name,
            "step_id": "tools",
            "attempt": attempt,
        }

        # 第一阶段：决定是否真正执行工具
        if used_calls >= state["max_tool_calls"] or output_exhausted:
            # 跳过是预算决策，不是一次实际执行，不能发出 TOOL_CALL_STARTED/FAILED。
            emit_agent_event(
                runtime,
                event_type="BUDGET_EXCEEDED",
                node_name="tools",
                message="Tool execution skipped due to budget",
                payload={
                    **base_payload,
                    "action": "skip_tool",
                    "reason": "tool_calls" if used_calls >= state["max_tool_calls"] else "tool_result_chars",
                    "attempted": False,
                    "used_calls": used_calls,
                    "max_tool_calls": state["max_tool_calls"],
                    "remaining_chars": remaining_chars,
                },
            )
            result = dict(BUDGET_ERROR)
        else:
            # 一旦开始处理这次调用，即使参数错误，也要消耗调用次数
            used_calls += 1

            # None 表示目前没有发现可恢复错误。
            error_type: str | None = None

            emit_agent_event(
                runtime,
                event_type="TOOL_CALL_STARTED",
                node_name="tools",
                message="Tool call started",
                payload={
                    **base_payload,
                    "arguments_chars": len(arguments_text),
                },
            )

            started_at = perf_counter()

            try:
                args = json.loads(arguments_text)

                if not isinstance(args, dict):
                    raise ValueError("argument must be a dict")

                result = execute_readonly_tool(
                    state["repository_id"],
                    tool_name=function_name,
                    arguments=args,
                )

            except RepositoryScanError as exc:
                error_type = type(exc).__name__

                # 记录 warning，不要把底层文件系统信息暴露给模型
                logger.warning(
                    "Agent source read failed; repository_id=%s",
                    state["repository_id"],
                    exc_info=True,
                )
                result = {
                    "error": "Cannot read requested source; check the path or search again"
                }

            except (ValueError, FileSkippedError, SyntaxError) as exc:
                error_type = type(exc).__name__

                # 将错误字符串限制在 MAX_TOOL_ERROR_CHARS
                result = {
                    "error": str(exc)[:MAX_TOOL_ERROR_CHARS],
                }

            except Exception as exc:
                try:
                    # 1. 调用 emit_agent_event
                    emit_agent_event(
                        runtime,
                        event_type="TOOL_CALL_FAILED",
                        node_name="tools",
                        message="Tool call failed",
                        payload={
                            **base_payload,
                            "duration_ms": int((perf_counter() - started_at) * 1000),
                            "error_type": type(exc).__name__,
                            "recoverable": False,
                        }
                    )

                except Exception:
                    logger.exception(
                        "Failed to persist tool failure event; call_id=%s",
                        call_id,
                    )
                raise

            duration_ms = int((perf_counter() - started_at) * 1000)

            if error_type is None:
                emit_agent_event(
                    runtime,
                    event_type="TOOL_CALL_COMPLETED",
                    node_name="tools",
                    message="Tool call completed",
                    payload={
                        **base_payload,
                        "duration_ms": duration_ms,
                    }
                )

            else:
                emit_agent_event(
                    runtime,
                    event_type="TOOL_CALL_FAILED",
                    node_name="tools",
                    message="Tool call failed",
                    payload={
                        **base_payload,
                        "duration_ms": duration_ms,
                        "error_type": error_type,
                        "recoverable": True,
                    }
                )

        # 第二阶段：从成功结果中准备候选证据
        result, pending_sources = prepare_evidence(
            function_name,
            result,
            len(sources),
        )

        result_text = json.dumps(result, ensure_ascii=False)

        # 第三阶段：检查字符预算
        calls_after_current = len(tool_calls) - call_index - 1
        reserved_chars = calls_after_current * budget_error_size

        if len(result_text) > remaining_chars - reserved_chars:

            emit_agent_event(
                runtime,
                event_type="BUDGET_EXCEEDED",
                node_name="tools",
                message="Tool result discarded due to budget",
                payload={
                    **base_payload,
                    "action": "discard_result",
                    "reason": "tool_result_chars",
                    "attempted": True,
                    "result_chars": len(result_text),
                    "remaining_chars": remaining_chars,
                    "reserved_chars": reserved_chars,
                    "available_chars": remaining_chars - reserved_chars,
                },
            )

            # 1. 将 result 换成 BUDGET_ERROR
            result = dict(BUDGET_ERROR)

            # 2. result_text 换成 budget_error_text
            result_text = budget_error_text

            # 3. 清空 pending_sources
            pending_sources = []

            # 4. 将 output_exhausted 设为 True
            output_exhausted = True

        remaining_chars -= len(result_text)

        # 只有实际发给模型的证据才能进入 sources
        sources.extend(pending_sources)

        # 第四阶段：添加协议要求的 tool 消息
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result_text,
            }
        )

        # 第五阶段：记录实际发送给模型的结果
        tool_trace.append(
            {
                "tool_call_id": call["id"],
                "tool_name": function_name,
                "arguments": arguments_text,
                "result": result,
            }
        )


    # 5. 返回更新后的消息、记录、证据及预算字段。
    return {
        "messages": messages,
        "tool_trace": tool_trace,
        "sources": sources,
        "used_calls": used_calls,
        "remaining_chars": remaining_chars,
        "output_exhausted": output_exhausted,
    }


def finish_node(state: ReadonlyAgentState) -> dict:
    # 1. 从最后一条 assistant 消息取得 content。
    content = state["messages"][-1]["content"]

    # 2. 调用 finish_answer，传入 sources 和 tool_trace。
    result = finish_answer(content, state["sources"], state["tool_trace"])

    # 3. 返回 {"result": 校验后的结果}。
    return {"result": result}

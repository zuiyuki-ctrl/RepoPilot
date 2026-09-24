from langgraph.graph import START, END, StateGraph

from .context import AgentRunContext
from .state import ReadonlyAgentState, PlanningAgentState
from .nodes import model_node, tools_node, finish_node, route_after_model, plan_node


def build_readonly_agent_graph():
    # 使用 ReadonlyAgentState 创建 StateGraph。
    builder = StateGraph(
        state_schema=ReadonlyAgentState,
        context_schema=AgentRunContext
    )

    # 注册 model、tools、finish 三个节点。
    builder.add_node("model", model_node)
    builder.add_node("tools", tools_node)
    builder.add_node("finish", finish_node)

    # 添加 START → model。
    builder.add_edge(START, "model")

    # 给 model 添加条件边：tools 路由到 tools
    # finish 路由到 finish
    builder.add_conditional_edges(
        "model",
        route_after_model,
        {
            "tools": "tools",
            "finish": "finish",
        }
    )

    # 添加 tools → model。
    builder.add_edge("tools", "model")

    # 添加 finish → END。
    builder.add_edge("finish", END)

    # compile() 并返回
    return builder.compile()


READONLY_AGENT_GRAPH = build_readonly_agent_graph()


def build_planning_agent_graph():
    # 1. 使用 PlanningAgentState 和现有 AgentRunContext 创建 StateGraph。
    builder = StateGraph(
        state_schema=PlanningAgentState,
        context_schema=AgentRunContext,
    )

    # 2. 注册研究阶段和计划阶段需要的三个节点：
    #    "model" → model_node
    #    "tools" → tools_node
    #    "plan"  → plan_node

    builder.add_node("model", model_node)
    builder.add_node("tools", tools_node)
    builder.add_node("plan", plan_node)

    # 3. 添加 START → model。
    builder.add_edge(START, "model")

    # 4. 给 model 添加条件边，继续复用 route_after_model：
    #    route_after_model 返回 "tools" 时进入 tools；
    #    返回 "finish" 时不要进入 finish_node，而是进入 plan_node。
    builder.add_conditional_edges(
        "model",
        route_after_model,
        {
            "tools": "tools",
            "finish": "plan",
        }
    )

    # 5. 添加 tools → model。
    builder.add_edge("tools", "model")

    # 6. 添加 plan → END。
    builder.add_edge("plan", END)

    # 7. compile() 并返回。
    return builder.compile()

PLANNING_AGENT_GRAPH = build_planning_agent_graph()

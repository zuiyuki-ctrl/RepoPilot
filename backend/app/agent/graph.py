from langgraph.graph import START, END, StateGraph

from .state import ReadonlyAgentState
from .nodes import model_node, tools_node, finish_node, route_after_model


def build_readonly_agent_graph():
    # 使用 ReadonlyAgentState 创建 StateGraph。
    builder = StateGraph(ReadonlyAgentState)

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
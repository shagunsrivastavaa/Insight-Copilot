"""LangGraph workflow for the Insight Copilot analysis assistant."""

from typing import Literal

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    execute_tools_node,
    plan_node,
    route_node,
    synthesize_node,
)
from agent.state import InsightCopilotState


def _route_after_route(
    state: InsightCopilotState,
) -> Literal["execute_tools", "synthesize"]:
    """Skip execution when routing failed or selected no tools."""
    if state.get("error") or not state.get("selected_tools"):
        return "synthesize"
    return "execute_tools"


workflow = StateGraph(InsightCopilotState)
workflow.add_node("plan", plan_node)
workflow.add_node("route", route_node)
workflow.add_node("execute_tools", execute_tools_node)
workflow.add_node("synthesize", synthesize_node)

workflow.add_edge(START, "plan")
workflow.add_edge("plan", "route")
workflow.add_conditional_edges(
    "route",
    _route_after_route,
    {
        "execute_tools": "execute_tools",
        "synthesize": "synthesize",
    },
)
workflow.add_edge("execute_tools", "synthesize")
workflow.add_edge("synthesize", END)

graph = workflow.compile()


def run_query(query: str) -> dict:
    """Run one non-empty question through the compiled Insight Copilot graph."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return graph.invoke({"query": query})


if __name__ == "__main__":
    result = run_query("What are the top five product categories by item sales?")
    print(result.get("final_answer", "No final answer was returned."))

from typing import Any, TypedDict


class _RequiredInsightCopilotState(TypedDict):
    query: str  # The user's current question about the dataset.


class InsightCopilotState(_RequiredInsightCopilotState, total=False):
    """State shared between Insight Copilot's LangGraph nodes."""

    plan: str  # A short plan that can be shown to the user.
    reasoning_trace: list[str]  # Concise, user-visible explanations of routing decisions.
    selected_tools: list[str]  # Names of tools chosen to answer the query.
    tool_inputs: dict[str, dict[str, Any]]  # Arguments to pass to each selected tool.
    tool_results: dict[str, Any]  # Results returned by the selected tools.
    chart_data: dict[str, Any]  # Optional data or specification for a chart.
    final_answer: str  # The user-facing answer synthesized from the results.
    error: str  # An error message if a graph step cannot complete.

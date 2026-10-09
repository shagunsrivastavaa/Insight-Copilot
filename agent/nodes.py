"""LangGraph node functions for Insight Copilot."""

import re
from typing import Any

from agent.router import route_query
from agent.state import InsightCopilotState
from tools.data_tool import query_data
from tools.delivery_tool import query_delivery_performance
from tools.trend_tool import query_monthly_orders


def plan_node(state: InsightCopilotState) -> dict:
    """Return a short, user-visible plan without selecting or running tools."""
    query = state.get("query", "")
    normalized = " ".join(query.casefold().split()) if isinstance(query, str) else ""

    asks_for_trends = bool(
        re.search(r"\bmonthly\b.{0,30}\b(?:orders?|trends?|volume|counts?)\b", normalized)
        or re.search(r"\borders?\b.{0,30}\b(?:by month|per month|over time|trends?)\b", normalized)
        or "order volume" in normalized
    )
    asks_for_delivery = bool(
        re.search(r"\blate[- ]deliver(?:y|ies)\b", normalized)
        or re.search(r"\bdelivery\s+(?:duration|time|performance)\b", normalized)
        or ("actual delivery" in normalized and "estimated delivery" in normalized)
        or "time to deliver" in normalized
    )
    has_product_sales_context = bool(
        re.search(r"\b(?:products?|items?|categor(?:y|ies))\b", normalized)
        and re.search(
            r"\b(?:sales?|revenue|sold|selling|sell|top|best|rank|ranking)\b",
            normalized,
        )
    )

    if asks_for_trends and asks_for_delivery:
        plan = (
            "I'll summarize monthly order counts and delivery-performance measures separately, "
            "then relate the returned results without assuming a cause."
        )
    elif asks_for_trends:
        plan = "I'll summarize monthly order counts and identify the highest-count month in the requested results."
    elif asks_for_delivery:
        plan = (
            "I'll calculate delivery duration and late-arrival performance using only the valid timestamps "
            "required for each measure."
        )
    elif has_product_sales_context:
        plan = "I'll rank the requested products or categories by item sales value and summarize the leading results."
    elif isinstance(query, str) and query.strip():
        plan = "I'll identify the metric and scope in your question, then prepare a concise summary from the dataset."
    else:
        plan = "I'll first identify what dataset question needs answering, then outline a concise analysis."

    return {"plan": plan}


def route_node(state: InsightCopilotState) -> dict:
    """Delegate routing to the existing deterministic query router."""
    return route_query(state)


def execute_tools_node(state: InsightCopilotState) -> dict:
    """Run only selected tools and collect structured results and tool errors."""
    if state.get("error") or not state.get("selected_tools"):
        return {"tool_results": {}}

    selected_tools = state["selected_tools"]
    inputs_by_tool = state.get("tool_inputs", {})
    tool_results: dict[str, Any] = {}
    tool_errors: list[str] = []

    for tool_name in selected_tools:
        try:
            if not isinstance(inputs_by_tool, dict):
                raise TypeError("tool_inputs must be a dictionary")
            tool_inputs = inputs_by_tool.get(tool_name, {})
            if tool_inputs is None:
                tool_inputs = {}
            if not isinstance(tool_inputs, dict):
                raise TypeError(f"arguments for {tool_name} must be a dictionary")

            if tool_name == "data_tool":
                result = query_data(
                    operation=tool_inputs.get("operation", "top_categories"),
                    top_n=tool_inputs.get("top_n", 10),
                )
            elif tool_name == "trend_tool":
                result = query_monthly_orders(
                    start_month=tool_inputs.get("start_month"),
                    end_month=tool_inputs.get("end_month"),
                )
            elif tool_name == "delivery_tool":
                result = query_delivery_performance()
            else:
                raise ValueError(f"Unsupported tool name: {tool_name}")

            tool_results[tool_name] = result
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            tool_results[tool_name] = {"error": message}
            tool_errors.append(f"{tool_name}: {message}")

    return {
        "tool_results": tool_results,
        "error": "; ".join(tool_errors),
    }


def _format_value(value: Any) -> str:
    """Format a numeric result compactly, preserving non-numeric values."""
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def _summarize_data_result(result: dict[str, Any]) -> str:
    """Describe the leading product or category item-sales records."""
    operation = result.get("operation")
    records = result.get("records", [])
    label = "Product" if operation == "top_products" else "Category"
    lines = [f"Product/category item-sales ranking ({label.lower()} leaders):"]
    metric = result.get("metric")
    if metric:
        lines.append(f"Metric: {metric}")

    if not records:
        lines.append("No ranking records were returned.")
        return "\n".join(lines)

    for index, record in enumerate(records, start=1):
        item_sales_value = _format_value(record.get("item_sales_value", "unknown"))
        if operation == "top_products":
            product_id = record.get("product_id", "unknown product")
            category = record.get("category")
            description = f"product {product_id}"
            if category:
                description += f" ({category})"
        else:
            description = str(record.get("category", "Unknown category"))
        lines.append(f"{index}. {description}: {item_sales_value} item sales value")
    return "\n".join(lines)


def _summarize_trend_result(result: dict[str, Any]) -> str:
    """Summarize returned monthly counts and their highest-count month."""
    records = result.get("records", [])
    lines = ["Monthly order trend:"]
    metric = result.get("metric")
    if metric:
        lines.append(f"Metric: {metric}")

    if not records:
        lines.append("No monthly records were returned for this request.")
        return "\n".join(lines)

    count_records = []
    for record in records:
        try:
            count_records.append((str(record["month"]), int(record["order_count"])))
        except (KeyError, TypeError, ValueError):
            continue

    if not count_records:
        lines.append("The returned records did not contain usable month/count pairs.")
        return "\n".join(lines)

    returned_counts = "; ".join(
        f"{month}: {count:,}" for month, count in count_records
    )
    lines.append(f"Returned monthly order counts: {returned_counts}.")
    highest_count = max(count for _, count in count_records)
    highest_months = [month for month, count in count_records if count == highest_count]
    lines.append(
        f"Highest among the returned months: {', '.join(highest_months)} "
        f"with {highest_count:,} orders."
    )
    return "\n".join(lines)


def _summarize_delivery_result(result: dict[str, Any]) -> str:
    """Report delivery measures with the denominator for each calculation."""
    values = result.get("results", {})
    definitions = result.get("metric_definitions", {})
    lines = ["Delivery performance:"]

    total_orders = values.get("total_distinct_orders")
    if total_orders is not None:
        lines.append(f"Total distinct orders: {int(total_orders):,}.")

    duration_denominator = values.get(
        "delivered_orders_with_valid_purchase_and_delivery_timestamps", 0
    )
    average_days = values.get("average_delivery_duration_days")
    if average_days is None:
        lines.append(
            "Average delivery duration is unavailable because no eligible delivered orders were returned."
        )
    else:
        lines.append(
            f"Average delivery duration: {_format_value(average_days)} days "
            f"across {int(duration_denominator):,} delivered orders with valid purchase "
            "and actual delivery timestamps."
        )

    lateness_denominator = values.get(
        "delivered_orders_with_valid_actual_and_estimated_timestamps", 0
    )
    late_count = values.get("late_delivered_orders", 0)
    late_percentage = values.get("late_delivery_percentage")
    if late_percentage is None:
        lines.append(
            "Late-delivery percentage is unavailable because no delivered orders had both valid actual and estimated delivery timestamps."
        )
    else:
        lines.append(
            f"Late deliveries: {int(late_count):,} of {int(lateness_denominator):,} "
            f"eligible delivered orders ({_format_value(late_percentage)}%). "
            "Eligibility requires valid actual and estimated delivery timestamps; "
            "an order is late only when actual delivery is after the estimate. "
            "Undelivered orders are not classified as late."
        )

    duration_definition = definitions.get(
        "average_delivery_duration_days", ""
    )
    if duration_definition and not duration_denominator:
        lines.append(f"Duration definition: {duration_definition}")
    return "\n".join(lines)


def synthesize_node(state: InsightCopilotState) -> dict:
    """Build a deterministic answer from tool results and documented metrics."""
    selected_tools = state.get("selected_tools", [])
    routing_error = state.get("error", "")
    if not selected_tools:
        if routing_error:
            return {"final_answer": routing_error}
        return {"final_answer": "No analysis tool was selected, so I could not produce an answer."}

    tool_results = state.get("tool_results", {})
    tool_results = tool_results if isinstance(tool_results, dict) else {}
    successful_results: list[tuple[str, dict[str, Any]]] = []
    failed_tools: list[str] = []

    for tool_name in selected_tools:
        result = tool_results.get(tool_name)
        if isinstance(result, dict) and result.get("error"):
            failed_tools.append(f"{tool_name}: {result['error']}")
        elif isinstance(result, dict):
            successful_results.append((tool_name, result))
        else:
            failed_tools.append(f"{tool_name}: no result was returned")

    if not successful_results:
        details = "; ".join(failed_tools)
        answer = "I couldn't complete the requested analysis."
        if details:
            answer += f" {details}"
        elif routing_error:
            answer += f" {routing_error}"
        return {"final_answer": answer}

    sections = []
    for tool_name, result in successful_results:
        if tool_name == "data_tool":
            sections.append(_summarize_data_result(result))
        elif tool_name == "trend_tool":
            sections.append(_summarize_trend_result(result))
        elif tool_name == "delivery_tool":
            sections.append(_summarize_delivery_result(result))

    if failed_tools:
        sections.append("Some requested analyses could not be completed: " + "; ".join(failed_tools))
    elif routing_error:
        sections.append(f"Execution note: {routing_error}")

    return {"final_answer": "\n\n".join(sections)}

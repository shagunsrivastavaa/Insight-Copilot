"""Route Insight Copilot questions to the data-analysis tools."""

import re

from agent.state import InsightCopilotState


_MONTH = r"\d{4}-(?:0[1-9]|1[0-2])"
_MONTH_TOKEN = r"\d{4}-[A-Za-z0-9]*"
_MONTH_RANGE_PATTERNS = (
    re.compile(
        rf"\b(?:between|from)\s+(?P<start>{_MONTH_TOKEN})\s+"
        rf"(?:and|to|through|until)\s+(?P<end>{_MONTH_TOKEN})\b"
    ),
    re.compile(
        rf"\b(?P<start>{_MONTH_TOKEN})\s+(?:to|through|until)\s+"
        rf"(?P<end>{_MONTH_TOKEN})\b"
    ),
)


def _has_data_intent(query: str) -> bool:
    """Require a product/category subject plus relevant sales or ranking intent."""
    subject = r"(?:products?|items?|categor(?:y|ies))"
    has_subject = re.search(rf"\b{subject}\b", query)
    has_sales_intent = re.search(
        r"\b(?:sales?|revenue|sold|selling|sell)\b", query
    )
    has_ranking_intent = any(
        re.search(pattern, query)
        for pattern in (
            rf"\b(?:top|best|highest|lowest|most|least)\s+(?:\d+\s+)?(?:selling\s+)?{subject}\b",
            rf"\b{subject}\s+(?:ranking|rank|ranked)\b",
            rf"\brank(?:ing|ed)?\b.{{0,15}}\b{subject}\b",
            r"\bcategor(?:y|ies)\b.{0,25}\b(?:performance|perform(?:s|ed|ing)?)\b",
            r"\b(?:performance|perform(?:s|ed|ing)?)\b.{0,25}\bcategor(?:y|ies)\b",
        )
    )
    return bool(has_subject and (has_sales_intent or has_ranking_intent))

def _is_product_ranking(query: str) -> bool:
    """Return whether a ranking is specifically about individual products."""
    mentions_product = re.search(r"\b(?:products?|items?)\b", query)
    mentions_category = re.search(r"\bcategor(?:y|ies)\b", query)
    ranking_word = re.search(
        r"\b(?:top|best|highest|lowest|most|least|rank|ranking|selling|sold)\b",
        query,
    )
    return bool(mentions_product and ranking_word and not mentions_category)


def _has_trend_intent(query: str) -> bool:
    """Recognize questions about order volume across calendar time."""
    patterns = (
        r"\bmonthly\s+(?:trends?|orders?|order volume|order counts?|volume)\b",
        r"\borders?\s+(?:trends?|over time|by month|per month|each month)\b",
        r"\border volume\b",
        r"\border counts?\s+(?:by|per|each)\s+month\b",
        r"\b(?:number|count)\s+of\s+orders?\s+(?:by|per|each)\s+month\b",
        r"\bhow many orders?\s+(?:by|per|each)\s+month\b",
    )
    return any(re.search(pattern, query) for pattern in patterns)


def _has_delivery_intent(query: str) -> bool:
    """Recognize delivery performance, not generic delivery preferences/options."""
    patterns = (
        r"\blate[- ]deliver(?:y|ies)\b",
        r"\b(?:late|delayed)\s+(?:delivery|deliveries|orders?)\b",
        r"\b(?:delivery|deliveries|orders?)\s+(?:were\s+)?(?:late|delayed)\b",
        r"\blate[- ]delivery\s+(?:rate|percentage|percent|share)\b",
        r"\bdelivery\s+(?:duration|time|times)\b",
        r"\b(?:time|duration)\s+to\s+deliver\b",
        r"\bdelivery\s+performance\b",
        r"\bactual delivery\b.{0,40}\bestimated delivery\b",
        r"\bestimated delivery\b.{0,40}\bactual delivery\b",
        r"\b(?:actual|estimated)\b.{0,30}\b(?:vs\.?|versus|compared with|compared to|against)\b.{0,30}\b(?:actual|estimated)\b.{0,30}\b(?:delivery|date|arrival)\b",
        r"\b(?:arrival|delivery)\s+(?:date|time)\s+(?:vs\.?|versus|compared with|compared to)\b",
    )
    return any(re.search(pattern, query) for pattern in patterns)


def _extract_month_range(query: str) -> tuple[str, str] | None:
    """Extract an explicit, valid YYYY-MM to YYYY-MM range, if present."""
    for pattern in _MONTH_RANGE_PATTERNS:
        match = pattern.search(query)
        if match:
            return match.group("start"), match.group("end")
    return None


def route_query(state: InsightCopilotState) -> dict:
    """Choose relevant tools and return routing updates for LangGraph."""
    raw_query = state.get("query", "")
    if not isinstance(raw_query, str) or not raw_query.strip():
        return {
            "selected_tools": [],
            "tool_inputs": {},
            "reasoning_trace": ["No usable question was provided, so no tool was selected."],
            "error": "Please provide a question about product sales, order trends, or delivery performance.",
        }

    # Normalize case and whitespace so the matching rules are predictable.
    query = " ".join(raw_query.casefold().split())
    wants_data = _has_data_intent(query)
    wants_trend = _has_trend_intent(query)
    wants_delivery = _has_delivery_intent(query)
    comparison_words = re.search(
        r"\b(?:compare|comparison|versus|vs\.?|against|difference|differ)\b",
        query,
    )

    month_range = _extract_month_range(query) if wants_trend else None
    if month_range and any(not re.fullmatch(_MONTH, month) for month in month_range):
        return {
            "selected_tools": [],
            "tool_inputs": {},
            "reasoning_trace": [
                "The requested month range contains a month that is not in YYYY-MM format."
            ],
            "error": "Both months in an explicit range must use YYYY-MM format with a month from 01 to 12.",
        }
    if month_range and month_range[0] > month_range[1]:
        return {
            "selected_tools": [],
            "tool_inputs": {},
            "reasoning_trace": ["The requested month range starts after it ends."],
            "error": "The start month must be on or before the end month.",
        }

    selected_tools: list[str] = []
    tool_inputs: dict[str, dict] = {}
    reasoning_trace: list[str] = []

    # Keep a stable order for explicit delivery-versus-trend comparisons.
    if wants_trend and wants_delivery and comparison_words:
        selected_tools.extend(["delivery_tool", "trend_tool"])
        if wants_data:
            selected_tools.append("data_tool")
    else:
        if wants_data:
            selected_tools.append("data_tool")
        if wants_trend:
            selected_tools.append("trend_tool")
        if wants_delivery:
            selected_tools.append("delivery_tool")

    if wants_data:
        operation = "top_products" if _is_product_ranking(query) else "top_categories"
        tool_inputs["data_tool"] = {"operation": operation, "top_n": 5}

    if wants_trend:
        tool_inputs["trend_tool"] = (
            {"start_month": month_range[0], "end_month": month_range[1]}
            if month_range
            else {}
        )

    if wants_delivery:
        tool_inputs["delivery_tool"] = {}

    if wants_trend and wants_delivery and comparison_words:
        reasoning_trace.append(
            "You asked to compare order trends with delivery performance, so both trend_tool and delivery_tool are needed."
        )
    else:
        if wants_data:
            if tool_inputs["data_tool"]["operation"] == "top_products":
                reasoning_trace.append(
                    "You asked for an individual product ranking, so data_tool will rank products by item sales."
                )
            else:
                reasoning_trace.append(
                    "You asked about sales or performance by product/category, so data_tool will rank categories by item sales."
                )
        if wants_trend:
            reasoning_trace.append(
                "You asked about monthly order volume, so trend_tool will count orders by month."
            )
        if wants_delivery:
            reasoning_trace.append(
                "You asked about delivery duration, lateness, or estimated-versus-actual performance, so delivery_tool will calculate delivery metrics."
            )

    if month_range:
        reasoning_trace.append(
            f"The trend tool will use the inclusive range {month_range[0]} through {month_range[1]}."
        )

    if not selected_tools:
        return {
            "selected_tools": [],
            "tool_inputs": {},
            "reasoning_trace": [
                "The question does not clearly match a supported sales, monthly-order, or delivery-performance analysis."
            ],
            "error": (
                "I couldn't determine which analysis you need. Ask about product/category sales, "
                "monthly order volume, or delivery performance."
            ),
        }

    return {
        "selected_tools": selected_tools,
        "tool_inputs": tool_inputs,
        "reasoning_trace": reasoning_trace,
        "error": "",
    }


def main() -> None:
    """Run routing-only assertions without invoking tools or loading CSVs."""
    cases = [
        (
            "Top five products by item sales",
            ["data_tool"],
            {"data_tool": {"operation": "top_products", "top_n": 5}},
            False,
        ),
        (
            "Best-selling categories",
            ["data_tool"],
            {"data_tool": {"operation": "top_categories", "top_n": 5}},
            False,
        ),
        (
            "Monthly order trends from 2017-01 to 2017-03",
            ["trend_tool"],
            {"trend_tool": {"start_month": "2017-01", "end_month": "2017-03"}},
            False,
        ),
        (
            "What was the late-delivery percentage?",
            ["delivery_tool"],
            {"delivery_tool": {}},
            False,
        ),
        (
            "Compare monthly order trends and delivery performance",
            ["delivery_tool", "trend_tool"],
            {"delivery_tool": {}, "trend_tool": {}},
            False,
        ),
        (
            "Tell me something interesting",
            [],
            {},
            True,
        ),
        (
            "Which delivery options are available?",
            [],
            {},
            True,
        ),
        (
            "Which products have the best delivery options?",
            [],
            {},
            True,
        ),
    ]

    for question, expected_tools, expected_inputs, expects_error in cases:
        updates = route_query({"query": question})
        assert updates["selected_tools"] == expected_tools, question
        assert updates["tool_inputs"] == expected_inputs, question
        assert bool(updates.get("error")) is expects_error, question
        print(f"PASS: {question}")

    reversed_range = route_query(
        {"query": "Monthly order trends from 2017-03 to 2017-01"}
    )
    assert reversed_range["selected_tools"] == []
    assert reversed_range["tool_inputs"] == {}
    assert reversed_range["error"]
    print("PASS: reversed month ranges return an error")


if __name__ == "__main__":
    main()





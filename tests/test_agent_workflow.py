"""Focused, dataset-independent tests for routing and analysis nodes."""

import unittest
from unittest.mock import patch

from agent.graph import run_query
from agent.nodes import execute_tools_node, synthesize_node
from agent.router import route_query


class RouteQueryTests(unittest.TestCase):
    def test_category_ranking_selects_data_tool(self) -> None:
        updates = route_query(
            {"query": "What are the top five product categories by item sales?"}
        )

        self.assertEqual(updates["selected_tools"], ["data_tool"])
        self.assertEqual(
            updates["tool_inputs"],
            {"data_tool": {"operation": "top_categories", "top_n": 5}},
        )
        self.assertEqual(updates["error"], "")

    def test_product_ranking_selects_data_tool(self) -> None:
        updates = route_query({"query": "Top five products by item sales"})

        self.assertEqual(updates["selected_tools"], ["data_tool"])
        self.assertEqual(
            updates["tool_inputs"]["data_tool"],
            {"operation": "top_products", "top_n": 5},
        )

    def test_monthly_trends_keep_explicit_date_range(self) -> None:
        updates = route_query(
            {"query": "Show monthly order trends from 2017-01 to 2017-03"}
        )

        self.assertEqual(updates["selected_tools"], ["trend_tool"])
        self.assertEqual(
            updates["tool_inputs"]["trend_tool"],
            {"start_month": "2017-01", "end_month": "2017-03"},
        )
        self.assertEqual(updates["error"], "")

    def test_malformed_start_month_returns_routing_error(self) -> None:
        updates = route_query(
            {"query": "Show monthly order trends from 2017-1 to 2017-03"}
        )

        self.assertEqual(updates["selected_tools"], [])
        self.assertTrue(updates["error"])
        self.assertIn("YYYY-MM", updates["error"])

    def test_malformed_end_month_returns_routing_error(self) -> None:
        updates = route_query(
            {"query": "Show monthly order trends from 2017-01 to 2017-3"}
        )

        self.assertEqual(updates["selected_tools"], [])
        self.assertTrue(updates["error"])
        self.assertIn("YYYY-MM", updates["error"])

    def test_valid_month_range_is_preserved(self) -> None:
        updates = route_query(
            {"query": "Show monthly order trends from 2017-01 to 2017-03"}
        )

        self.assertEqual(updates["selected_tools"], ["trend_tool"])
        self.assertEqual(
            updates["tool_inputs"]["trend_tool"],
            {"start_month": "2017-01", "end_month": "2017-03"},
        )
        self.assertEqual(updates["error"], "")

    def test_late_delivery_question_selects_delivery_tool(self) -> None:
        updates = route_query({"query": "What was the late-delivery percentage?"})

        self.assertEqual(updates["selected_tools"], ["delivery_tool"])
        self.assertEqual(updates["tool_inputs"]["delivery_tool"], {})

    def test_trend_and_delivery_comparison_selects_both_tools(self) -> None:
        updates = route_query(
            {
                "query": (
                    "Compare monthly order trends from 2017-01 to 2017-03 "
                    "and delivery performance"
                )
            }
        )

        self.assertEqual(updates["selected_tools"], ["delivery_tool", "trend_tool"])
        self.assertEqual(
            updates["tool_inputs"],
            {
                "delivery_tool": {},
                "trend_tool": {"start_month": "2017-01", "end_month": "2017-03"},
            },
        )

    def test_unclear_question_returns_routing_error_without_tools(self) -> None:
        updates = route_query({"query": "Tell me something interesting"})

        self.assertEqual(updates["selected_tools"], [])
        self.assertTrue(updates["error"])

    def test_reversed_month_range_returns_error_without_tools(self) -> None:
        updates = route_query(
            {"query": "Show monthly order trends from 2017-03 to 2017-01"}
        )

        self.assertEqual(updates["selected_tools"], [])
        self.assertTrue(updates["error"])
        self.assertIn("on or before", updates["error"])


class ExecuteToolsNodeTests(unittest.TestCase):
    @patch("agent.nodes.query_delivery_performance")
    @patch("agent.nodes.query_monthly_orders")
    @patch("agent.nodes.query_data")
    def test_only_selected_tools_are_executed(
        self, query_data, query_monthly_orders, query_delivery_performance
    ) -> None:
        query_data.return_value = {"operation": "top_categories", "records": []}

        updates = execute_tools_node(
            {
                "query": "top categories",
                "selected_tools": ["data_tool"],
                "tool_inputs": {
                    "data_tool": {"operation": "top_categories", "top_n": 3}
                },
            }
        )

        query_data.assert_called_once_with(operation="top_categories", top_n=3)
        query_monthly_orders.assert_not_called()
        query_delivery_performance.assert_not_called()
        self.assertEqual(
            updates["tool_results"],
            {"data_tool": {"operation": "top_categories", "records": []}},
        )

    @patch("agent.nodes.query_delivery_performance")
    @patch("agent.nodes.query_monthly_orders")
    @patch("agent.nodes.query_data")
    def test_successful_result_survives_another_tool_failure(
        self, query_data, query_monthly_orders, query_delivery_performance
    ) -> None:
        query_data.side_effect = RuntimeError("synthetic data-tool failure")
        successful_trend = {
            "operation": "monthly_orders",
            "records": [{"month": "2017-01", "order_count": 4}],
        }
        query_monthly_orders.return_value = successful_trend

        updates = execute_tools_node(
            {
                "query": "compare product sales and monthly trends",
                "selected_tools": ["data_tool", "trend_tool"],
                "tool_inputs": {
                    "data_tool": {"operation": "top_products", "top_n": 5}
                },
            }
        )

        self.assertIn("synthetic data-tool failure", updates["tool_results"]["data_tool"]["error"])
        self.assertEqual(updates["tool_results"]["trend_tool"], successful_trend)
        self.assertIn("data_tool", updates["error"])
        query_delivery_performance.assert_not_called()


class SynthesizeNodeTests(unittest.TestCase):
    def test_empty_monthly_records_return_no_results_message(self) -> None:
        updates = synthesize_node(
            {
                "query": "Show monthly order trends",
                "selected_tools": ["trend_tool"],
                "tool_results": {
                    "trend_tool": {
                        "operation": "monthly_orders",
                        "records": [],
                    }
                },
            }
        )

        self.assertIn("No monthly records were returned", updates["final_answer"])

    def test_empty_product_and_category_records_return_no_results_message(self) -> None:
        for operation in ("top_products", "top_categories"):
            with self.subTest(operation=operation):
                updates = synthesize_node(
                    {
                        "query": "Rank products or categories by item sales",
                        "selected_tools": ["data_tool"],
                        "tool_results": {
                            "data_tool": {"operation": operation, "records": []}
                        },
                    }
                )

                self.assertIn(
                    "No ranking records were returned", updates["final_answer"]
                )

    def test_monthly_summary_identifies_highest_returned_month(self) -> None:
        updates = synthesize_node(
            {
                "query": "Show monthly order trends",
                "selected_tools": ["trend_tool"],
                "tool_results": {
                    "trend_tool": {
                        "operation": "monthly_orders",
                        "metric": "Distinct order count by purchase month.",
                        "records": [
                            {"month": "2017-01", "order_count": 11},
                            {"month": "2017-02", "order_count": 19},
                            {"month": "2017-03", "order_count": 7},
                        ],
                    }
                },
            }
        )

        answer = updates["final_answer"]
        self.assertIn("2017-01: 11", answer)
        self.assertIn("2017-02: 19", answer)
        self.assertIn("Highest among the returned months: 2017-02 with 19 orders", answer)

    def test_delivery_summary_includes_denominators_and_undelivered_caveat(self) -> None:
        updates = synthesize_node(
            {
                "query": "What was delivery performance?",
                "selected_tools": ["delivery_tool"],
                "tool_results": {
                    "delivery_tool": {
                        "operation": "delivery_performance",
                        "metric_definitions": {},
                        "results": {
                            "total_distinct_orders": 12,
                            "delivered_orders_with_valid_purchase_and_delivery_timestamps": 8,
                            "average_delivery_duration_days": 4.25,
                            "delivered_orders_with_valid_actual_and_estimated_timestamps": 6,
                            "late_delivered_orders": 2,
                            "late_delivery_percentage": 33.33,
                        },
                    }
                },
            }
        )

        answer = updates["final_answer"]
        self.assertIn("across 8 delivered orders with valid purchase and actual delivery timestamps", answer)
        self.assertIn("2 of 6 eligible delivered orders (33.33%)", answer)
        self.assertIn("Undelivered orders are not classified as late", answer)


class RunQueryTests(unittest.TestCase):
    @patch("agent.nodes.query_delivery_performance")
    @patch("agent.nodes.query_monthly_orders")
    @patch("agent.nodes.query_data")
    def test_unclear_question_returns_final_answer_without_tools(
        self, query_data, query_monthly_orders, query_delivery_performance
    ) -> None:
        result = run_query("Tell me something interesting")

        self.assertEqual(result["selected_tools"], [])
        self.assertTrue(result["error"])
        self.assertTrue(result["final_answer"])
        query_data.assert_not_called()
        query_monthly_orders.assert_not_called()
        query_delivery_performance.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Delivery-time and lateness metrics for the Olist orders dataset."""

from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_FILE = PROJECT_ROOT / "data" / "olist" / "olist_orders_dataset.csv"
DATETIME_COLUMNS = [
    "order_purchase_timestamp",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def query_delivery_performance() -> dict[str, Any]:
    """Calculate delivery duration and lateness from the Olist orders CSV."""
    columns = ["order_id", "order_status", *DATETIME_COLUMNS]
    orders = pd.read_csv(ORDERS_FILE, usecols=columns)

    # Coercion converts missing or malformed timestamp strings to NaT so they
    # can be excluded from the relevant calculations safely.
    for column in DATETIME_COLUMNS:
        orders[column] = pd.to_datetime(orders[column], errors="coerce")

    # The file represents one row per order. Keep one row per non-missing ID so
    # that every reported order count and average is based on distinct orders.
    orders = orders.dropna(subset=["order_id"]).drop_duplicates(
        subset=["order_id"], keep="first"
    )
    delivered = orders[orders["order_status"] == "delivered"]

    valid_duration = delivered.dropna(
        subset=["order_purchase_timestamp", "order_delivered_customer_date"]
    )
    delivery_days = (
        valid_duration["order_delivered_customer_date"]
        - valid_duration["order_purchase_timestamp"]
    ).dt.total_seconds() / (24 * 60 * 60)

    valid_lateness = delivered.dropna(
        subset=["order_delivered_customer_date", "order_estimated_delivery_date"]
    )
    late_mask = (
        valid_lateness["order_delivered_customer_date"]
        > valid_lateness["order_estimated_delivery_date"]
    )
    late_order_count = int(late_mask.sum())
    lateness_denominator = len(valid_lateness)

    results = {
        "total_distinct_orders": int(orders["order_id"].nunique()),
        "delivered_orders_with_valid_purchase_and_delivery_timestamps": int(
            len(valid_duration)
        ),
        "average_delivery_duration_days": (
            round(float(delivery_days.mean()), 2) if len(delivery_days) else None
        ),
        "delivered_orders_with_valid_actual_and_estimated_timestamps": int(
            lateness_denominator
        ),
        "late_delivered_orders": late_order_count,
        "late_delivery_percentage": (
            round(late_order_count / lateness_denominator * 100, 2)
            if lateness_denominator
            else None
        ),
    }

    return {
        "operation": "delivery_performance",
        "metric_definitions": {
            "total_distinct_orders": (
                "Distinct non-missing order_id values across all statuses."
            ),
            "delivered_orders_with_valid_purchase_and_delivery_timestamps": (
                "Distinct delivered orders with both a valid purchase timestamp "
                "and a valid actual customer-delivery timestamp. This is the "
                "denominator for average delivery duration."
            ),
            "average_delivery_duration_days": (
                "Mean of actual customer-delivery timestamp minus purchase "
                "timestamp, in elapsed days; only delivered orders with both "
                "timestamps valid are included."
            ),
            "delivered_orders_with_valid_actual_and_estimated_timestamps": (
                "Denominator for lateness: delivered orders with both valid "
                "actual customer-delivery and estimated-delivery timestamps."
            ),
            "late_delivered_orders": (
                "Among the lateness denominator, orders with actual delivery "
                "timestamp strictly later than the estimated delivery timestamp. "
                "Arrival exactly at the estimate is on time."
            ),
            "late_delivery_percentage": (
                "Late delivered orders divided by delivered orders with valid "
                "actual and estimated delivery timestamps, multiplied by 100."
            ),
        },
        "results": results,
    }


def main() -> None:
    """Print a readable summary when this module is run directly."""
    result = query_delivery_performance()
    print(f"Operation: {result['operation']}")
    print("Metric definitions:")
    for name, definition in result["metric_definitions"].items():
        print(f"  {name}: {definition}")
    print("Results:")
    for name, value in result["results"].items():
        print(f"  {name}: {value}")


if __name__ == "__main__":
    main()

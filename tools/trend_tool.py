"""Monthly order-volume analysis for the Olist dataset."""

from pathlib import Path
import re
from typing import Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_FILE = PROJECT_ROOT / "data" / "olist" / "olist_orders_dataset.csv"
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _parse_month(value: Optional[str], parameter_name: str) -> Optional[pd.Period]:
    """Validate YYYY-MM input and return its calendar-month period."""
    if value is None:
        return None
    if not isinstance(value, str) or not MONTH_PATTERN.fullmatch(value):
        raise ValueError(f"{parameter_name} must be in YYYY-MM format")
    return pd.Period(value, freq="M")


def query_monthly_orders(
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
) -> dict:
    """Count distinct orders by purchase month, optionally within an inclusive range.

    All order statuses are included, including canceled and unavailable orders.
    Rows with an invalid/missing purchase timestamp or missing order_id are skipped.
    """
    start_period = _parse_month(start_month, "start_month")
    end_period = _parse_month(end_month, "end_month")
    if start_period is not None and end_period is not None and start_period > end_period:
        raise ValueError("start_month must be on or before end_month")

    # Read only the fields needed, then coerce bad timestamp values to NaT.
    orders = pd.read_csv(
        ORDERS_FILE,
        usecols=["order_id", "order_purchase_timestamp"],
    )
    orders["order_purchase_timestamp"] = pd.to_datetime(
        orders["order_purchase_timestamp"], errors="coerce"
    )
    orders = orders.dropna(subset=["order_id", "order_purchase_timestamp"])
    orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M")

    monthly_counts = orders.groupby("month")["order_id"].nunique().sort_index()
    if start_period is not None:
        monthly_counts = monthly_counts[monthly_counts.index >= start_period]
    if end_period is not None:
        monthly_counts = monthly_counts[monthly_counts.index <= end_period]

    records = [
        {"month": str(month), "order_count": int(count)}
        for month, count in monthly_counts.items()
    ]
    return {
        "operation": "monthly_orders",
        "metric": (
            "Distinct order_id count by calendar month of order_purchase_timestamp. "
            "All order statuses are included, including canceled and unavailable; "
            "rows with invalid/missing timestamps or missing order_id are omitted."
        ),
        "records": records,
    }


def main() -> None:
    """Print the first five months as a runnable example."""
    result = query_monthly_orders()
    print(f"Operation: {result['operation']}")
    print(f"Metric: {result['metric']}")
    print("First five monthly records:")
    for record in result["records"][:5]:
        print(f"  {record['month']}: {record['order_count']:,} orders")


if __name__ == "__main__":
    main()

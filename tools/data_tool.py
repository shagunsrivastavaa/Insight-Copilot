"""Reusable Pandas tools for exploring the Olist order-items dataset."""

from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "olist"
ORDER_ITEMS_FILE = DATA_DIR / "olist_order_items_dataset.csv"
PRODUCTS_FILE = DATA_DIR / "olist_products_dataset.csv"
CATEGORY_TRANSLATION_FILE = DATA_DIR / "product_category_name_translation.csv"


def query_data(operation: str, top_n: int = 10) -> dict[str, Any]:
    """Return a top-N ranking for item sales by category or product.

    Supported operations are ``top_categories`` and ``top_products``.
    Item sales value is the sum of ``price`` from order items; freight is excluded.
    """
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")

    if operation not in {"top_categories", "top_products"}:
        raise ValueError(
            "operation must be 'top_categories' or 'top_products'"
        )

    # These paths are anchored to this module's project root, not the shell's
    # current directory, so the function works when called from another folder.
    order_items = pd.read_csv(ORDER_ITEMS_FILE)
    products = pd.read_csv(PRODUCTS_FILE, usecols=["product_id", "product_category_name"])
    translations = pd.read_csv(CATEGORY_TRANSLATION_FILE)

    # Left joins keep every order item, even if its product or category is missing.
    items_with_category = order_items.merge(
        products,
        on="product_id",
        how="left",
    ).merge(
        translations,
        on="product_category_name",
        how="left",
    )

    # Use the English name when present, then the source name, then a safe label.
    source_category = items_with_category["product_category_name"].replace(
        r"^\s*$", pd.NA, regex=True
    )
    english_category = items_with_category[
        "product_category_name_english"
    ].replace(r"^\s*$", pd.NA, regex=True)
    items_with_category["category"] = (
        english_category.fillna(source_category).fillna("Uncategorized")
    )
    items_with_category["product_id"] = items_with_category["product_id"].fillna(
        "unknown_product"
    )

    # Convert malformed or missing prices to NA; Pandas excludes them from sums.
    items_with_category["price"] = pd.to_numeric(
        items_with_category["price"], errors="coerce"
    )

    if operation == "top_categories":
        ranking = (
            items_with_category.groupby("category", as_index=False)["price"]
            .sum(min_count=1)
            .rename(columns={"price": "item_sales_value"})
            .dropna(subset=["item_sales_value"])
            .sort_values("item_sales_value", ascending=False)
            .head(top_n)
        )
        records = ranking.to_dict(orient="records")
        metric = (
            "Sum of order item price grouped by English product category; "
            "freight_value is excluded. Missing category names are labeled "
            "'Uncategorized'."
        )
    else:
        ranking = (
            items_with_category.groupby("product_id", as_index=False)
            .agg(category=("category", "first"), item_sales_value=("price", "sum"))
            .sort_values("item_sales_value", ascending=False)
            .head(top_n)
        )
        records = ranking.to_dict(orient="records")
        metric = (
            "Sum of order item price grouped by product_id; freight_value is "
            "excluded. Products without a category are labeled 'Uncategorized', "
            "and missing product IDs are labeled 'unknown_product'."
        )

    return {
        "operation": operation,
        "metric": metric,
        "records": records,
    }


def main() -> None:
    """Run a small example when this file is executed directly."""
    result = query_data("top_categories", top_n=5)
    print(f"Operation: {result['operation']}")
    print(f"Metric: {result['metric']}")
    print("Results:")
    print(pd.DataFrame(result["records"]).to_string(index=False))


if __name__ == "__main__":
    main()

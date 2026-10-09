"""Inspect the expected Olist CSV files without loading large files at once."""

from pathlib import Path
import sqlite3
import tempfile

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "olist"
CHUNK_SIZE = 50_000
EXPECTED_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]


def inspect_csv(filename: str) -> None:
    """Print a summary for one CSV, reading it in manageable chunks."""
    path = DATA_DIR / filename

    try:
        if not path.is_file():
            print(f"\n{filename}: MISSING (expected at {path})")
            return

        print(f"\n{'=' * 78}\nFile: {filename}\nSize: {path.stat().st_size:,} bytes")

        # Read only the header first so empty-but-valid CSVs still report columns.
        columns = pd.read_csv(path, nrows=0, dtype=str).columns.tolist()
        missing_counts = pd.Series(0, index=columns, dtype="int64")
        first_rows = []
        row_count = 0

        # SQLite stores compact row fingerprints on disk, avoiding retention of
        # all rows in memory while counting duplicates across chunk boundaries.
        with tempfile.TemporaryDirectory(prefix="olist_inspection_") as temp_dir:
            database_path = Path(temp_dir) / "row_fingerprints.sqlite"
            connection = sqlite3.connect(database_path)
            cursor = None
            try:
                cursor = connection.cursor()
                cursor.execute("CREATE TABLE fingerprints (value TEXT PRIMARY KEY)")

                for chunk in pd.read_csv(path, chunksize=CHUNK_SIZE, dtype=str):
                    row_count += len(chunk)

                    if len(first_rows) < 3:
                        remaining = 3 - sum(len(frame) for frame in first_rows)
                        first_rows.append(chunk.head(remaining))

                    missing_counts = missing_counts.add(
                        chunk.isna().sum(), fill_value=0
                    ).astype("int64")

                    fingerprints = pd.util.hash_pandas_object(
                        chunk, index=False, categorize=True
                    )
                    cursor.executemany(
                        "INSERT OR IGNORE INTO fingerprints(value) VALUES (?)",
                        ((f"{int(value):016x}",) for value in fingerprints),
                    )

                cursor.execute("SELECT COUNT(*) FROM fingerprints")
                unique_count = cursor.fetchone()[0]
            finally:
                # SQLite's connection context manager does not close its handles.
                # Close both before TemporaryDirectory deletes the database;
                # Windows otherwise keeps the open file locked.
                try:
                    if cursor is not None:
                        cursor.close()
                finally:
                    connection.close()

        print(f"Rows: {row_count:,}")
        print("Columns:")
        for column in columns:
            print(f"  - {column}")

        print("First three rows:")
        if first_rows and row_count:
            print(pd.concat(first_rows, ignore_index=True).to_string(index=False))
        else:
            print("  (no data rows)")

        print("Missing values by column:")
        if columns:
            for column, count in missing_counts.items():
                print(f"  - {column}: {int(count):,}")
        else:
            print("  (no columns)")

        print(f"Duplicate rows: {row_count - unique_count:,}")
        print("  (count is extra copies after the first occurrence)")

    except Exception as exc:
        # Keep one problematic file from preventing reports on the remaining files.
        print(f"Could not inspect {filename}: {type(exc).__name__}: {exc}")

def main() -> None:
    print(f"Olist data folder: {DATA_DIR}")
    missing_files = [name for name in EXPECTED_FILES if not (DATA_DIR / name).is_file()]
    if missing_files:
        print("Missing expected CSV files:")
        for name in missing_files:
            print(f"  - {name}")
    else:
        print("All nine expected CSV files are present.")

    for filename in EXPECTED_FILES:
        inspect_csv(filename)


if __name__ == "__main__":
    main()



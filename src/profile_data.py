
from pathlib import Path
import pandas as pd

# Locate the project and its data folders
PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
REPORT_FILE = PROJECT_DIR / "data" / "processed" / "data_quality_report.txt"

# Expected schema for each dataset
EXPECTED_COLUMNS = {
    "customers": [
        "customer_id",
        "customer_name",
        "email",
        "city",
        "signup_date",
    ],
    "orders": [
        "order_id",
        "customer_id",
        "product_id",
        "order_date",
        "quantity",
        "unit_price",
        "payment_status",
    ],
    "products": [
        "product_id",
        "product_name",
        "category",
        "supplier_id",
        "cost_price",
        "selling_price",
    ],
    "clickstream": [
        "event_id",
        "customer_id",
        "event_type",
        "page_url",
        "event_timestamp",
        "device_type",
    ],
}


def add_line(report, text=""):
    """Add a line to the report."""
    report.append(str(text))


def main():
    datasets = {}
    report = []

    add_line(report, "QUICKCART - DATA QUALITY REPORT")
    add_line(report, "=" * 40)

    # 1. Read all CSV files and validate their schemas
    for dataset_name, expected_columns in EXPECTED_COLUMNS.items():
        file_path = RAW_DIR / f"{dataset_name}.csv"

        add_line(report, f"\nDATASET: {dataset_name}")
        add_line(report, "-" * 40)

        if not file_path.exists():
            add_line(report, f"ERROR: File not found: {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)
        except Exception as error:
            add_line(report, f"ERROR reading CSV: {error}")
            continue

        datasets[dataset_name] = df

        add_line(report, f"Rows: {len(df)}")
        add_line(report, f"Columns: {len(df.columns)}")
        add_line(report, f"Exact duplicate rows: {df.duplicated().sum()}")

        missing_columns = [
            column
            for column in expected_columns
            if column not in df.columns
        ]

        unexpected_columns = [
            column
            for column in df.columns
            if column not in expected_columns
        ]

        add_line(report, f"Missing expected columns: {missing_columns}")
        add_line(report, f"Unexpected columns: {unexpected_columns}")

        add_line(report, "\nColumn details:")
        add_line(
            report,
            df.dtypes.to_string()
        )

        missing_values = df.isna().sum()
        add_line(report, "\nMissing values by column:")
        add_line(report, missing_values.to_string())

        add_line(report, "\n")

    # 2. Check duplicate customer IDs and emails
    if "customers" in datasets:
        customers = datasets["customers"]

        add_line(report, "\nCUSTOMER QUALITY CHECKS")
        add_line(report, "-" * 40)

        if "customer_id" in customers.columns:
            duplicate_ids = customers["customer_id"].duplicated().sum()
            add_line(report, f"Repeated customer IDs: {duplicate_ids}")

        if "email" in customers.columns:
            normalized_emails = (
                customers["email"]
                .astype("string")
                .str.strip()
                .str.lower()
            )
            duplicate_emails = normalized_emails.duplicated().sum()
            add_line(report, f"Repeated emails after normalization: {duplicate_emails}")

    # 3. Check order IDs, quantities, prices and references
    if "orders" in datasets:
        orders = datasets["orders"]

        add_line(report, "\nORDER QUALITY CHECKS")
        add_line(report, "-" * 40)

        if "order_id" in orders.columns:
            add_line(
                report,
                f"Repeated order IDs: {orders['order_id'].duplicated().sum()}"
            )

        for column in ["quantity", "unit_price"]:
            if column in orders.columns:
                numeric_values = pd.to_numeric(
                    orders[column], errors="coerce"
                )
                invalid = numeric_values.isna() | (numeric_values <= 0)
                add_line(
                    report,
                    f"Invalid or non-positive {column}: {invalid.sum()}"
                )

        if "order_date" in orders.columns:
            parsed_dates = pd.to_datetime(
                orders["order_date"], errors="coerce", format="mixed"
            )
            add_line(
                report,
                f"Unparseable order dates: {parsed_dates.isna().sum()}"
            )

        if "customers" in datasets and "customer_id" in orders.columns:
            known_customers = set(
                datasets["customers"]["customer_id"].dropna().astype(str)
            )
            order_customers = orders["customer_id"].dropna().astype(str)
            unmatched = ~order_customers.isin(known_customers)
            add_line(
                report,
                f"Orders with unmatched customer IDs: {unmatched.sum()}"
            )

        if "products" in datasets and "product_id" in orders.columns:
            known_products = set(
                datasets["products"]["product_id"].dropna().astype(str)
            )
            order_products = orders["product_id"].dropna().astype(str)
            unmatched = ~order_products.isin(known_products)
            add_line(
                report,
                f"Orders with unmatched product IDs: {unmatched.sum()}"
            )

    # 4. Check product prices
    if "products" in datasets:
        products = datasets["products"]

        add_line(report, "\nPRODUCT QUALITY CHECKS")
        add_line(report, "-" * 40)

        if "product_id" in products.columns:
            add_line(
                report,
                f"Repeated product IDs: {products['product_id'].duplicated().sum()}"
            )

        if {"cost_price", "selling_price"}.issubset(products.columns):
            cost = pd.to_numeric(products["cost_price"], errors="coerce")
            selling = pd.to_numeric(products["selling_price"], errors="coerce")

            invalid_prices = (
                cost.isna()
                | selling.isna()
                | (cost < 0)
                | (selling < 0)
            )

            add_line(report, f"Invalid product prices: {invalid_prices.sum()}")
            add_line(
                report,
                f"Selling price below cost: {(selling < cost).sum()}"
            )

    # 5. Check clickstream events
    if "clickstream" in datasets:
        clickstream = datasets["clickstream"]

        add_line(report, "\nCLICKSTREAM QUALITY CHECKS")
        add_line(report, "-" * 40)

        if "event_id" in clickstream.columns:
            add_line(
                report,
                f"Repeated event IDs: {clickstream['event_id'].duplicated().sum()}"
            )

        if "event_timestamp" in clickstream.columns:
            timestamps = pd.to_datetime(
                clickstream["event_timestamp"],
                errors="coerce",
                format="mixed",
                utc=True
            )
            add_line(
                report,
                f"Missing or unparseable timestamps: {timestamps.isna().sum()}"
            )

        for column in ["event_type", "device_type", "city"]:
            if column in clickstream.columns:
                values = clickstream[column].dropna().astype(str)
                normalized = values.str.strip().str.lower()
                add_line(
                    report,
                    f"{column}: {values.nunique()} original values, "
                    f"{normalized.nunique()} after normalization"
                )

        if "customers" in datasets and "customer_id" in clickstream.columns:
            known_customers = set(
                datasets["customers"]["customer_id"]
                .dropna()
                .astype(str)
            )
            event_customers = (
                clickstream["customer_id"]
                .dropna()
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
            )
            normalized_customers = {
                value.removesuffix(".0") for value in known_customers
            }
            unmatched = ~event_customers.isin(normalized_customers)
            add_line(
                report,
                f"Events with unmatched customer IDs: {unmatched.sum()}"
            )

    # 6. Save the report without changing the input datasets
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("Data profiling completed.")
    print(f"Datasets loaded: {len(datasets)} of {len(EXPECTED_COLUMNS)}")
    print(f"Report saved to: {REPORT_FILE}")
    print("\n" + "\n".join(report))


if __name__ == "__main__":
    main()

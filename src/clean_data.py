
from pathlib import Path
from datetime import date
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"

AS_OF_DATE = pd.Timestamp(date.today())

def add_reasons(index, rules):
    """Combine all validation reasons for each row."""
    reasons = pd.Series("", index=index, dtype="string")

    for mask, reason in rules:
        mask = pd.Series(mask, index=index).fillna(False).astype(bool)

        for row_index in index[mask]:
            existing = reasons.at[row_index]
            reasons.at[row_index] = (
                f"{existing}; {reason}" if existing else reason
            )

    return reasons


def save_split(name, df, reasons):
    """Save accepted rows and quarantine rejected rows separately."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rejected_mask = reasons.ne("")
    clean = df.loc[~rejected_mask].copy()
    rejected = df.loc[rejected_mask].copy()

    clean_path = OUTPUT_DIR / f"{name}_clean.csv"
    clean.to_csv(clean_path, index=False)

    if not rejected.empty:
        rejected["quarantine_reason"] = reasons.loc[rejected_mask]
        rejected_path = OUTPUT_DIR / f"{name}_quarantine.csv"
        rejected.to_csv(rejected_path, index=False)
    else:
        rejected_path = None

    print(
        f"{name}: {len(clean)} accepted, "
        f"{len(rejected)} quarantined"
    )
    print(f"  Clean output: {clean_path}")

    if rejected_path:
        print(f"  Quarantine:   {rejected_path}")
        print("  Reasons:")
        print(
            rejected["quarantine_reason"]
            .value_counts()
            .to_string()
        )

    return clean


def normalize_text(series):
    """Trim strings and convert empty strings to missing values."""
    values = series.astype("string").str.strip()
    return values.mask(values.eq(""))


def main():
    # 1. CUSTOMERS
    customers = pd.read_csv(RAW_DIR / "customers.csv")

    customers["email"] = (
        normalize_text(customers["email"]).str.lower()
    )
    customers["city"] = normalize_text(
        customers["city"]
    ).str.title()
    customers["customer_name"] = normalize_text(
        customers["customer_name"]
    )

    signup_date = pd.to_datetime(
        customers["signup_date"], errors="coerce"
    )
    customers["signup_date"] = signup_date.dt.strftime("%Y-%m-%d")

    customer_reasons = add_reasons(
        customers.index,
        [
            (customers["customer_id"].isna(), "missing_customer_id"),
            (
                customers["customer_id"].duplicated(keep=False),
                "duplicate_customer_id",
            ),
            (customers["email"].isna(), "missing_email"),
            (
                customers["email"].duplicated(keep=False),
                "duplicate_email",
            ),
            (customers["customer_name"].isna(), "missing_customer_name"),
            (signup_date.isna(), "invalid_signup_date"),
        ],
    )

    clean_customers = save_split(
        "customers", customers, customer_reasons
    )
    valid_customer_ids = set(clean_customers["customer_id"].dropna())

    # 2. PRODUCTS
    products = pd.read_csv(RAW_DIR / "products.csv")

    for column in ["product_name", "category"]:
        products[column] = normalize_text(products[column])

    for column in ["cost_price", "selling_price"]:
        products[column] = pd.to_numeric(
            products[column], errors="coerce"
        )

    product_reasons = add_reasons(
        products.index,
        [
            (products["product_id"].isna(), "missing_product_id"),
            (
                products["product_id"].duplicated(keep=False),
                "duplicate_product_id",
            ),
            (products["product_name"].isna(), "missing_product_name"),
            (products["category"].isna(), "missing_category"),
            (
                products["cost_price"].isna()
                | products["selling_price"].isna(),
                "invalid_price",
            ),
            (
                (products["cost_price"] < 0)
                | (products["selling_price"] < 0),
                "negative_price",
            ),
        ],
    )

    clean_products = save_split(
        "products", products, product_reasons
    )
    valid_product_ids = set(clean_products["product_id"].dropna())

    # 3. ORDERS
    orders = pd.read_csv(RAW_DIR / "orders.csv")

    order_date = pd.to_datetime(
        orders["order_date"], errors="coerce"
    )
    orders["order_date"] = order_date.dt.strftime("%Y-%m-%d")

    orders["quantity"] = pd.to_numeric(
        orders["quantity"], errors="coerce"
    )
    orders["unit_price"] = pd.to_numeric(
        orders["unit_price"], errors="coerce"
    )
    orders["payment_status"] = (
        normalize_text(orders["payment_status"]).str.lower()
    )

    future_order = order_date.dt.normalize() > AS_OF_DATE

    unknown_customer = (
        orders["customer_id"].notna()
        & ~orders["customer_id"].isin(valid_customer_ids)
    )
    unknown_product = (
        orders["product_id"].notna()
        & ~orders["product_id"].isin(valid_product_ids)
    )

    order_reasons = add_reasons(
        orders.index,
        [
            (orders["order_id"].isna(), "missing_order_id"),
            (
                orders["order_id"].duplicated(keep=False),
                "duplicate_order_id",
            ),
            (order_date.isna(), "invalid_order_date"),
            (future_order, "future_order_date"),
            (
                orders["quantity"].isna() | (orders["quantity"] <= 0),
                "invalid_quantity",
            ),
            (
                orders["unit_price"].isna() | (orders["unit_price"] <= 0),
                "invalid_unit_price",
            ),
            (unknown_customer, "unknown_customer_id"),
            (unknown_product, "unknown_product_id"),
            (orders["payment_status"].isna(), "missing_payment_status"),
        ],
    )

    save_split("orders", orders, order_reasons)

    # 4. CLICKSTREAM
    clickstream = pd.read_csv(RAW_DIR / "clickstream.csv")

    clickstream["event_id"] = pd.to_numeric(
        clickstream["event_id"], errors="coerce"
    ).astype("Int64")

    clickstream["customer_id"] = pd.to_numeric(
        clickstream["customer_id"], errors="coerce"
    ).astype("Int64")

    for column in ["event_type", "page_url", "device_type"]:
        clickstream[column] = normalize_text(clickstream[column])

    # Standardize event names and known spelling variants.
    event_type = (
        clickstream["event_type"]
        .str.lower()
        .str.replace(r"[\s-]+", "_", regex=True)
    )

    event_aliases = {
        "pageview": "page_view",
        "clik": "click",
        "serach": "search",
        "add_to_cart": "add_to_cart",
        "log_out": "logout",
        "logout": "logout",
    }
    clickstream["event_type"] = (
        event_type.replace(event_aliases)
    )

    # Standardize device types. Missing values remain identifiable.
    clickstream["device_type"] = (
        clickstream["device_type"].str.lower()
    )
    clickstream["device_type"] = clickstream["device_type"].fillna(
        "unknown"
    )

    valid_devices = {"mobile", "desktop", "tablet", "unknown"}
    clickstream.loc[
        ~clickstream["device_type"].isin(valid_devices),
        "device_type",
    ] = "unknown"

    # Mixed formats and timezone markers are normalized to UTC.
    event_timestamp = pd.to_datetime(
        clickstream["event_timestamp"],
        errors="coerce",
        format="mixed",
        dayfirst=True,
        utc=True,
    )
    clickstream["event_timestamp"] = (
        event_timestamp.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    unknown_event_customer = (
        clickstream["customer_id"].notna()
        & ~clickstream["customer_id"].isin(valid_customer_ids)
    )

    clickstream_reasons = add_reasons(
        clickstream.index,
        [
            (clickstream["event_id"].isna(), "missing_event_id"),
            (
                clickstream["event_id"].duplicated(keep=False),
                "event_id_collision",
            ),
            (
                event_timestamp.isna(),
                "invalid_event_timestamp",
            ),
            (
                unknown_event_customer,
                "unknown_customer_id",
            ),
        ],
    )

    # Missing customer IDs can represent anonymous events.
    # Missing page URLs are retained as missing instead of invented.
    save_split(
        "clickstream", clickstream, clickstream_reasons
    )

    print("\nCleaning completed.")
    print(f"Order dates checked against: {AS_OF_DATE.date()}")
    print(f"Original files remain unchanged in: {RAW_DIR}")


if __name__ == "__main__":
    main()

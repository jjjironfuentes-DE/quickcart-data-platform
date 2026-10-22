
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"


def main():
    clickstream = pd.read_csv(RAW_DIR / "clickstream.csv")
    orders = pd.read_csv(RAW_DIR / "orders.csv")

    # 1. Investigate repeated event IDs
    duplicate_mask = clickstream["event_id"].duplicated(keep=False)
    duplicates = clickstream.loc[duplicate_mask].sort_values("event_id")

    print("\n=== CLICKSTREAM: REPEATED EVENT IDs ===")
    print(f"Rows involved in repeated IDs: {len(duplicates)}")
    print(
        "Distinct repeated IDs:",
        duplicates["event_id"].nunique()
    )

    if not duplicates.empty:
        print("\nSample of repeated IDs:")
        columns = [
            "event_id",
            "customer_id",
            "event_type",
            "page_url",
            "event_timestamp",
            "device_type",
        ]
        print(duplicates[columns].head(20).to_string(index=False))

    # 2. Investigate missing clickstream values
    print("\n=== CLICKSTREAM: MISSING VALUES ===")
    for column in ["customer_id", "page_url", "device_type"]:
        missing = clickstream[column].isna().sum()
        percentage = missing / len(clickstream) * 100
        print(f"{column}: {missing} missing ({percentage:.2f}%)")

    # 3. Compare raw and normalized event types/devices
    print("\n=== EVENT TYPE VARIANTS ===")
    event_types = clickstream["event_type"].dropna().astype("string")
    event_types = event_types.str.strip()
    print("Original variants:", event_types.nunique())
    print(
        "After lowercase/trim:",
        event_types.str.lower().nunique()
    )
    print("Values:", sorted(event_types.unique().tolist()))

    print("\n=== DEVICE TYPE VARIANTS ===")
    devices = clickstream["device_type"].dropna().astype("string")
    devices = devices.str.strip()
    print("Original variants:", devices.nunique())
    print("After lowercase/trim:", devices.str.lower().nunique())
    print("Values:", sorted(devices.unique().tolist()))

    # 4. Check order date range and future dates
    print("\n=== ORDER DATE CHECK ===")
    parsed_dates = pd.to_datetime(
        orders["order_date"],
        errors="coerce",
        format="mixed",
    )

    today = pd.Timestamp.now().normalize().tz_localize(None)
    future_mask = parsed_dates > today

    print("Earliest order date:", parsed_dates.min())
    print("Latest order date:", parsed_dates.max())
    print("Rows with future order dates:", int(future_mask.sum()))

    if future_mask.any():
        print(
            orders.loc[future_mask, ["order_id", "order_date"]]
            .head(15)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()

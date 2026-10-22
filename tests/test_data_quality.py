from datetime import date
from pathlib import Path

import pandas as pd
import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

DATASETS = ["customers", "products", "orders", "clickstream"]


def read_csv(path: Path) -> pd.DataFrame:
    assert path.is_file(), f"Missing file: {path}"
    return pd.read_csv(path)


def read_clean(name: str) -> pd.DataFrame:
    return read_csv(PROCESSED_DIR / f"{name}_clean.csv")


def read_quarantine(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}_quarantine.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@pytest.mark.parametrize("name", DATASETS)
def test_raw_and_clean_files_exist_and_are_not_empty(name):
    raw = read_csv(RAW_DIR / f"{name}.csv")
    clean = read_clean(name)

    assert not raw.empty
    assert not clean.empty


@pytest.mark.parametrize("name", DATASETS)
def test_every_source_row_is_clean_or_quarantined(name):
    raw = read_csv(RAW_DIR / f"{name}.csv")
    clean = read_clean(name)
    quarantine = read_quarantine(name)

    assert len(raw) == len(clean) + len(quarantine)


def test_customer_ids_are_present_and_unique():
    customers = read_clean("customers")

    assert customers["customer_id"].notna().all()
    assert customers["customer_id"].is_unique
    assert customers["customer_name"].notna().all()
    assert customers["email"].notna().all()
    assert customers["email"].is_unique
    assert pd.to_datetime(
        customers["signup_date"], errors="coerce"
    ).notna().all()


def test_product_ids_and_prices_are_valid():
    products = read_clean("products")

    assert products["product_id"].notna().all()
    assert products["product_id"].is_unique

    for column in ["cost_price", "selling_price"]:
        prices = pd.to_numeric(products[column], errors="coerce")
        assert prices.notna().all()
        assert (prices >= 0).all()


def test_orders_have_valid_values_and_references():
    orders = read_clean("orders")
    customers = read_clean("customers")
    products = read_clean("products")

    assert orders["order_id"].notna().all()
    assert orders["order_id"].is_unique
    assert orders["customer_id"].notna().all()
    assert orders["product_id"].notna().all()

    quantities = pd.to_numeric(orders["quantity"], errors="coerce")
    prices = pd.to_numeric(orders["unit_price"], errors="coerce")
    dates = pd.to_datetime(orders["order_date"], errors="coerce")

    assert quantities.notna().all()
    assert (quantities > 0).all()
    assert prices.notna().all()
    assert (prices > 0).all()
    assert dates.notna().all()
    assert (dates.dt.date <= date.today()).all()

    customer_ids = set(customers["customer_id"].dropna())
    product_ids = set(products["product_id"].dropna())

    assert orders["customer_id"].isin(customer_ids).all()
    assert orders["product_id"].isin(product_ids).all()


def test_clickstream_events_are_valid_and_normalised():
    events = read_clean("clickstream")
    customers = read_clean("customers")

    assert events["event_id"].notna().all()
    assert events["event_id"].is_unique
    assert events["event_type"].notna().all()
    assert events["event_timestamp"].notna().all()

    timestamps = pd.to_datetime(
        events["event_timestamp"], errors="coerce", utc=True
    )
    assert timestamps.notna().all()

    event_types = events["event_type"].astype(str)
    assert event_types.eq(event_types.str.lower()).all()
    assert event_types.eq(
        event_types.str.replace(r"[\s-]+", "_", regex=True)
    ).all()

    valid_devices = {"mobile", "desktop", "tablet", "unknown"}
    assert set(events["device_type"].dropna()).issubset(valid_devices)

    known_customer_ids = set(customers["customer_id"].dropna())
    identified_events = events["customer_id"].dropna()
    assert identified_events.isin(known_customer_ids).all()


@pytest.mark.parametrize("name", DATASETS)
def test_quarantine_reasons_are_recorded(name):
    quarantine = read_quarantine(name)

    if quarantine.empty:
        return

    assert "quarantine_reason" in quarantine.columns
    reasons = quarantine["quarantine_reason"].astype("string")
    assert reasons.notna().all()
    assert reasons.str.strip().ne("").all()

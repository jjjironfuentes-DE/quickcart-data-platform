from __future__ import annotations

import csv
import logging
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.sensors.python import PythonSensor
from airflow.providers.postgres.hooks.postgres import PostgresHook


PROJECT_DIR = Path("/opt/airflow/quickcart")
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
SRC_DIR = PROJECT_DIR / "src"

POSTGRES_CONN_ID = "quickcart_postgres"

EXPECTED_COLUMNS = {
    "customers.csv": [
        "customer_id", "customer_name", "email", "city", "signup_date"
    ],
    "orders.csv": [
        "order_id", "customer_id", "product_id", "order_date",
        "quantity", "unit_price", "payment_status"
    ],
    "products.csv": [
        "product_id", "product_name", "category", "supplier_id",
        "cost_price", "selling_price"
    ],
    "clickstream.csv": [
        "event_id", "customer_id", "event_type", "page_url",
        "event_timestamp", "device_type"
    ],
}


def file_exists(filename: str, **context) -> bool:
    """Sensor: comprueba que un CSV exista y no esté vacío."""
    path = RAW_DIR / filename
    exists = path.is_file() and path.stat().st_size > 0

    if exists:
        logging.info("Archivo disponible: %s", path)
    else:
        logging.info("Esperando archivo: %s", path)

    return exists


def validate_input_files(**context) -> None:
    """Valida los encabezados y comprueba que los CSV tengan filas."""
    for filename, expected_columns in EXPECTED_COLUMNS.items():
        path = RAW_DIR / filename

        if not path.is_file():
            raise FileNotFoundError(f"No existe el archivo: {path}")

        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            header = next(reader, None)
            row_count = sum(1 for _ in reader)

        if header != expected_columns:
            raise ValueError(
                f"Encabezado incorrecto en {filename}. "
                f"Esperado: {expected_columns}. Encontrado: {header}"
            )

        if row_count == 0:
            raise ValueError(f"El archivo no contiene filas: {filename}")

        logging.info(
            "Validación correcta: %s; filas=%s",
            filename,
            row_count,
        )


def clean_data(**context) -> None:
    """Ejecuta el script de limpieza que ya existe en src/."""
    script = SRC_DIR / "clean_data.py"

    if not script.is_file():
        raise FileNotFoundError(f"No existe el script: {script}")

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout:
        logging.info("Salida de limpieza:\n%s", result.stdout)

    if result.returncode != 0:
        logging.error("Error de limpieza:\n%s", result.stderr)
        raise RuntimeError(
            f"clean_data.py terminó con código {result.returncode}"
        )

    if result.stderr:
        logging.warning("Mensajes de limpieza:\n%s", result.stderr)

    expected_outputs = [
        "customers_clean.csv",
        "products_clean.csv",
        "orders_clean.csv",
        "clickstream_clean.csv",
    ]

    for filename in expected_outputs:
        path = PROCESSED_DIR / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(
                f"No se generó el archivo limpio esperado: {path}"
            )

    logging.info("Limpieza y comprobación de archivos terminadas.")


def load_staging(**context) -> None:
    """Carga los CSV originales a las tablas staging."""
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    conn = hook.get_conn()

    tables = [
        (
            "staging.stg_customers",
            "customers.csv",
            ["customer_id", "customer_name", "email", "city", "signup_date"],
        ),
        (
            "staging.stg_products",
            "products.csv",
            [
                "product_id", "product_name", "category", "supplier_id",
                "cost_price", "selling_price",
            ],
        ),
        (
            "staging.stg_orders",
            "orders.csv",
            [
                "order_id", "customer_id", "product_id", "order_date",
                "quantity", "unit_price", "payment_status",
            ],
        ),
        (
            "staging.stg_clickstream",
            "clickstream.csv",
            [
                "event_id", "customer_id", "event_type", "page_url",
                "event_timestamp", "device_type",
            ],
        ),
    ]

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE TABLE
                    staging.stg_clickstream,
                    staging.stg_orders,
                    staging.stg_products,
                    staging.stg_customers
                """
            )

            for table, filename, columns in tables:
                path = RAW_DIR / filename
                column_list = ", ".join(columns)
                copy_sql = (
                    f"COPY {table} ({column_list}) "
                    "FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
                )

                with path.open("r", encoding="utf-8-sig", newline="") as source:
                    cursor.copy_expert(copy_sql, source)

                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                logging.info("Carga staging: %s = %s filas", table, count)

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_core(**context) -> None:
    """Carga los CSV limpios a core mediante tablas temporales y upserts."""
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    conn = hook.get_conn()

    temporary_tables = [
        """
        CREATE TEMP TABLE load_customers (
            customer_id BIGINT PRIMARY KEY,
            customer_name TEXT,
            email TEXT,
            city TEXT,
            signup_date DATE
        ) ON COMMIT DROP
        """,
        """
        CREATE TEMP TABLE load_products (
            product_id BIGINT PRIMARY KEY,
            product_name TEXT,
            category TEXT,
            supplier_id BIGINT,
            cost_price NUMERIC(12, 2),
            selling_price NUMERIC(12, 2)
        ) ON COMMIT DROP
        """,
        """
        CREATE TEMP TABLE load_orders (
            order_id BIGINT PRIMARY KEY,
            customer_id BIGINT,
            product_id BIGINT,
            order_date DATE,
            quantity INTEGER,
            unit_price NUMERIC(12, 2),
            payment_status TEXT
        ) ON COMMIT DROP
        """,
        """
        CREATE TEMP TABLE load_clickstream (
            event_id BIGINT PRIMARY KEY,
            customer_id BIGINT,
            event_type TEXT,
            page_url TEXT,
            event_timestamp TIMESTAMPTZ,
            device_type TEXT
        ) ON COMMIT DROP
        """,
    ]

    clean_files = [
        (
            "load_customers",
            "customers_clean.csv",
            "customer_id, customer_name, email, city, signup_date",
        ),
        (
            "load_products",
            "products_clean.csv",
            "product_id, product_name, category, supplier_id, "
            "cost_price, selling_price",
        ),
        (
            "load_orders",
            "orders_clean.csv",
            "order_id, customer_id, product_id, order_date, quantity, "
            "unit_price, payment_status",
        ),
        (
            "load_clickstream",
            "clickstream_clean.csv",
            "event_id, customer_id, event_type, page_url, "
            "event_timestamp, device_type",
        ),
    ]

    upsert_statements = [
        """
        INSERT INTO core.customers (
            customer_id, customer_name, email, city, signup_date
        )
        SELECT customer_id, customer_name, email, city, signup_date
        FROM load_customers
        ON CONFLICT (customer_id) DO UPDATE SET
            customer_name = EXCLUDED.customer_name,
            email = EXCLUDED.email,
            city = EXCLUDED.city,
            signup_date = EXCLUDED.signup_date
        """,
        """
        INSERT INTO core.products (
            product_id, product_name, category,
            supplier_id, cost_price, selling_price
        )
        SELECT
            product_id, product_name, category,
            supplier_id, cost_price, selling_price
        FROM load_products
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = EXCLUDED.product_name,
            category = EXCLUDED.category,
            supplier_id = EXCLUDED.supplier_id,
            cost_price = EXCLUDED.cost_price,
            selling_price = EXCLUDED.selling_price
        """,
        """
        INSERT INTO core.orders (
            order_id, customer_id, product_id,
            order_date, quantity, unit_price, payment_status
        )
        SELECT
            order_id, customer_id, product_id,
            order_date, quantity, unit_price, payment_status
        FROM load_orders
        ON CONFLICT (order_id) DO UPDATE SET
            customer_id = EXCLUDED.customer_id,
            product_id = EXCLUDED.product_id,
            order_date = EXCLUDED.order_date,
            quantity = EXCLUDED.quantity,
            unit_price = EXCLUDED.unit_price,
            payment_status = EXCLUDED.payment_status
        """,
        """
        INSERT INTO core.clickstream_events (
            event_id, customer_id, event_type,
            page_url, event_timestamp, device_type
        )
        SELECT
            event_id, customer_id, event_type,
            page_url, event_timestamp, device_type
        FROM load_clickstream
        ON CONFLICT (event_id) DO UPDATE SET
            customer_id = EXCLUDED.customer_id,
            event_type = EXCLUDED.event_type,
            page_url = EXCLUDED.page_url,
            event_timestamp = EXCLUDED.event_timestamp,
            device_type = EXCLUDED.device_type
        """,
    ]

    try:
        with conn.cursor() as cursor:
            for statement in temporary_tables:
                cursor.execute(statement)

            for table, filename, columns in clean_files:
                path = PROCESSED_DIR / filename
                copy_sql = (
                    f"COPY {table} ({columns}) "
                    "FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
                )

                with path.open("r", encoding="utf-8-sig", newline="") as source:
                    cursor.copy_expert(copy_sql, source)

                logging.info("CSV limpio cargado en %s", table)

            for statement in upsert_statements:
                cursor.execute(statement)
                logging.info("Filas insertadas/actualizadas: %s", cursor.rowcount)

        conn.commit()
        logging.info("Carga de core completada correctamente.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_core(**context) -> None:
    """Comprueba que las tablas principales tengan datos."""
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)

    tables = [
        "core.customers",
        "core.products",
        "core.orders",
        "core.clickstream_events",
    ]

    conn = hook.get_conn()
    try:
        with conn.cursor() as cursor:
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                logging.info("Verificación: %s = %s filas", table, count)

                if count == 0:
                    raise ValueError(f"La tabla está vacía: {table}")
    finally:
        conn.close()


default_args = {
    "owner": "quickcart",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email": ["jjjironfuentes@gmail.com"],
    "email_on_failure": True,
    "email_on_retry": False,
}

with DAG(
    dag_id="quickcart_daily_pipeline",
    description="Ingesta, validación, limpieza y carga diaria de QuickCart",
    default_args=default_args,
    start_date=pendulum.datetime(2025, 1, 1, tz="Europe/Berlin"),
    schedule="0 2 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["quickcart", "etl", "postgres"],
) as dag:

    wait_for_customers = PythonSensor(
        task_id="wait_for_customers",
        python_callable=file_exists,
        op_kwargs={"filename": "customers.csv"},
        poke_interval=60,
        timeout=3600,
        mode="reschedule",
    )

    wait_for_orders = PythonSensor(
        task_id="wait_for_orders",
        python_callable=file_exists,
        op_kwargs={"filename": "orders.csv"},
        poke_interval=60,
        timeout=3600,
        mode="reschedule",
    )

    wait_for_products = PythonSensor(
        task_id="wait_for_products",
        python_callable=file_exists,
        op_kwargs={"filename": "products.csv"},
        poke_interval=60,
        timeout=3600,
        mode="reschedule",
    )

    wait_for_clickstream = PythonSensor(
        task_id="wait_for_clickstream",
        python_callable=file_exists,
        op_kwargs={"filename": "clickstream.csv"},
        poke_interval=60,
        timeout=3600,
        mode="reschedule",
    )

    validate_files = PythonOperator(
        task_id="validate_files",
        python_callable=validate_input_files,
    )

    clean_csv_data = PythonOperator(
        task_id="clean_csv_data",
        python_callable=clean_data,
    )

    load_raw_staging = PythonOperator(
        task_id="load_raw_staging",
        python_callable=load_staging,
    )

    load_core_tables = PythonOperator(
        task_id="load_core_tables",
        python_callable=load_core,
    )

    verify_core_tables = PythonOperator(
        task_id="verify_core_tables",
        python_callable=verify_core,
    )

    sensors = [
        wait_for_customers,
        wait_for_orders,
        wait_for_products,
        wait_for_clickstream,
    ]

    sensors >> validate_files >> load_raw_staging
    load_raw_staging >> clean_csv_data >> load_core_tables >> verify_core_tables

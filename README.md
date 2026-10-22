# QuickCart Data Platform

A data engineering project for ingesting, validating, cleaning, storing,
and analysing customer, product, order, and clickstream data.

## Objectives

- Profile source data and identify quality issues.
- Clean CSV files with Python and Pandas.
- Preserve original data and quarantine rejected records.
- Load data into PostgreSQL staging and core schemas.
- Answer business questions using SQL.
- Orchestrate the pipeline with Apache Airflow.

## Architecture

Source CSV files -> Python validation and cleaning
                 -> Clean files and quarantine files
                 -> PostgreSQL staging
                 -> PostgreSQL core
                 -> Business SQL and reporting

## Source datasets

Place these files in `data/raw/`:

- `customers.csv`
- `orders.csv`
- `products.csv`
- `clickstream.csv`

## Python setup

Create and activate a virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt

## Data profiling and cleaning

Run from the project directory:

    python src/profile_data.py
    python src/inspect_anomalies.py
    python src/clean_data.py

The cleaning script generates clean CSV files and quarantine files
under `data/processed/`. Original files remain unchanged.

## SQL

- `01_create_schema.sql`: creates staging, core, and operational tables.
- `02_load_staging.sql`: loads raw source data.
- `03_load_core.sql`: loads cleaned data into core.
- `04_business_queries.sql`: analytical business queries.
- `05_optimization.sql`: query plans and performance analysis.

Review SQL scripts before running them because staging is replaced and
core records can be inserted or updated.

## Airflow orchestration

The DAG ID is `quickcart_daily_pipeline`.

The DAG is configured to run daily at 02:00 in the `Europe/Berlin`
timezone. It waits for the four source files, validates their headers,
loads raw data into staging, cleans the CSV files, loads the cleaned
records into core tables, and verifies the final tables.

Tasks are configured with two retries and a two-minute retry delay.
Failure email notifications are configured, but successful email delivery
depends on valid SMTP settings in the Airflow environment.

The DAG runs in the existing Airflow installation in the sibling
`airflow-project` directory. Its configuration mounts the QuickCart
DAG, source code, data, and SQL files into the Airflow containers.

## Representative data quality results

A run on 22 October 2026 produced these results:

| Dataset | Accepted | Quarantined |
|---|---:|---:|
| Customers | 100 | 0 |
| Products | 10 | 0 |
| Orders | 316 | 184 |
| Clickstream | 1,927 | 73 |

The order-date rule rejects future-dated orders relative to the date
of processing. Clickstream rows with colliding event IDs are quarantined.
Counts can change when source files or processing dates change.

## Security and reproducibility

- Keep `.env` and credentials out of version control.
- Do not commit raw CSV files or generated reports by default.
- Preserve original source files during cleaning.
- Record quarantine reasons for rejected records.
- Review SQL scripts before rerunning them.
- Check Airflow task logs when investigating pipeline failures.

## Documentation

See [docs/theory.md](docs/theory.md) for explanations of OLTP and OLAP,
ACID and BASE, file formats, indexing, partitioning, and normalisation.

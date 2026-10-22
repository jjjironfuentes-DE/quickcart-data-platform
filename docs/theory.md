# QuickCart Data Engineering Concepts

## 1. OLTP versus OLAP

**OLTP (Online Transaction Processing)** supports operational transactions,
such as placing orders, updating inventory, and recording shipments.
It typically handles many small reads and writes and relies on keys,
constraints, and transactional consistency.

**OLAP (Online Analytical Processing)** supports analytical queries such
as revenue trends, customer rankings, and category performance. These
queries often aggregate or scan many rows.

In QuickCart, the core relational tables store customers, products,
orders, and clickstream events. The business SQL queries analyse this data.
As the dataset grows, analytical workloads could be moved to a dedicated
data warehouse.

## 2. ACID versus BASE

ACID describes four transaction properties:

- **Atomicity:** a transaction succeeds completely or is rolled back.
- **Consistency:** constraints and rules remain satisfied.
- **Isolation:** concurrent transactions are controlled to prevent
  invalid interference.
- **Durability:** committed changes persist.

QuickCart uses PostgreSQL transactions, primary keys, foreign keys, and
CHECK constraints to help protect data integrity.

BASE is an approach associated with many distributed systems:

- **Basically Available:** the system aims to remain available.
- **Soft state:** replicas or views may temporarily differ while updates
  propagate.
- **Eventual consistency:** replicas are expected to converge when updates
  stop and propagation completes.

BASE is not always a replacement for ACID. The right approach depends on
the system's consistency, availability, and transaction requirements.

## 3. CSV, JSON, Avro, and Parquet

| Format | Structure | Strengths | Trade-offs |
|---|---|---|---|
| CSV | Delimited text rows | Simple, portable, easy to inspect | Weak type information; quoting and dates require care |
| JSON | Nested objects and arrays | Flexible; useful for APIs and event payloads | Repeated field names and parsing overhead |
| Avro | Schema-based binary records | Supports schema evolution; useful for event pipelines | Requires compatible tools to decode |
| Parquet | Column-oriented binary format | Compression and efficient analytical column reads | Less convenient for manual inspection |

QuickCart uses CSV because the supplied datasets are easy to exchange and
inspect. For larger analytical history, Parquet could reduce storage and
improve queries that read selected columns. Avro could suit schema-governed
event streaming, while JSON is useful for nested or variable event data.

No single format is always best. The choice depends on access patterns,
schema requirements, interoperability, and available tools.

## 4. Indexing

An index helps PostgreSQL locate rows without scanning an entire table.
Indexes can improve selective filters, joins, and ordered lookups, but they
require storage and add maintenance work when data changes.

QuickCart defines indexes for common query patterns, including:

- Case-insensitive customer email lookups.
- Order-date filtering.
- Customer and order-date combinations.
- Product lookups from orders.
- Paid-order date filtering through a partial index.
- Product-category searches.
- Clickstream timestamp and customer-time lookups.
- Shipment, support-ticket, and inventory relationships.

Composite indexes should match real query predicates and column order.
Indexes should be evaluated using `EXPLAIN (ANALYZE, BUFFERS)` on realistic
data. Sequential scans can be appropriate for small tables or queries
that read a large proportion of the rows.

## 5. Partitioning

Partitioning divides one logical table into smaller physical partitions.
For large event or order tables, range partitioning by date can make it
easier to exclude irrelevant date ranges from a query and manage old data.

Partitioning also adds operational complexity. Partition boundaries,
indexes, uniqueness constraints, and retention policies need careful design.

QuickCart's supplied datasets are small, so partitioning is not justified
by the current workload alone. If clickstream volume grows substantially,
monthly or daily range partitions on `event_timestamp` could be benchmarked
against a non-partitioned table before adoption.

## 6. Normalisation and relational design

Normalisation reduces unnecessary duplication and helps keep related
facts consistent.

- **First Normal Form (1NF):** columns hold single values and rows can be
  uniquely identified.
- **Second Normal Form (2NF):** non-key attributes depend on the whole
  candidate key, not merely part of a composite key.
- **Third Normal Form (3NF):** non-key attributes depend on the key rather
  than on other non-key attributes.

QuickCart separates customers, products, orders, and clickstream events.
Orders reference customers and products instead of repeating their
descriptive attributes in every order row.

The operational schema applies the same idea:

- `ops.shipments` references an order.
- `ops.shipment_events` stores multiple timestamped events for a shipment.
- `ops.warehouses` represents warehouse locations.
- `ops.inventory` links products and warehouses through a composite key.
- `ops.support_tickets` references a customer and can reference an order.

These relationships reduce duplicated descriptions and keep operational
records connected through primary and foreign keys.

## 7. Analytical query patterns

QuickCart's SQL queries demonstrate common analytical techniques:

- Aggregation and sorting for top customers by paid revenue.
- Monthly grouping and previous-month comparisons for revenue growth.
- Calendar-month logic to find customers ordering in consecutive months.
- `NOT EXISTS` or anti-joins to find products never ordered.
- Window functions for customer rankings and cumulative sales.
- Calendar series and rolling window frames for seven-day average revenue,
  including days with no paid sales.

Business metrics must define their rules explicitly. QuickCart's revenue
reports use paid orders instead of treating pending, failed, or refunded
orders as paid revenue.

## 8. Data quality and quarantine

Data quality checks should detect missing keys, duplicate identifiers,
invalid dates, invalid numeric values, unknown references, and inconsistent
event labels.

QuickCart's cleaning process writes accepted records to `*_clean.csv` and
rejected records to `*_quarantine.csv`, including a reason for rejection.
The original input files remain unchanged so that decisions can be audited.

Some rules depend on time. In particular, an order is considered future
dated relative to the date on which the cleaning script runs. Therefore,
accepted and quarantined order counts may change between runs.

For reliable production operation, quality rules should be documented,
monitored, and tested. Quarantine counts should be reviewed to distinguish
expected anomalies
from unexpected changes in source-system behaviour.

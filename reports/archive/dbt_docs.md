# dbt model layer (Gate 6)

Overall status: **PASS**

## Models

| Layer | Model | Materialization | Schema | Rows |
|---|---|---|---|---:|
| staging | `stg_ga_sessions` | view | `ducklake.stg` | 903,653 |
| staging | `stg_transactions` | view | `ducklake.stg` | 11,552 |
| intermediate | `int_session_behavior` | view | `ducklake.intermediate` | 903,653 |
| marts | `fct_session_conversion` | table | `ducklake.marts` | 902,755 |

- `fct_session_conversion` deduplicates 898 duplicate `(fullVisitorId, visitId)` keys
  (keeps the observation with the most hits, then earliest visit start).
- Conversion rate in the mart: 11,529 / 902,755 = 1.28%.

## Tests

- 22 data tests, all PASS (0.14-0.25 s each).
- Coverage: `not_null` on keys and metrics, `accepted_values` on `conversion_label`,
  `non_negative_counts`, `transaction_count_positive`, `label_not_degenerate`,
  `reconciliation_fct_vs_raw` (mart rows == distinct raw keys).

## Leakage control

- `fct_session_conversion` contains prediction-time features only (device, channel,
  geography, traffic source, session engagement counts). Transaction/revenue fields
  are confined to `stg_transactions` and are not joined into the mart.

## Documentation

- `dbt docs generate` succeeds; catalog written to `dbt_project/target/catalog.json`
  (Git-ignored; local only).
- Model and column descriptions are defined in `schema.yml` files.

## Commands and outcomes

```text
dbt run --project-dir dbt_project --profiles-dir .
  4 of 4 OK (1 table, 3 views) in 2.48 s

dbt test --project-dir dbt_project --profiles-dir .
  22 of 22 PASS in 1.45 s

dbt docs generate --project-dir dbt_project --profiles-dir .
  Catalog written to dbt_project/target/catalog.json
```

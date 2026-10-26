{{ config(materialized='view') }}

-- One row per converting session, exposing the transaction fields that exist in
-- the raw `totals` struct. There is no nested transaction array in this sample,
-- so transaction-level granularity is session grain.

select
    fullVisitorId,
    visitId,
    date,
    visitStartTime,
    totals.transactions as transaction_count,
    totals.transactionRevenue as transaction_revenue_micros,
    totals.totalTransactionRevenue as total_transaction_revenue_micros,
    _ingested_at
from {{ source('ducklake_raw', 'ga_sessions') }}
where totals.transactions is not null

-- Reconciliation: the mart must have one row per distinct raw session key.
select 1
where (
    select count(*) from {{ ref('fct_session_conversion') }}
) != (
    select count(distinct (fullVisitorId, visitId)) from {{ ref('stg_ga_sessions') }}
)

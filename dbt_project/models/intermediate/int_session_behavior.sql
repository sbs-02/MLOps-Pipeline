{{ config(materialized='view') }}

-- Session-level features that are available at prediction time. Derived from
-- stg_ga_sessions so the feature definitions stay single-sourced.

select
    fullVisitorId,
    visitId,
    date,
    visitNumber,
    channelGrouping,
    device_category,
    browser,
    operating_system,
    country,
    continent,
    traffic_source,
    traffic_medium,
    visits,
    hits,
    pageviews,
    time_on_site
from {{ ref('stg_ga_sessions') }}

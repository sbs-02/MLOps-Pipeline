{{ config(materialized='view') }}

-- Staging view over the immutable DuckLake raw table.
-- `is_conversion` is the session-level purchase proxy derived from
-- `totals.transactions IS NOT NULL` (see reports/schema_quality.md). It is the
-- target label for the conversion model, not a feature.

select
    fullVisitorId,
    visitId,
    date,
    visitNumber,
    visitStartTime,
    channelGrouping,
    device.deviceCategory as device_category,
    device.browser as browser,
    device.operatingSystem as operating_system,
    geoNetwork.country as country,
    geoNetwork.continent as continent,
    trafficSource.source as traffic_source,
    trafficSource.medium as traffic_medium,
    coalesce(totals.visits, 0) as visits,
    coalesce(totals.hits, 0) as hits,
    coalesce(totals.pageviews, 0) as pageviews,
    coalesce(totals.timeOnSite, 0) as time_on_site,
    totals.transactions is not null as is_conversion,
    _ingested_at,
    _source
from {{ source('ducklake_raw', 'ga_sessions') }}

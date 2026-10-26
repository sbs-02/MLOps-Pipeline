{{ config(materialized='table') }}

-- One row per unique session (deduplicated on (fullVisitorId, visitId)).
-- Features are prediction-time only; transaction/revenue fields are excluded to
-- avoid label leakage. `conversion_label` is the target.

with ranked as (
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
        time_on_site,
        conversion_label,
        row_number() over (
            partition by fullVisitorId, visitId
            order by hits desc, visitStartTime asc, _ingested_at asc
        ) as rn
    from (
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
            time_on_site,
            is_conversion as conversion_label,
            visitStartTime,
            _ingested_at
        from {{ ref('stg_ga_sessions') }}
    )
)
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
    time_on_site,
    conversion_label
from ranked
where rn = 1

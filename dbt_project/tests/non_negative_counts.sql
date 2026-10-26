-- Non-negative counts in the mart.
select *
from {{ ref('fct_session_conversion') }}
where hits < 0 or pageviews < 0 or time_on_site < 0 or visits < 0

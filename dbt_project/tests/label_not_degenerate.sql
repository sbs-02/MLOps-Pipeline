-- The label must not be degenerate (all 0 or all 1).
select 1
where (
    select count(*) filter (where conversion_label) from {{ ref('fct_session_conversion') }}
) = 0
   or (
    select count(*) filter (where conversion_label) from {{ ref('fct_session_conversion') }}
) = (select count(*) from {{ ref('fct_session_conversion') }})

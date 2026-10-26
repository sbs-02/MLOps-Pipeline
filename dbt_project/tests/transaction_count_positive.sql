-- Transaction counts must be positive in the transaction staging model.
select *
from {{ ref('stg_transactions') }}
where transaction_count is null or transaction_count <= 0

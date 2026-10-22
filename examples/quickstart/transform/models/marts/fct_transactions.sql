{{ config(tags=["hourly"]) }}

-- Business rules live here, once, instead of in every feature query.
select customer_id, merchant_id, amount, created_at
from {{ ref('stg_transactions') }}
where amount > 0

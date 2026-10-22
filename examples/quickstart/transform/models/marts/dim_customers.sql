{{ config(tags=["daily"]) }}

select customer_id, age, country, is_premium, updated_at
from {{ ref('stg_customers') }}

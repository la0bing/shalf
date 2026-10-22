select
    customer_id,
    age,
    country,
    cast(is_premium as boolean) as is_premium,
    cast(updated_at as timestamptz) as updated_at
from {{ source('app', 'customers') }}

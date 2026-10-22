select
    txn_id,
    customer_id,
    merchant_id,
    cast(amount as double) as amount,
    cast(created_at as timestamptz) as created_at
from {{ source('app', 'transactions') }}

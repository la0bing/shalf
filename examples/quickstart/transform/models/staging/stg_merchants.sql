select
    merchant_id,
    cast(risk_score as double) as risk_score,
    category,
    cast(updated_at as timestamptz) as updated_at
from {{ source('app', 'merchants') }}

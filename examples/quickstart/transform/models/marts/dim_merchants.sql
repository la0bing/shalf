{{ config(tags=["daily"]) }}

select merchant_id, risk_score as merchant_risk_score, category, updated_at
from {{ ref('stg_merchants') }}

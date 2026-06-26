-- Regras de negocio: status de receita e flags de qualidade.
with t as (
    select * from {{ ref('stg_transactions') }}
)
select
    *,
    (status = 'approved')                                  as is_approved,
    case
        when status = 'approved'                then 'realizado'
        when status in ('cancelled', 'refunded') then 'perdido'
        else 'aberto'
    end                                                    as revenue_status,
    (cashback_amount is null)                              as is_cashback_missing
from t

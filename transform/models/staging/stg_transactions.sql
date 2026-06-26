-- Limpeza 1:1 da fonte de transacoes (sem joins).
with src as (
    select * from {{ source('raw', 'raw_transactions') }}
)
select
    txn_id,
    cast(txn_ts as timestamp)        as txn_ts,
    cast(txn_ts as date)             as txn_date,
    user_id,
    merchant_id,
    lower(channel)                   as channel,
    cast(gmv as double)              as gmv,
    cast(cashback_amount as double)  as cashback_amount,
    lower(status)                    as status
from src

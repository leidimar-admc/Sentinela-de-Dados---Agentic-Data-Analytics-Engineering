with src as (
    select * from {{ source('raw', 'raw_marketing_spend') }}
)
select
    cast(spend_date as date)  as spend_date,
    lower(channel)            as channel,
    cast(spend as double)     as spend
from src

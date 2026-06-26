with src as (
    select * from {{ source('raw', 'raw_users') }}
)
select
    user_id,
    cast(signup_date as date) as signup_date,
    uf,
    lower(segment)            as segment
from src

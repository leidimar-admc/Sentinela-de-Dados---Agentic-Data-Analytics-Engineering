-- Camada de METRICAS que os agentes vigiam (formato longo, 1 linha por metrica/dia).
-- Definicao unica de cada KPI -> single source of truth.
with txn as (
    select * from {{ ref('int_transactions_enriched') }}
),
spend as (
    select spend_date as d, sum(spend) as spend
    from {{ ref('stg_marketing') }}
    group by 1
),
daily as (
    select
        txn_date                                              as d,
        sum(gmv)                                              as gmv,
        sum(coalesce(cashback_amount, 0))                    as cashback_liability,
        avg(case when is_approved then 1.0 else 0.0 end)     as approval_rate,
        avg(case when is_cashback_missing then 1.0 else 0.0 end) as cashback_null_rate,
        count(distinct user_id)                              as active_users
    from txn
    group by 1
),
joined as (
    select
        daily.*,
        spend.spend,
        case when spend.spend > 0 then daily.gmv / spend.spend end as roas
    from daily
    left join spend using (d)
),
unioned as (
    select d as metric_date, 'gmv'                as metric_name, gmv                as metric_value from joined
    union all select d, 'cashback_liability', cashback_liability from joined
    union all select d, 'approval_rate',      approval_rate      from joined
    union all select d, 'cashback_null_rate', cashback_null_rate from joined
    union all select d, 'active_users',       active_users       from joined
    union all select d, 'roas',               roas               from joined
)
select
    metric_date,
    metric_name,
    cast(metric_value as double) as metric_value
from unioned
order by metric_name, metric_date

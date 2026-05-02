MERGE INTO core_fact_renewables_obligation AS tgt
USING (
    SELECT
        d.date_id,
        o.obligation_period,
        o.period_label,
        o.technology,
        o.metric_name,
        AVG(o.value)::numeric AS value,
        MIN(o.unit) AS unit,
        MIN(o.source_file) AS source_file
    FROM stg_renewables_obligation o
    LEFT JOIN core_dim_date d
        ON d.year = o.year
       AND ((o.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = o.quarter)
    GROUP BY d.date_id, o.obligation_period, o.period_label, o.technology, o.metric_name
) src
ON (
    COALESCE(tgt.obligation_period, '__N__') = COALESCE(src.obligation_period, '__N__')
    AND COALESCE(tgt.period_label, '__N__') = COALESCE(src.period_label, '__N__')
    AND COALESCE(tgt.technology, '__N__') = COALESCE(src.technology, '__N__')
    AND tgt.metric_name = src.metric_name
)
WHEN MATCHED THEN UPDATE SET
    date_id = src.date_id,
    value = src.value,
    unit = src.unit,
    source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (
    date_id, obligation_period, period_label, technology, metric_name, value, unit, source_file
)
VALUES (
    src.date_id, src.obligation_period, src.period_label, src.technology,
    src.metric_name, src.value, src.unit, src.source_file
);

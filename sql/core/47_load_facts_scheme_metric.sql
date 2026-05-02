MERGE INTO core_fact_scheme_metric AS tgt
USING (
    SELECT
        s.period_date,
        s.period_label,
        s.year AS calendar_year,
        s.month AS calendar_month,
        s.quarter,
        s.scheme_key,
        s.entity,
        s.metric_name,
        AVG(s.value)::numeric AS value,
        MIN(s.unit) AS unit,
        MIN(s.source_file) AS source_file
    FROM stg_scheme_metric s
    GROUP BY
        s.period_date,
        s.period_label,
        s.year,
        s.month,
        s.quarter,
        s.scheme_key,
        s.entity,
        s.metric_name,
        s.source_file
) src
ON (
    COALESCE(tgt.source_file, '') = COALESCE(src.source_file, '')
    AND COALESCE(tgt.period_label, '') = COALESCE(src.period_label, '')
    AND tgt.scheme_key = src.scheme_key
    AND COALESCE(tgt.entity, '') = COALESCE(src.entity, '')
    AND tgt.metric_name = src.metric_name
)
WHEN MATCHED THEN UPDATE SET
    period_date = src.period_date,
    calendar_year = src.calendar_year,
    calendar_month = src.calendar_month,
    quarter = src.quarter,
    value = src.value,
    unit = src.unit,
    source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (
    period_date,
    period_label,
    calendar_year,
    calendar_month,
    quarter,
    scheme_key,
    entity,
    metric_name,
    value,
    unit,
    source_file
)
VALUES (
    src.period_date,
    src.period_label,
    src.calendar_year,
    src.calendar_month,
    src.quarter,
    src.scheme_key,
    src.entity,
    src.metric_name,
    src.value,
    src.unit,
    src.source_file
);

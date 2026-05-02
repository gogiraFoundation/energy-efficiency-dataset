-- Official DESNZ DUKES Chapter 6 renewables — convenience layer on staging.
-- Full detail remains in stg_dukes_chapter6.

DROP MATERIALIZED VIEW IF EXISTS mart_dukes_official_renewables CASCADE;

CREATE MATERIALIZED VIEW mart_dukes_official_renewables AS
SELECT
    dukes_table,
    period_year,
    period_label,
    row_label,
    column_label,
    metric_name,
    value,
    unit,
    source_file,
    CASE
        WHEN dukes_table = '6.1' THEN 'commodity_balance'
        WHEN dukes_table = '6.2' THEN 'capacity_generation_shares'
        WHEN dukes_table = '6.3' THEN 'load_factors'
        WHEN dukes_table = '6.4' THEN 'renewable_use_by_vector'
        WHEN dukes_table = '6.5' THEN 'gross_final_consumption'
        WHEN dukes_table = '6.6' THEN 'overseas_trade'
        WHEN dukes_table = '6.7' THEN 'station_counts'
        ELSE 'other'
    END AS grain
FROM stg_dukes_chapter6;

CREATE INDEX IF NOT EXISTS idx_mart_dukes_off_grain_year
    ON mart_dukes_official_renewables (grain, period_year);

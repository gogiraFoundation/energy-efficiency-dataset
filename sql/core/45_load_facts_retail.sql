-- =============================================================================
-- Load core_fact_retail_* tables from stg_retail_*.
--
-- Joins:
--   - core_dim_date          via (year, quarter) — quarterly rows when quarter
--                            is not null, annual rows when quarter is null.
--   - core_dim_supplier      via supplier_name (alias-resolved upstream).
--   - core_dim_payment_method via payment_method text.
--   - core_dim_supplier_size  via size_band text.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- core_fact_supplier_financial : profits, margins, segment aggregates
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_supplier_financial AS tgt
USING (
    SELECT
        d.date_id,
        s.supplier_id,
        sp.segment,
        sp.metric_name,
        sp.value,
        sp.unit,
        sp.source_file
    FROM stg_supplier_profits sp
    JOIN core_dim_date d
        ON d.year = sp.year
       AND ((sp.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = sp.quarter)
    LEFT JOIN core_dim_supplier s ON s.supplier_name = sp.supplier_name
    WHERE sp.segment IS NOT NULL
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND tgt.segment = src.segment
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET
    value = src.value,
    unit = src.unit,
    source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, supplier_id, segment, metric_name, value, unit, source_file)
VALUES (src.date_id, src.supplier_id, src.segment, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_consumer_debt
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_consumer_debt AS tgt
USING (
    SELECT
        d.date_id,
        cd.commodity,
        pm.payment_method_id,
        s.supplier_id,
        cd.component,
        cd.metric_name,
        cd.value,
        cd.unit,
        cd.source_file
    FROM stg_consumer_debt cd
    JOIN core_dim_date d
        ON d.year = cd.year
       AND ((cd.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = cd.quarter)
    LEFT JOIN core_dim_payment_method pm ON pm.payment_method = cd.payment_method
    LEFT JOIN core_dim_supplier s ON s.supplier_name = cd.supplier_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.payment_method_id, -1) = COALESCE(src.payment_method_id, -1)
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND COALESCE(tgt.component, '__N__') = COALESCE(src.component, '__N__')
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, payment_method_id, supplier_id, component, metric_name, value, unit, source_file)
VALUES (src.date_id, src.commodity, src.payment_method_id, src.supplier_id, src.component, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_consumer_disconnections
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_consumer_disconnections AS tgt
USING (
    SELECT
        d.date_id,
        cd.commodity,
        pm.payment_method_id,
        s.supplier_id,
        cd.metric_name,
        cd.value,
        cd.unit,
        cd.source_file
    FROM stg_consumer_disconnections cd
    JOIN core_dim_date d
        ON d.year = cd.year
       AND ((cd.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = cd.quarter)
    LEFT JOIN core_dim_payment_method pm ON pm.payment_method = cd.payment_method
    LEFT JOIN core_dim_supplier s ON s.supplier_name = cd.supplier_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.payment_method_id, -1) = COALESCE(src.payment_method_id, -1)
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, payment_method_id, supplier_id, metric_name, value, unit, source_file)
VALUES (src.date_id, src.commodity, src.payment_method_id, src.supplier_id, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_switching_activity
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_switching_activity AS tgt
USING (
    SELECT
        d.date_id,
        sw.commodity,
        ss.supplier_size_id,
        sw.metric_name,
        AVG(sw.value) AS value,
        MIN(sw.unit) AS unit,
        MIN(sw.source_file) AS source_file
    FROM stg_switching sw
    JOIN core_dim_date d
        ON d.year = sw.year
       AND ((sw.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = sw.quarter)
    LEFT JOIN core_dim_supplier_size ss ON ss.size_band = sw.supplier_size
    GROUP BY d.date_id, sw.commodity, ss.supplier_size_id, sw.metric_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.supplier_size_id, -1) = COALESCE(src.supplier_size_id, -1)
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, supplier_size_id, metric_name, value, unit, source_file)
VALUES (src.date_id, src.commodity, src.supplier_size_id, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_tariff_benchmarks
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_tariff_benchmarks AS tgt
USING (
    SELECT
        d.date_id,
        t.commodity,
        t.supplier_group,
        s.supplier_id,
        pm.payment_method_id,
        t.tariff_type,
        t.metric_name,
        AVG(t.value) AS value,
        MIN(t.unit) AS unit,
        MIN(t.source_file) AS source_file
    FROM stg_tariffs_price_cap t
    JOIN core_dim_date d
        ON d.year = t.year
       AND ((t.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = t.quarter)
    LEFT JOIN core_dim_supplier s ON s.supplier_name = t.supplier_name
    LEFT JOIN core_dim_payment_method pm ON pm.payment_method = t.payment_method
    GROUP BY d.date_id, t.commodity, t.supplier_group, s.supplier_id, pm.payment_method_id, t.tariff_type, t.metric_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.supplier_group, '__N__') = COALESCE(src.supplier_group, '__N__')
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND COALESCE(tgt.payment_method_id, -1) = COALESCE(src.payment_method_id, -1)
    AND COALESCE(tgt.tariff_type, '__N__') = COALESCE(src.tariff_type, '__N__')
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, supplier_group, supplier_id, payment_method_id, tariff_type, metric_name, value, unit, source_file)
VALUES (src.date_id, src.commodity, src.supplier_group, src.supplier_id, src.payment_method_id, src.tariff_type, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_bill_breakdown
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_bill_breakdown AS tgt
USING (
    SELECT
        d.date_id,
        b.commodity,
        pm.payment_method_id,
        b.supplier_group,
        b.component,
        b.metric_name,
        AVG(b.value) AS value,
        MIN(b.unit) AS unit,
        MIN(b.source_file) AS source_file
    FROM stg_bill_breakdown b
    JOIN core_dim_date d
        ON d.year = b.year
       AND ((b.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = b.quarter)
    LEFT JOIN core_dim_payment_method pm ON pm.payment_method = b.payment_method
    GROUP BY d.date_id, b.commodity, pm.payment_method_id, b.supplier_group, b.component, b.metric_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.payment_method_id, -1) = COALESCE(src.payment_method_id, -1)
    AND COALESCE(tgt.supplier_group, '__N__') = COALESCE(src.supplier_group, '__N__')
    AND tgt.component = src.component
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, payment_method_id, supplier_group, component, metric_name, value, unit, source_file)
VALUES (src.date_id, src.commodity, src.payment_method_id, src.supplier_group, src.component, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_complaints_resolution
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_complaints_resolution AS tgt
USING (
    SELECT
        d.date_id,
        s.supplier_id,
        ss.supplier_size_id,
        c.metric_name,
        AVG(c.value) AS value,
        MIN(c.unit) AS unit,
        MIN(c.source_file) AS source_file
    FROM stg_complaints c
    JOIN core_dim_date d
        ON d.year = c.year
       AND ((c.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = c.quarter)
    LEFT JOIN core_dim_supplier s ON s.supplier_name = c.supplier_name
    LEFT JOIN core_dim_supplier_size ss ON ss.size_band = c.supplier_size
    GROUP BY d.date_id, s.supplier_id, ss.supplier_size_id, c.metric_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND COALESCE(tgt.supplier_size_id, -1) = COALESCE(src.supplier_size_id, -1)
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, supplier_id, supplier_size_id, metric_name, value, unit, source_file)
VALUES (src.date_id, src.supplier_id, src.supplier_size_id, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_satisfaction_scores
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_satisfaction_scores AS tgt
USING (
    SELECT
        d.date_id,
        s.supplier_id,
        ss.supplier_size_id,
        sat.commodity,
        sat.aspect,
        sat.metric_name,
        AVG(sat.value) AS value,
        MIN(sat.unit) AS unit,
        MIN(sat.source_file) AS source_file
    FROM stg_satisfaction sat
    JOIN core_dim_date d
        ON d.year = sat.year
       AND ((sat.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = sat.quarter)
    LEFT JOIN core_dim_supplier s ON s.supplier_name = sat.supplier_name
    LEFT JOIN core_dim_supplier_size ss ON ss.size_band = sat.supplier_size
    GROUP BY d.date_id, s.supplier_id, ss.supplier_size_id, sat.commodity, sat.aspect, sat.metric_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND COALESCE(tgt.supplier_size_id, -1) = COALESCE(src.supplier_size_id, -1)
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.aspect, '__N__') = COALESCE(src.aspect, '__N__')
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, supplier_id, supplier_size_id, commodity, aspect, metric_name, value, unit, source_file)
VALUES (src.date_id, src.supplier_id, src.supplier_size_id, src.commodity, src.aspect, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_market_structure
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_market_structure AS tgt
USING (
    SELECT
        d.date_id,
        ms.commodity,
        ms.metric_name,
        AVG(ms.value) AS value,
        MIN(ms.unit) AS unit,
        MIN(ms.source_file) AS source_file
    FROM stg_market_structure ms
    JOIN core_dim_date d
        ON d.year = ms.year
       AND ((ms.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = ms.quarter)
    GROUP BY d.date_id, ms.commodity, ms.metric_name
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, metric_name, value, unit, source_file)
VALUES (src.date_id, src.commodity, src.metric_name, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_market_share_retail
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_market_share_retail AS tgt
USING (
    SELECT
        d.date_id,
        ms.commodity,
        s.supplier_id,
        COALESCE(ms.segment, 'domestic') AS segment,
        AVG(ms.share_pct) AS share_pct,
        MIN(ms.source_file) AS source_file
    FROM stg_market_share_retail ms
    JOIN core_dim_date d
        ON d.year = ms.year
       AND ((ms.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = ms.quarter)
    JOIN core_dim_supplier s ON s.supplier_name = ms.supplier_name
    GROUP BY d.date_id, ms.commodity, s.supplier_id, COALESCE(ms.segment, 'domestic')
) src
ON (tgt.date_id = src.date_id AND tgt.commodity = src.commodity AND tgt.supplier_id = src.supplier_id AND tgt.segment = src.segment)
WHEN MATCHED THEN UPDATE SET share_pct = src.share_pct, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, commodity, supplier_id, segment, share_pct, source_file)
VALUES (src.date_id, src.commodity, src.supplier_id, src.segment, src.share_pct, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_household_spend
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_household_spend AS tgt
USING (
    SELECT d.date_id, hs.segment, hs.value_pct, hs.source_file
    FROM stg_household_spend hs
    JOIN core_dim_date d ON d.year = hs.year AND d.quarter IS NULL
) src
ON (tgt.date_id = src.date_id AND tgt.segment = src.segment)
WHEN MATCHED THEN UPDATE SET value_pct = src.value_pct, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, segment, value_pct, source_file)
VALUES (src.date_id, src.segment, src.value_pct, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_customer_accounts_retail
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_customer_accounts_retail AS tgt
USING (
    SELECT
        d.date_id,
        s.supplier_id,
        c.commodity,
        c.segment,
        c.tariff_type,
        AVG(c.value) AS value,
        MIN(c.unit) AS unit,
        MIN(c.source_file) AS source_file
    FROM stg_customer_accounts_retail c
    JOIN core_dim_date d ON d.year = c.year AND d.quarter IS NULL
    LEFT JOIN core_dim_supplier s ON s.supplier_name = c.supplier_name
    GROUP BY d.date_id, s.supplier_id, c.commodity, c.segment, c.tariff_type
) src
ON (tgt.date_id = src.date_id
    AND COALESCE(tgt.supplier_id, -1) = COALESCE(src.supplier_id, -1)
    AND COALESCE(tgt.commodity, '__N__') = COALESCE(src.commodity, '__N__')
    AND COALESCE(tgt.segment, '__N__') = COALESCE(src.segment, '__N__')
    AND COALESCE(tgt.tariff_type, '__N__') = COALESCE(src.tariff_type, '__N__'))
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, supplier_id, commodity, segment, tariff_type, value, unit, source_file)
VALUES (src.date_id, src.supplier_id, src.commodity, src.segment, src.tariff_type, src.value, src.unit, src.source_file);

-- ---------------------------------------------------------------------------
-- core_fact_heating_systems
-- ---------------------------------------------------------------------------

MERGE INTO core_fact_heating_systems AS tgt
USING (
    SELECT
        d.date_id,
        h.component,
        AVG(h.value) AS value,
        MIN(h.unit) AS unit,
        MIN(h.source_file) AS source_file
    FROM stg_heating_systems h
    JOIN core_dim_date d
        ON d.year = h.year
       AND ((h.quarter IS NULL AND d.quarter IS NULL) OR d.quarter = h.quarter)
    GROUP BY d.date_id, h.component
) src
ON (tgt.date_id = src.date_id AND tgt.component = src.component)
WHEN MATCHED THEN UPDATE SET value = src.value, unit = src.unit, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (date_id, component, value, unit, source_file)
VALUES (src.date_id, src.component, src.value, src.unit, src.source_file);

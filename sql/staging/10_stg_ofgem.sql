-- Fan-in staging: each stg_* table is a UNION of the existing JSONB raw layer
-- (raw_ofgem_*) and the new typed xlsx raw layer (raw_xlsx_*), keyed on year +
-- canonical company_name + sector_code.  The xlsx pivot uses MAX/FILTER to
-- collapse the long (year, company, metric, value) shape back to the wide
-- staging schema expected downstream.
--
-- Company name normalisation: stg_company_alias.source_company_name ->
-- canonical company_name + sector code.  Falls back to the raw text if no
-- alias row matches (the join is LEFT, downstream will surface unmatched
-- companies via 10_quality_checks.sql).

-- Defensive: if the user runs `staging` on a brand-new database without ever
-- running the `xlsx` step, the xlsx raw tables and the mapping tables won't
-- exist yet.  Create empty stand-ins so this script remains runnable.
CREATE TABLE IF NOT EXISTS stg_company_alias (
    source_system        TEXT,
    source_company_name  TEXT,
    ofgem_company_id     TEXT,
    company_name         TEXT,
    network_sector_code  TEXT,
    owner_group          TEXT
);
CREATE TABLE IF NOT EXISTS raw_xlsx_reliability             (year INT, company_name TEXT, network_sector TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_expenditure             (year INT, company_name TEXT, network_sector TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_rore                    (year INT, company_name TEXT, network_sector TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_customer_satisfaction   (year INT, company_name TEXT, network_sector TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_emissions               (year INT, company_name TEXT, network_sector TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);

DROP TABLE IF EXISTS stg_network_reliability CASCADE;
DROP TABLE IF EXISTS stg_financial_performance CASCADE;
DROP TABLE IF EXISTS stg_customer_metrics CASCADE;
DROP TABLE IF EXISTS stg_emissions CASCADE;

-- =============================================================================
-- stg_network_reliability
-- =============================================================================

CREATE TABLE stg_network_reliability (
    year INT,
    company_name TEXT,
    network_sector TEXT,
    ens_mwh NUMERIC,
    customer_interruptions NUMERIC,
    minutes_lost NUMERIC,
    gas_interruption_volume NUMERIC,
    gas_lost_volume NUMERIC
);

WITH jsonb_src AS (
    SELECT
        (payload->>'year')::numeric::int AS year,
        nullif(payload->>'company_name', '') AS company_name,
        nullif(payload->>'network_sector', '') AS network_sector,
        (payload->>'ens_mwh')::numeric AS ens_mwh,
        (payload->>'customer_interruptions')::numeric AS customer_interruptions,
        (payload->>'minutes_lost')::numeric AS minutes_lost,
        (payload->>'gas_interruption_volume')::numeric AS gas_interruption_volume,
        (payload->>'gas_lost_volume')::numeric AS gas_lost_volume
    FROM raw_ofgem_ens
),
xlsx_src AS (
    SELECT
        x.year,
        coalesce(ca.company_name, x.company_name) AS company_name,
        CASE x.network_sector
            WHEN 'Electricity Transmission' THEN 'ET'
            WHEN 'Electricity Distribution' THEN 'ED'
            WHEN 'Gas Transmission'         THEN 'GT'
            WHEN 'Gas Distribution'         THEN 'GD'
            ELSE x.network_sector
        END AS network_sector,
        MAX(value) FILTER (WHERE metric_name = 'ens_mwh') AS ens_mwh,
        MAX(value) FILTER (WHERE metric_name = 'customer_interruptions') AS customer_interruptions,
        MAX(value) FILTER (WHERE metric_name = 'minutes_lost') AS minutes_lost,
        NULL::numeric AS gas_interruption_volume,   -- not in source xlsx set
        MAX(value) FILTER (WHERE metric_name = 'gas_lost_volume') AS gas_lost_volume
    FROM raw_xlsx_reliability x
    LEFT JOIN stg_company_alias ca
        ON ca.source_company_name = x.company_name
       AND (ca.network_sector_code IS NULL
            OR ca.network_sector_code = CASE x.network_sector
                                        WHEN 'Electricity Transmission' THEN 'ET'
                                        WHEN 'Electricity Distribution' THEN 'ED'
                                        WHEN 'Gas Transmission'         THEN 'GT'
                                        WHEN 'Gas Distribution'         THEN 'GD'
                                        ELSE x.network_sector END)
    WHERE x.year IS NOT NULL
    GROUP BY x.year, coalesce(ca.company_name, x.company_name), x.network_sector
),
combined AS (
    SELECT *, 1 AS prio FROM xlsx_src
    UNION ALL
    SELECT *, 2 AS prio FROM jsonb_src
),
deduped AS (
    SELECT DISTINCT ON (year, company_name, network_sector)
        year, company_name, network_sector,
        ens_mwh, customer_interruptions, minutes_lost,
        gas_interruption_volume, gas_lost_volume
    FROM combined
    WHERE company_name IS NOT NULL AND network_sector IS NOT NULL
    ORDER BY year, company_name, network_sector, prio
)
INSERT INTO stg_network_reliability
SELECT * FROM deduped;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_network_reliability_uniq
    ON stg_network_reliability (year, company_name, network_sector);

-- =============================================================================
-- stg_financial_performance  (totex actual + allowance + RoRE)
-- =============================================================================

CREATE TABLE stg_financial_performance (
    year INT,
    company_name TEXT,
    network_sector TEXT,
    totex_allowance_million_gbp NUMERIC,
    actual_totex_million_gbp NUMERIC,
    rore_pct NUMERIC
);

WITH jsonb_src AS (
    SELECT
        (re.payload->>'year')::numeric::int AS year,
        nullif(re.payload->>'company_name', '') AS company_name,
        nullif(re.payload->>'network_sector', '') AS network_sector,
        (re.payload->>'totex_allowance_million_gbp')::numeric AS totex_allowance_million_gbp,
        (re.payload->>'actual_totex_million_gbp')::numeric AS actual_totex_million_gbp,
        coalesce(
            (re.payload->>'rore_pct')::numeric,
            (rmatch.rr->>'rore_pct')::numeric
        ) AS rore_pct
    FROM raw_ofgem_expenditure re
    LEFT JOIN LATERAL (
        SELECT ror.payload AS rr
        FROM raw_ofgem_rore ror
        WHERE (ror.payload->>'year')::numeric::int = (re.payload->>'year')::numeric::int
          AND ror.payload->>'company_name' = re.payload->>'company_name'
          AND ror.payload->>'network_sector' = re.payload->>'network_sector'
        LIMIT 1
    ) rmatch ON TRUE
),
xlsx_exp AS (
    SELECT
        x.year,
        coalesce(ca.company_name, x.company_name) AS company_name,
        CASE x.network_sector
            WHEN 'Electricity Transmission' THEN 'ET'
            WHEN 'Electricity Distribution' THEN 'ED'
            WHEN 'Gas Transmission'         THEN 'GT'
            WHEN 'Gas Distribution'         THEN 'GD'
            ELSE x.network_sector
        END AS network_sector,
        MAX(value) FILTER (WHERE metric_name = 'totex_allowance_million_gbp') AS totex_allowance_million_gbp,
        MAX(value) FILTER (WHERE metric_name = 'actual_totex_million_gbp')    AS actual_totex_million_gbp
    FROM raw_xlsx_expenditure x
    LEFT JOIN stg_company_alias ca ON ca.source_company_name = x.company_name
    WHERE x.year IS NOT NULL
    GROUP BY x.year, coalesce(ca.company_name, x.company_name), x.network_sector
),
xlsx_rore AS (
    SELECT
        x.year,
        coalesce(ca.company_name, x.company_name) AS company_name,
        CASE x.network_sector
            WHEN 'Electricity Transmission' THEN 'ET'
            WHEN 'Electricity Distribution' THEN 'ED'
            WHEN 'Gas Transmission'         THEN 'GT'
            WHEN 'Gas Distribution'         THEN 'GD'
            ELSE x.network_sector
        END AS network_sector,
        MAX(value) FILTER (WHERE metric_name = 'rore_pct') AS rore_pct
    FROM raw_xlsx_rore x
    LEFT JOIN stg_company_alias ca ON ca.source_company_name = x.company_name
    GROUP BY x.year, coalesce(ca.company_name, x.company_name), x.network_sector
),
xlsx_src AS (
    -- RoRE files are RIIO-cumulative (single eight-year value).  Broadcast
    -- the cumulative figure to every year that has expenditure data so marts
    -- can join on (year, company, sector) without losing rows.
    SELECT
        e.year,
        e.company_name,
        e.network_sector,
        e.totex_allowance_million_gbp,
        e.actual_totex_million_gbp,
        coalesce(rsame.rore_pct, rfb.rore_pct) AS rore_pct
    FROM xlsx_exp e
    LEFT JOIN xlsx_rore rsame
        ON rsame.year = e.year
       AND rsame.company_name = e.company_name
       AND rsame.network_sector = e.network_sector
    LEFT JOIN LATERAL (
        SELECT MAX(rore_pct) AS rore_pct
        FROM xlsx_rore r2
        WHERE r2.company_name = e.company_name
          AND r2.network_sector = e.network_sector
    ) rfb ON TRUE
),
combined AS (
    SELECT *, 1 AS prio FROM xlsx_src
    UNION ALL
    SELECT *, 2 AS prio FROM jsonb_src
),
deduped AS (
    SELECT DISTINCT ON (year, company_name, network_sector)
        year, company_name, network_sector,
        totex_allowance_million_gbp, actual_totex_million_gbp, rore_pct
    FROM combined
    WHERE company_name IS NOT NULL AND network_sector IS NOT NULL
    ORDER BY year, company_name, network_sector, prio
)
INSERT INTO stg_financial_performance
SELECT * FROM deduped;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_financial_performance_uniq
    ON stg_financial_performance (year, company_name, network_sector);

-- =============================================================================
-- stg_customer_metrics  (cost per customer + satisfaction score)
-- =============================================================================

CREATE TABLE stg_customer_metrics (
    year INT,
    company_name TEXT,
    network_sector TEXT,
    geography_code TEXT,
    cost_per_customer_gbp NUMERIC,
    satisfaction_score NUMERIC
);

WITH jsonb_src AS (
    SELECT
        (payload->>'year')::numeric::int AS year,
        nullif(payload->>'company_name', '') AS company_name,
        nullif(payload->>'network_sector', '') AS network_sector,
        coalesce(nullif(payload->>'geography_code', ''), 'GB') AS geography_code,
        (payload->>'cost_per_customer_gbp')::numeric AS cost_per_customer_gbp,
        (payload->>'satisfaction_score')::numeric AS satisfaction_score
    FROM raw_ofgem_customer_metrics
),
xlsx_src AS (
    SELECT
        x.year,
        coalesce(ca.company_name, x.company_name) AS company_name,
        CASE x.network_sector
            WHEN 'Electricity Transmission' THEN 'ET'
            WHEN 'Electricity Distribution' THEN 'ED'
            WHEN 'Gas Transmission'         THEN 'GT'
            WHEN 'Gas Distribution'         THEN 'GD'
            ELSE x.network_sector
        END AS network_sector,
        'GB' AS geography_code,
        NULL::numeric AS cost_per_customer_gbp,
        -- Combine stakeholder/customer scores into a single satisfaction
        -- composite (mean of any non-null components) so downstream joins
        -- have one row per (year, company, sector).
        NULLIF(
            (
                coalesce(MAX(value) FILTER (WHERE metric_name='customer_survey_score'), 0)
              + coalesce(MAX(value) FILTER (WHERE metric_name='stakeholder_engagement_score'), 0)
              + coalesce(MAX(value) FILTER (WHERE metric_name='stakeholder_survey_score'), 0)
            )::numeric / NULLIF(
                (CASE WHEN MAX(value) FILTER (WHERE metric_name='customer_survey_score') IS NOT NULL THEN 1 ELSE 0 END)
              + (CASE WHEN MAX(value) FILTER (WHERE metric_name='stakeholder_engagement_score') IS NOT NULL THEN 1 ELSE 0 END)
              + (CASE WHEN MAX(value) FILTER (WHERE metric_name='stakeholder_survey_score') IS NOT NULL THEN 1 ELSE 0 END)
            , 0)
        , 0) AS satisfaction_score
    FROM raw_xlsx_customer_satisfaction x
    LEFT JOIN stg_company_alias ca ON ca.source_company_name = x.company_name
    WHERE x.year IS NOT NULL
    GROUP BY x.year, coalesce(ca.company_name, x.company_name), x.network_sector
),
combined AS (
    SELECT *, 1 AS prio FROM xlsx_src
    UNION ALL
    SELECT *, 2 AS prio FROM jsonb_src
),
deduped AS (
    SELECT DISTINCT ON (year, company_name, network_sector, geography_code)
        year, company_name, network_sector, geography_code,
        cost_per_customer_gbp, satisfaction_score
    FROM combined
    WHERE company_name IS NOT NULL
    ORDER BY year, company_name, network_sector, geography_code, prio
)
INSERT INTO stg_customer_metrics
SELECT * FROM deduped;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_customer_metrics_uniq
    ON stg_customer_metrics (year, company_name, network_sector, geography_code);

-- =============================================================================
-- stg_emissions  (SF6 + business carbon footprint scopes 1/2/3)
-- =============================================================================

CREATE TABLE stg_emissions (
    year INT,
    company_name TEXT,
    network_sector TEXT,
    sf6_kg NUMERIC,
    carbon_footprint_tco2e NUMERIC
);

WITH jsonb_src AS (
    SELECT
        (payload->>'year')::numeric::int AS year,
        nullif(payload->>'company_name', '') AS company_name,
        nullif(payload->>'network_sector', '') AS network_sector,
        (payload->>'sf6_kg')::numeric AS sf6_kg,
        (payload->>'carbon_footprint_tco2e')::numeric AS carbon_footprint_tco2e
    FROM raw_ofgem_emissions
),
xlsx_src AS (
    SELECT
        x.year,
        coalesce(ca.company_name, x.company_name) AS company_name,
        CASE x.network_sector
            WHEN 'Electricity Transmission' THEN 'ET'
            WHEN 'Electricity Distribution' THEN 'ED'
            WHEN 'Gas Transmission'         THEN 'GT'
            WHEN 'Gas Distribution'         THEN 'GD'
            ELSE x.network_sector
        END AS network_sector,
        MAX(value) FILTER (WHERE metric_name = 'sf6_kg') AS sf6_kg,
        coalesce(
            MAX(value) FILTER (WHERE metric_name = 'ghg_scope1_tco2e'), 0
        ) + coalesce(
            MAX(value) FILTER (WHERE metric_name = 'ghg_scope2_tco2e'), 0
        ) + coalesce(
            MAX(value) FILTER (WHERE metric_name = 'ghg_scope3_tco2e'), 0
        ) AS carbon_footprint_tco2e
    FROM raw_xlsx_emissions x
    LEFT JOIN stg_company_alias ca ON ca.source_company_name = x.company_name
    WHERE x.year IS NOT NULL
    GROUP BY x.year, coalesce(ca.company_name, x.company_name), x.network_sector
),
combined AS (
    SELECT *, 1 AS prio FROM xlsx_src
    UNION ALL
    SELECT *, 2 AS prio FROM jsonb_src
),
deduped AS (
    SELECT DISTINCT ON (year, company_name, network_sector)
        year, company_name, network_sector,
        sf6_kg, NULLIF(carbon_footprint_tco2e, 0) AS carbon_footprint_tco2e
    FROM combined
    WHERE company_name IS NOT NULL AND network_sector IS NOT NULL
    ORDER BY year, company_name, network_sector, prio
)
INSERT INTO stg_emissions
SELECT * FROM deduped;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_emissions_uniq
    ON stg_emissions (year, company_name, network_sector);

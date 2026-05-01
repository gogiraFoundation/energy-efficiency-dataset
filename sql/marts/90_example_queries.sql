-- Example analytical queries.
-- These are illustrative SELECTs; running this file as part of the marts stage
-- materialises nothing (it's just SELECTs which are discarded).
-- The orchestrator picks them up so they're parse-checked on every run.

-- ---------------------------------------------------------------------------
-- 1. Cost vs reliability for transmission owners (RIIO-T1 window).
-- ---------------------------------------------------------------------------
SELECT year, company_name,
       ens_mwh,
       actual_totex_million_gbp,
       ens_per_million_gbp_spend,
       reliability_rate,
       cost_efficiency_score,
       rore_pct
FROM mart_cost_reliability
WHERE sector_name = 'Electricity Transmission'
  AND year BETWEEN 2013 AND 2021
ORDER BY company_name, year;

-- ---------------------------------------------------------------------------
-- 2. Top industries by total output_at_risk_gbp (latest year).
-- ---------------------------------------------------------------------------
SELECT year, sic_code, industry_name, SUM(output_at_risk_gbp) AS output_at_risk_gbp
FROM mart_economic_impact
GROUP BY year, sic_code, industry_name
ORDER BY output_at_risk_gbp DESC
LIMIT 5;

-- ---------------------------------------------------------------------------
-- 3. YoY ENS / spend deltas per company.
-- ---------------------------------------------------------------------------
WITH yearly AS (
    SELECT year, company_name,
           SUM(ens_mwh) AS ens_mwh,
           SUM(actual_totex_million_gbp) AS spend
    FROM mart_cost_reliability
    GROUP BY year, company_name
)
SELECT
    year,
    company_name,
    ens_mwh - LAG(ens_mwh) OVER (PARTITION BY company_name ORDER BY year) AS ens_delta,
    spend   - LAG(spend)   OVER (PARTITION BY company_name ORDER BY year) AS spend_delta,
    (ens_mwh - LAG(ens_mwh) OVER (PARTITION BY company_name ORDER BY year))
        / NULLIF(spend - LAG(spend) OVER (PARTITION BY company_name ORDER BY year), 0)
    AS ens_change_per_spend_change
FROM yearly
ORDER BY company_name, year;

-- ===========================================================================
-- REQUIRED EXAMPLE QUERIES (per project specification)
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- A. Top 3 transmission owners with worst ENS per £m spend (2018-2021).
--     "worst" = highest ratio (more energy not supplied per pound spent).
-- ---------------------------------------------------------------------------
WITH window_avg AS (
    SELECT
        company_name,
        AVG(ens_per_million_gbp_spend) AS avg_ens_per_mgbp,
        SUM(ens_mwh) AS total_ens_mwh,
        SUM(actual_totex_million_gbp) AS total_spend_mgbp
    FROM mart_cost_reliability
    WHERE sector_name = 'Electricity Transmission'
      AND year BETWEEN 2018 AND 2021
      AND ens_per_million_gbp_spend IS NOT NULL
    GROUP BY company_name
)
SELECT *
FROM window_avg
ORDER BY avg_ens_per_mgbp DESC NULLS LAST
LIMIT 3;

-- ---------------------------------------------------------------------------
-- B. Year-over-year change in output_at_risk_gbp for the manufacturing sector.
--     Manufacturing maps to SIC section 'C'.  We sum across regions, then take
--     LAG over year.
-- ---------------------------------------------------------------------------
WITH manufacturing_yearly AS (
    SELECT
        year,
        SUM(output_at_risk_gbp) AS output_at_risk_gbp
    FROM mart_economic_impact
    WHERE LEFT(sic_code, 1) = 'C' OR LOWER(industry_name) LIKE '%manufactur%'
    GROUP BY year
)
SELECT
    year,
    output_at_risk_gbp,
    output_at_risk_gbp - LAG(output_at_risk_gbp) OVER (ORDER BY year) AS yoy_delta_gbp,
    100.0 * (output_at_risk_gbp - LAG(output_at_risk_gbp) OVER (ORDER BY year))
        / NULLIF(LAG(output_at_risk_gbp) OVER (ORDER BY year), 0) AS yoy_delta_pct
FROM manufacturing_yearly
ORDER BY year;

-- ---------------------------------------------------------------------------
-- C. Correlation between network availability and customer satisfaction
--     for gas distribution (RIIO-GD1).
--     Uses raw_xlsx_network_availability (Yearly availability % per company)
--     joined to raw_xlsx_customer_satisfaction (composite score per company).
-- ---------------------------------------------------------------------------
WITH avail AS (
    SELECT year, company_name,
           AVG(value) AS network_availability_pct
    FROM raw_xlsx_network_availability
    WHERE network_sector = 'Gas Distribution'
      AND metric_name = 'network_availability_pct'
    GROUP BY year, company_name
),
sat AS (
    -- Pick a single canonical satisfaction metric to keep the scale consistent.
    -- For GD1 the AVCSC (customer survey score, 0-10) is the most directly
    -- comparable to availability %.
    SELECT year, company_name,
           MAX(value) AS customer_satisfaction_score
    FROM raw_xlsx_customer_satisfaction
    WHERE network_sector = 'Gas Distribution'
      AND metric_name = 'customer_survey_score'
    GROUP BY year, company_name
)
SELECT
    corr(avail.network_availability_pct, sat.customer_satisfaction_score)
        AS pearson_corr,
    COUNT(*) AS pair_count
FROM avail
JOIN sat USING (year, company_name);

-- Quality assertions run after core load.  Hard FAIL on data corruption,
-- WARN (NOTICE) on data incompleteness that downstream marts can tolerate.

DO $$
DECLARE
    v_count   INTEGER;
    v_pct     NUMERIC;
    v_total   INTEGER;
BEGIN
    -- ---------- HARD FAILS ----------

    SELECT COUNT(*) INTO v_count FROM core_fact_network_reliability WHERE ens_mwh < 0;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Quality check failed: ENS < 0 in core_fact_network_reliability';
    END IF;

    SELECT COUNT(*) INTO v_count FROM core_fact_financial_performance WHERE actual_totex_million_gbp < 0;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Quality check failed: actual_totex < 0';
    END IF;

    SELECT COUNT(*) INTO v_count
    FROM (
        SELECT date_id, geography_id, company_id, network_sector_id, COUNT(*)
        FROM core_fact_network_reliability
        GROUP BY 1, 2, 3, 4
        HAVING COUNT(*) > 1
    ) d;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Quality check failed: duplicate reliability keys';
    END IF;

    -- raw_xlsx_* sanity: known non-negative metrics must not be negative.
    SELECT COUNT(*) INTO v_count
    FROM raw_xlsx_reliability
    WHERE metric_name IN ('ens_mwh','customer_interruptions','minutes_lost','gas_lost_volume')
      AND value < 0;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Quality check failed: negative non-negative metric in raw_xlsx_reliability (%) row(s)', v_count;
    END IF;

    SELECT COUNT(*) INTO v_count
    FROM raw_xlsx_expenditure
    WHERE metric_name IN ('actual_totex_million_gbp','totex_allowance_million_gbp')
      AND value < 0;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Quality check failed: negative spend in raw_xlsx_expenditure (% rows)', v_count;
    END IF;

    -- ---------- SOFT WARNINGS ----------

    SELECT COUNT(*), COUNT(*) FILTER (WHERE total_demand_mwh IS NULL)
      INTO v_total, v_count
      FROM core_fact_network_reliability nr
      JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
     WHERE ns.commodity = 'electricity';
    IF v_total > 0 THEN
        v_pct := 100.0 * v_count / v_total;
        IF v_pct > 10 THEN
            RAISE NOTICE 'WARN: % %% of electricity reliability rows missing total_demand_mwh (% / %)', v_pct, v_count, v_total;
        END IF;
    END IF;

    SELECT COUNT(*) INTO v_count
      FROM stg_network_reliability s
      LEFT JOIN core_dim_company c ON c.company_name = s.company_name
     WHERE c.company_id IS NULL;
    IF v_count > 0 THEN
        RAISE NOTICE 'WARN: % stg_network_reliability rows have no matching core_dim_company entry', v_count;
    END IF;

    SELECT COUNT(*) INTO v_count
      FROM raw_xlsx_reliability x
      LEFT JOIN stg_company_alias ca ON ca.source_company_name = x.company_name
     WHERE ca.company_name IS NULL
       AND x.company_name IS NOT NULL;
    IF v_count > 0 THEN
        RAISE NOTICE 'WARN: % raw_xlsx_reliability rows have no company alias mapping', v_count;
    END IF;
END $$;

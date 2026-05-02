-- Migration: move legacy public raw/audit tables into intended schemas.
-- This script is idempotent and contains both UP and DOWN sections.

-- ============================================================================
-- UP
-- ============================================================================
BEGIN;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS audit;

DO $$
BEGIN
  IF to_regclass('public.etl_run_log') IS NOT NULL
     AND to_regclass('audit.etl_run_log') IS NULL THEN
    ALTER TABLE public.etl_run_log SET SCHEMA audit;
  END IF;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'raw_ofgem_ens',
    'raw_ofgem_expenditure',
    'raw_ofgem_rore',
    'raw_ofgem_customer_metrics',
    'raw_ofgem_emissions',
    'raw_ons_energy_intensity',
    'raw_ons_sector_fuel_use',
    'raw_ons_regional_gva',
    'raw_ons_lcree',
    'raw_ons_intermediate_consumption',
    'raw_daily_market_prices'
  ]
  LOOP
    IF to_regclass('public.' || t) IS NOT NULL
       AND to_regclass('raw.' || t) IS NULL THEN
      EXECUTE format('ALTER TABLE public.%I SET SCHEMA raw', t);
    END IF;
  END LOOP;
END $$;

COMMIT;

-- ============================================================================
-- DOWN (manual rollback section)
-- Execute this block independently only when rollback is required.
-- ============================================================================
-- BEGIN;
--
-- DO $$
-- DECLARE t text;
-- BEGIN
--   FOREACH t IN ARRAY ARRAY[
--     'raw_ofgem_ens',
--     'raw_ofgem_expenditure',
--     'raw_ofgem_rore',
--     'raw_ofgem_customer_metrics',
--     'raw_ofgem_emissions',
--     'raw_ons_energy_intensity',
--     'raw_ons_sector_fuel_use',
--     'raw_ons_regional_gva',
--     'raw_ons_lcree',
--     'raw_ons_intermediate_consumption',
--     'raw_daily_market_prices'
--   ]
--   LOOP
--     IF to_regclass('raw.' || t) IS NOT NULL
--        AND to_regclass('public.' || t) IS NULL THEN
--       EXECUTE format('ALTER TABLE raw.%I SET SCHEMA public', t);
--     END IF;
--   END LOOP;
-- END $$;
--
-- DO $$
-- BEGIN
--   IF to_regclass('audit.etl_run_log') IS NOT NULL
--      AND to_regclass('public.etl_run_log') IS NULL THEN
--     ALTER TABLE audit.etl_run_log SET SCHEMA public;
--   END IF;
-- END $$;
--
-- COMMIT;

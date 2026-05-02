-- Wholesale market fact tables.
--
-- core_fact_market_prices  : observation-grain prices/spreads/volatility
-- core_fact_market_context : annualised generation mix, market shares,
--                            customer-cost roll-ups for mart_market_context.
--
-- These are populated by sql/core/40_load_facts.sql from stg_market_*.

CREATE TABLE IF NOT EXISTS core_fact_market_prices (
    market_price_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER REFERENCES core_dim_date(date_id),
    geography_id BIGINT REFERENCES core_dim_geography(geography_id),
    period_date DATE,
    period_label TEXT,
    year INTEGER NOT NULL,
    commodity TEXT NOT NULL,
    instrument TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_market_prices_uniq
        UNIQUE NULLS NOT DISTINCT (year, commodity, instrument, metric_name, period_label)
);

CREATE INDEX IF NOT EXISTS idx_core_fact_market_prices_yc
    ON core_fact_market_prices (year, commodity, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_market_context (
    market_context_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER REFERENCES core_dim_date(date_id),
    geography_id BIGINT REFERENCES core_dim_geography(geography_id),
    year INTEGER NOT NULL,
    commodity TEXT NOT NULL,
    fuel_source TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_market_context_uniq
        UNIQUE NULLS NOT DISTINCT (year, commodity, fuel_source, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_core_fact_market_context_yc
    ON core_fact_market_context (year, commodity, fuel_source);

-- A simple wholesale-share table fed by raw_xlsx_generation_share. Intentionally
-- separate from core_fact_market_context so 2024 snapshot stays attached to a
-- company rather than a fuel source.
CREATE TABLE IF NOT EXISTS core_fact_market_share (
    market_share_id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    commodity TEXT NOT NULL,
    company_name TEXT NOT NULL,
    share_pct NUMERIC,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_market_share_uniq
        UNIQUE (year, commodity, company_name)
);

CREATE TABLE IF NOT EXISTS core_fact_daily_prices (
    daily_price_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER REFERENCES core_dim_date(date_id),
    geography_id BIGINT REFERENCES core_dim_geography(geography_id),
    period_date DATE NOT NULL,
    commodity TEXT NOT NULL,
    source_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_daily_prices_uniq
        UNIQUE (period_date, commodity, source_name, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_core_fact_daily_prices_period
    ON core_fact_daily_prices (period_date, commodity, metric_name);

import argparse
from pathlib import Path

from pipeline.config.loader import load_settings
from pipeline.ingest.fetch_sources import fetch_all_sources
from pipeline.ingest.load_raw import load_all_raw_tables
from pipeline.ingest.load_xlsx import load_all_xlsx
from pipeline.utils.db import DbConfig, PostgresClient
from pipeline.utils.logging import setup_logger


def run_sql_folder(client: PostgresClient, folder: str) -> None:
    """Run every numbered (`NN_*.sql`) script in a folder in order.

    Files without a numeric prefix (e.g. ``healthcheck.sql``) are treated as
    on-demand tools and skipped here; pipeline.healthcheck calls them
    explicitly.
    """
    for sql_file in sorted(Path(folder).glob("*.sql")):
        if not sql_file.name[:1].isdigit():
            continue
        client.execute_file(str(sql_file))


def build_client(settings: dict) -> PostgresClient:
    db = settings["database"]
    cfg = DbConfig(
        host=db["host"],
        port=int(db["port"]),
        dbname=db["dbname"],
        user=db["user"],
        password_env_var=db["password_env_var"],
        connect_timeout=int(db.get("connect_timeout", 10)),
    )
    return PostgresClient(cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="UK Energy pipeline orchestrator")
    parser.add_argument(
        "command",
        choices=["ingest", "xlsx", "staging", "core", "marts", "full_refresh"],
        help=(
            "Stage to run. 'ingest' loads JSONB raw_ofgem_* / raw_ons_* via the "
            "registry CSV path; 'xlsx' loads typed raw_xlsx_* from the 38 Ofgem "
            "Data Portal Excel files; 'full_refresh' chains ingest -> xlsx -> "
            "staging -> core -> marts."
        ),
    )
    args = parser.parse_args()

    settings = load_settings()
    logger = setup_logger(settings["paths"]["log_dir"])
    fail_fast = bool(settings.get("pipeline", {}).get("fail_fast", False))
    client = None
    try:
        client = build_client(settings)
    except (ConnectionError, ValueError) as e:
        logger.error("%s", e)
        raise SystemExit(1) from e

    try:
        if args.command in {"ingest", "full_refresh"}:
            logger.info("Starting source fetch")
            try:
                fetch_all_sources(settings, logger)
            except Exception:
                logger.exception("fetch_all_sources failed")
                if fail_fast:
                    raise
            logger.info("Loading raw tables (JSONB sources)")
            load_all_raw_tables(settings, client, logger)
            client.commit()

        if args.command in {"xlsx", "full_refresh"}:
            logger.info("Loading raw xlsx tables (38 Ofgem Data Portal files)")
            load_all_xlsx(settings, client, logger)
            client.commit()

        if args.command in {"staging", "full_refresh"}:
            logger.info("Running staging SQL")
            run_sql_folder(client, "sql/staging")
            client.commit()

        if args.command in {"core", "full_refresh"}:
            logger.info("Running core SQL")
            run_sql_folder(client, "sql/core")
            run_sql_folder(client, "sql/checks")
            client.commit()

        if args.command in {"marts", "full_refresh"}:
            logger.info("Running mart SQL")
            run_sql_folder(client, "sql/marts")
            client.commit()

        logger.info("Pipeline command completed: %s", args.command)
    except Exception:
        if client is not None:
            client.rollback()
        logger.exception("Pipeline failed")
        raise
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()

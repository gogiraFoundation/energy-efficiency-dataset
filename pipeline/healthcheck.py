from pipeline.config.loader import load_settings
from pipeline.orchestrate import build_client


def main() -> None:
    settings = load_settings()
    client = build_client(settings)
    try:
        rows = client.fetchall(open("sql/checks/healthcheck.sql", "r", encoding="utf-8").read())
        print("layer\ttable_name\trow_count")
        for row in rows:
            print(f"{row['layer']}\t{row['table_name']}\t{row['row_count']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

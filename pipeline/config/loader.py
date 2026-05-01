import os
from pathlib import Path
import yaml


def _load_dotenv_if_present(dotenv_path: str = ".env", override_existing: bool = True) -> None:
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override_existing or key not in os.environ:
            os.environ[key] = value


def load_settings(settings_path: str = "pipeline/config/settings.yaml") -> dict:
    _load_dotenv_if_present()
    with Path(settings_path).open("r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    db = settings.get("database", {})
    env_overrides = {
        "host": os.getenv("UK_ENERGY_DB_HOST"),
        "port": os.getenv("UK_ENERGY_DB_PORT"),
        "dbname": os.getenv("UK_ENERGY_DB_NAME"),
        "user": os.getenv("UK_ENERGY_DB_USER"),
        "password_env_var": os.getenv("UK_ENERGY_DB_PASSWORD_ENV_VAR"),
    }
    for key, value in env_overrides.items():
        if value not in (None, ""):
            db[key] = int(value) if key == "port" else value
    settings["database"] = db
    return settings

import logging
from pathlib import Path


def setup_logger(log_dir: str, logger_name: str = "uk_energy_pipeline") -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(Path(log_dir) / f"{logger_name}.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

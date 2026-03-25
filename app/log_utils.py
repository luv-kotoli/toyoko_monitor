from __future__ import annotations

import logging
from collections import deque
from pathlib import Path


APP_LOG_FILE = "app.log"
PUSH_CONTENT_LOG_FILE = "serverchan.content.log"
PUSH_RESULT_LOG_FILE = "serverchan.result.log"

PUSH_CONTENT_LOGGER_NAME = "toyoko.serverchan.content"
PUSH_RESULT_LOGGER_NAME = "toyoko.serverchan.result"

LOG_SOURCES = (
    ("app", "应用日志", APP_LOG_FILE),
    ("push_content", "推送内容日志", PUSH_CONTENT_LOG_FILE),
    ("push_result", "推送结果日志", PUSH_RESULT_LOG_FILE),
)


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    _ensure_file_handler(root_logger, log_dir / APP_LOG_FILE, formatter)

    content_logger = logging.getLogger(PUSH_CONTENT_LOGGER_NAME)
    content_logger.setLevel(logging.INFO)
    content_logger.propagate = False
    _ensure_file_handler(content_logger, log_dir / PUSH_CONTENT_LOG_FILE, formatter)

    result_logger = logging.getLogger(PUSH_RESULT_LOGGER_NAME)
    result_logger.setLevel(logging.INFO)
    result_logger.propagate = False
    _ensure_file_handler(result_logger, log_dir / PUSH_RESULT_LOG_FILE, formatter)


def read_log_sections(log_dir: Path, *, line_count: int = 100) -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": label,
            "file_name": file_name,
            "content": tail_log_file(log_dir / file_name, line_count=line_count),
        }
        for key, label, file_name in LOG_SOURCES
    ]


def tail_log_file(path: Path, *, line_count: int = 100) -> str:
    if not path.exists():
        return "日志文件尚未生成。"

    with path.open("r", encoding="utf-8", errors="replace") as file:
        return "".join(deque(file, maxlen=line_count)).rstrip() or "日志文件当前为空。"


def _ensure_file_handler(logger: logging.Logger, path: Path, formatter: logging.Formatter) -> None:
    resolved_path = str(path.resolve())
    for handler in logger.handlers:
        if getattr(handler, "baseFilename", None) == resolved_path:
            return

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

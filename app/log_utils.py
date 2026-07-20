from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
import shutil


APP_LOG_FILE = "app.log"
PUSH_CONTENT_LOG_FILE = "push.content.log"
PUSH_RESULT_LOG_FILE = "push.result.log"
LEGACY_PUSH_CONTENT_LOG_FILE = "serverchan.content.log"
LEGACY_PUSH_RESULT_LOG_FILE = "serverchan.result.log"

PUSH_CONTENT_LOGGER_NAME = "toyoko.push.content"
PUSH_RESULT_LOGGER_NAME = "toyoko.push.result"

LOG_SOURCES = (
    ("app", "应用日志", APP_LOG_FILE, (APP_LOG_FILE,)),
    (
        "push_content",
        "推送内容日志",
        f"{PUSH_CONTENT_LOG_FILE} / {LEGACY_PUSH_CONTENT_LOG_FILE}",
        (LEGACY_PUSH_CONTENT_LOG_FILE, PUSH_CONTENT_LOG_FILE),
    ),
    (
        "push_result",
        "推送结果日志",
        f"{PUSH_RESULT_LOG_FILE} / {LEGACY_PUSH_RESULT_LOG_FILE}",
        (LEGACY_PUSH_RESULT_LOG_FILE, PUSH_RESULT_LOG_FILE),
    ),
)


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    _migrate_legacy_log_file(
        legacy_path=log_dir / LEGACY_PUSH_CONTENT_LOG_FILE,
        target_path=log_dir / PUSH_CONTENT_LOG_FILE,
    )
    _migrate_legacy_log_file(
        legacy_path=log_dir / LEGACY_PUSH_RESULT_LOG_FILE,
        target_path=log_dir / PUSH_RESULT_LOG_FILE,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    _ensure_file_handler(root_logger, log_dir / APP_LOG_FILE, formatter)

    # httpx logs complete request URLs at INFO. Keep routine requests out of the
    # application log so notification endpoints and query parameters stay private.
    logging.getLogger("httpx").setLevel(logging.WARNING)

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
            "content": tail_log_files(
                [log_dir / candidate_name for candidate_name in candidate_names],
                line_count=line_count,
            ),
        }
        for key, label, file_name, candidate_names in LOG_SOURCES
    ]


def tail_log_files(paths: list[Path], *, line_count: int = 100) -> str:
    existing_paths = [path for path in paths if path.exists()]
    if not existing_paths:
        return "日志文件尚未生成。"

    lines: deque[str] = deque(maxlen=line_count)
    for path in existing_paths:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            lines.extend(file)

    return "".join(lines).rstrip() or "日志文件当前为空。"


def _migrate_legacy_log_file(*, legacy_path: Path, target_path: Path) -> None:
    if not legacy_path.exists() or target_path.exists():
        return
    shutil.copyfile(legacy_path, target_path)


def _ensure_file_handler(logger: logging.Logger, path: Path, formatter: logging.Formatter) -> None:
    resolved_path = str(path.resolve())
    for handler in logger.handlers:
        if getattr(handler, "baseFilename", None) == resolved_path:
            return

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

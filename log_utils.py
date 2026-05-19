"""
两套独立的输出系统：
1. print_* → 终端 stdout only（简洁，面向用户）
2. logger.* → 文件 only（详细，面向开发者）
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"

_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def print_info(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    print(f"{_GREEN}{msg}{_RESET}", **kwargs)


def print_warn(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    print(f"{_YELLOW}{msg}{_RESET}", **kwargs)


def print_error(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    print(f"{_RED}{msg}{_RESET}", **kwargs)


def print_banner(title: str, char: str = "=", width: int = 70):
    print(f"\n{_CYAN}{char * width}{_RESET}")
    print(f"{_CYAN}  {title}{_RESET}")
    print(f"{_CYAN}{char * width}{_RESET}")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_file_logging(log_dir: str | None = None) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = log_dir or os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(
        log_dir, f"sentinel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return log_path

    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return log_path

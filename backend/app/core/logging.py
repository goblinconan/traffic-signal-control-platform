"""日志模块：统一 uvicorn 之外的业务日志格式。
输入：logger 名称。
输出：logging.Logger。
依赖：标准库 logging。
调用方：signal_service、sumo_runner、main。
"""
from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)

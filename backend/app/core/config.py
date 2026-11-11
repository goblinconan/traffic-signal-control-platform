"""配置模块：读取环境变量和默认仿真参数。
输入：环境变量 SUMO_HOME、SUMO_CONFIG、DATABASE_URL。
输出：Settings 单例。
依赖：pydantic-settings。
调用方：main.py、signal_service.py、sumo_runner.py。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "traffic-signal-control-platform"
    sumo_home: str | None = os.environ.get("SUMO_HOME", r"C:\Program Files (x86)\SUMO")
    sumo_config: str = str(
        Path(__file__).resolve().parents[3] / "simulation" / "config" / "intersection.sumocfg"
    )
    tls_id: str = "intersection_0"
    database_url: str = "postgresql+asyncpg://traffic:traffic@localhost:5432/traffic"
    sim_step_length: float = 0.5
    simulation_step_delay: float = 0.0  # 每步真实延迟，0 表示全速

    # 第一版默认配时（4个主相位 + 黄灯）
    ns_straight_green: float = 40.0
    ns_left_green: float = 20.0
    ew_straight_green: float = 40.0
    ew_left_green: float = 20.0
    yellow: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
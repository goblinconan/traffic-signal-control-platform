"""B4 真实 SUMO 集成测试：统一快照读取实际生命周期、TLS 和网络版本。"""
from __future__ import annotations

import asyncio
import os

import pytest

from app.core.config import get_settings
from app.services.signal_service import SignalService
from app.services.state_service import RuntimeStateService
from app.simulation.lifecycle import SimulationLifecycle
from app.simulation.sumo_runner import SumoRunner


@pytest.mark.integration
def test_real_sumo_unified_snapshot_matches_live_runtime_state():
    if os.environ.get("RUN_SUMO_INTEGRATION") != "1":
        pytest.skip("set RUN_SUMO_INTEGRATION=1 to run real SUMO B4 integration")

    async def run_test():
        settings = get_settings()
        runner = SumoRunner(settings)
        signal_service = SignalService.create(settings, runner)
        lifecycle = SimulationLifecycle(runner, signal_service)
        state_service = RuntimeStateService(lifecycle, signal_service, runner, settings)
        try:
            started = await lifecycle.start()
            assert started.status.value == "RUNNING"

            message = await state_service.create_message("simulation_snapshot")
            actual_tls = runner.get_tls_state(settings.tls_id)
            controlled_links = runner.controlled_links(settings.tls_id)

            assert message["type"] == "simulation_snapshot"
            assert message["simulation_status"] == "RUNNING"
            assert message["sumo_connected"] is True
            assert message["process_alive"] is True
            assert message["signal_control"]["phase_id"] == "NS_LEFT"
            assert message["signal_control"]["phase_index"] == 0
            assert len(actual_tls) == len(controlled_links)
            assert len(message["signal_control"]["groups"]) == 4
            assert len(message["signal_control"]["right_turns"]) == 4
            assert message["network_version"]
            assert message["sequence"] >= 1
        finally:
            await lifecycle.stop()

    asyncio.run(run_test())

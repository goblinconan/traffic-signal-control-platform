"""B3 真实 SUMO 集成测试：验证手动阶段切换时 ALL_RED 确实到达 SUMO。"""
from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.models.signal import ControlMode, PhaseId
from app.services.signal_service import SignalService
from app.simulation.sumo_runner import SumoRunner


@pytest.mark.integration
def test_real_sumo_manual_switch_holds_all_red_for_one_simulation_step():
    if os.environ.get("RUN_SUMO_INTEGRATION") != "1":
        pytest.skip("set RUN_SUMO_INTEGRATION=1 to run real SUMO B3 integration")

    settings = get_settings()
    runner = SumoRunner(settings)
    service = SignalService.create(settings, runner)

    try:
        runner.start()
        service.on_started()
        assert len(runner.get_tls_state(settings.tls_id)) == 20

        # AUTO -> MANUAL：完整执行当前绿灯、黄灯，全红实际下发后再完成模式切换。
        service.request_control_mode(ControlMode.MANUAL)
        for _ in range(2000):
            service.step()
            if service.controller.phase_id == PhaseId.ALL_RED:
                break
        assert service.controller.phase_id == PhaseId.ALL_RED
        assert runner.get_tls_state(settings.tls_id) == "r" * 20
        assert service.control_mode == ControlMode.AUTO

        service.step()
        assert service.control_mode == ControlMode.MANUAL
        assert service.controller.phase_id == PhaseId.ALL_RED
        assert runner.get_tls_state(settings.tls_id) == "r" * 20

        # 从 ALL_RED 启动 EW_LEFT，再请求 NS_STRAIGHT，必须经真实全红。
        accepted, reason = service.manual_switch(PhaseId.EW_LEFT)
        assert accepted is True
        assert reason == "started_from_all_red"
        assert service.controller.phase_id == PhaseId.EW_LEFT

        accepted, reason = service.manual_switch(PhaseId.NS_STRAIGHT)
        assert accepted is True
        assert reason == "accepted_after_safe_all_red"

        for _ in range(2000):
            service.step()
            if service.controller.phase_id == PhaseId.ALL_RED:
                break

        assert service.controller.phase_id == PhaseId.ALL_RED
        assert runner.get_tls_state(settings.tls_id) == "r" * 20

        # 关键安全断言：ALL_RED 已在 SUMO 实际保持一个 step。
        service.step()
        assert service.controller.phase_id == PhaseId.NS_STRAIGHT
        actual = runner.get_tls_state(settings.tls_id)
        assert len(actual) == 20
        assert {i for i, char in enumerate(actual) if char == "G"} == {
            1, 2, 11, 12
        }
    finally:
        runner.stop()

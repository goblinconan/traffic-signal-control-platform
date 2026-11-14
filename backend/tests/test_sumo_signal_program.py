
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NET_FILE = PROJECT_ROOT / "simulation" / "network" / "intersection.net.xml"
TLL_FILE = PROJECT_ROOT / "simulation" / "network" / "intersection.tll.xml"


def _phases(path: Path):
    root = ET.parse(path).getroot()
    logic = root.find("tlLogic")
    if logic is None:
        logic = root.find("tlLogics/tlLogic")
    assert logic is not None
    return [
        (float(phase.get("duration")), phase.get("state"))
        for phase in logic.findall("phase")
    ]


def test_net_and_standalone_tll_have_same_eight_phase_program():
    net_phases = _phases(NET_FILE)
    tll_phases = _phases(TLL_FILE)

    assert len(net_phases) == 8
    assert net_phases == tll_phases
    assert [duration for duration, _ in net_phases] == [
        20, 3, 40, 3, 20, 3, 40, 3
    ]
    assert all(len(state) == 20 for _, state in net_phases)


def test_static_signal_program_matches_approved_phase_order():
    phases = _phases(NET_FILE)
    expected_green_indices = [
        {3, 4, 13, 14},       # 南北左转
        set(),
        {1, 2, 11, 12},       # 南北直行
        set(),
        {8, 9, 18, 19},       # 东西左转
        set(),
        {6, 7, 16, 17},       # 东西直行
        set(),
    ]

    for (_, state), expected in zip(phases, expected_green_indices):
        actual = {index for index, color in enumerate(state) if color == "G"}
        if expected:
            assert actual == expected
        else:
            assert not actual

    # 四个右转 linkIndex 在所有阶段均使用小写 g（让行绿灯）。
    for _, state in phases:
        assert all(state[index] == "g" for index in (0, 5, 10, 15))

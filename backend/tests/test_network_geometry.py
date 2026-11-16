from pathlib import Path

import pytest

from app.simulation.network_geometry import load_network_geometry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NET_FILE = PROJECT_ROOT / "simulation" / "network" / "intersection.net.xml"


def test_load_network_geometry_parses_junctions_edges_and_internal_lanes():
    geometry = load_network_geometry(NET_FILE)
    assert geometry["junctions"]
    assert geometry["edges"]
    assert geometry["internal_lanes"]
    assert geometry["bounds"]["conv_boundary"]
    assert all("shape" in lane for edge in geometry["edges"] for lane in edge["lanes"])


def test_load_network_geometry_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_network_geometry(tmp_path / "missing.net.xml")


def test_load_network_geometry_uses_defaults_and_excludes_internal_edges(tmp_path):
    net_file = tmp_path / "minimal.net.xml"
    net_file.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<net>
    <junction id="J0"/>
    <edge id="normal_edge">
        <lane id="normal_0"/>
    </edge>
    <edge id=":internal_0" function="internal">
        <lane id=":internal_0_0" shape="0,0 1,1"/>
    </edge>
    <location convBoundary="0,0,10,10"/>
</net>
""",
        encoding="utf-8",
    )

    geometry = load_network_geometry(net_file)

    assert geometry["junctions"] == [
        {
            "id": "J0",
            "type": "",
            "x": 0.0,
            "y": 0.0,
            "shape": [],
        }
    ]

    assert len(geometry["edges"]) == 1
    assert geometry["edges"][0]["id"] == "normal_edge"
    assert geometry["edges"][0]["lanes"] == [
        {
            "id": "normal_0",
            "index": 0,
            "width": 3.2,
            "speed": 0.0,
            "shape": [],
        }
    ]

    assert geometry["internal_lanes"] == [
        {
            "id": ":internal_0_0",
            "width": 3.2,
            "shape": [
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 1.0},
            ],
        }
    ]


def test_load_network_geometry_skips_invalid_shape_coordinates(tmp_path):
    net_file = tmp_path / "invalid-shape.net.xml"
    net_file.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<net>
    <edge id="road_0">
        <lane id="road_0_0" shape="0,0 invalid 1,abc 2,2"/>
    </edge>
</net>
""",
        encoding="utf-8",
    )

    geometry = load_network_geometry(net_file)

    assert geometry["edges"][0]["lanes"][0]["shape"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 2.0, "y": 2.0},
    ]


@pytest.mark.parametrize(
    "lane_attributes",
    [
        'index="invalid"',
        'width="invalid"',
        'speed="invalid"',
    ],
)
def test_load_network_geometry_rejects_invalid_lane_attributes(
    tmp_path,
    lane_attributes,
):
    net_file = tmp_path / "invalid-lane.net.xml"
    net_file.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<net>
    <edge id="road_0">
        <lane id="road_0_0" {lane_attributes}/>
    </edge>
</net>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_network_geometry(net_file)

def test_load_network_geometry_skips_non_finite_shape_coordinates(tmp_path):
    net_file = tmp_path / "non-finite-shape.net.xml"
    net_file.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<net>
    <edge id="road_0">
        <lane
            id="road_0_0"
            shape="0,0 nan,1 2,inf 3,-inf 4,4"
        />
    </edge>
</net>
""",
        encoding="utf-8",
    )

    geometry = load_network_geometry(net_file)

    assert geometry["edges"][0]["lanes"][0]["shape"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 4.0, "y": 4.0},
    ]

@pytest.mark.parametrize(
    ("x", "y"),
    [
        ("nan", "0"),
        ("0", "inf"),
        ("-inf", "10"),
    ],
)
def test_load_network_geometry_rejects_non_finite_junction_coordinates(
    tmp_path,
    x,
    y,
):
    net_file = tmp_path / "non-finite-junction.net.xml"
    net_file.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<net>
    <junction id="J0" x="{x}" y="{y}"/>
</net>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="路口坐标"):
        load_network_geometry(net_file)
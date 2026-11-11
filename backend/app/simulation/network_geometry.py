
"""SUMO 路网几何解析模块。

从 SUMO 生成的 intersection.net.xml 读取道路、车道和路口几何。
静态几何只需在应用启动时加载一次。

输入：simulation/network/intersection.net.xml
输出：可通过 FastAPI JSON 序列化的路网几何字典。
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _parse_shape(shape_text: str | None) -> list[dict[str, float]]:
    """解析 SUMO shape 字符串为坐标数组。"""
    if not shape_text:
        return []

    points: list[dict[str, float]] = []

    for item in shape_text.strip().split():
        coordinates = item.split(",")

        if len(coordinates) < 2:
            continue

        try:
            points.append({
                "x": float(coordinates[0]),
                "y": float(coordinates[1]),
            })
        except ValueError:
            log.warning("忽略无效的 SUMO shape 坐标: %s", item)

    return points


def load_network_geometry(net_file: str | Path) -> dict[str, Any]:
    """读取 SUMO net.xml，提取前端绘制所需的静态几何。"""
    path = Path(net_file).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"SUMO 路网文件不存在: {path}")

    root = ET.parse(path).getroot()

    junctions: list[dict[str, Any]] = []

    for element in root.findall("junction"):
        junctions.append({
            "id": element.get("id", ""),
            "type": element.get("type", ""),
            "x": float(element.get("x", "0")),
            "y": float(element.get("y", "0")),
            "shape": _parse_shape(element.get("shape")),
        })

    edges: list[dict[str, Any]] = []

    for element in root.findall("edge"):
        edge_id = element.get("id", "")

        # 内部连接边以 ":" 开头，单独作为内部车道数据处理。
        if edge_id.startswith(":"):
            continue

        lanes: list[dict[str, Any]] = []

        for lane in element.findall("lane"):
            lanes.append({
                "id": lane.get("id", ""),
                "index": int(lane.get("index", "0")),
                "width": float(lane.get("width", "3.2")),
                "speed": float(lane.get("speed", "0")),
                "shape": _parse_shape(lane.get("shape")),
            })

        edges.append({
            "id": edge_id,
            "from": element.get("from", ""),
            "to": element.get("to", ""),
            "function": element.get("function", ""),
            "lanes": lanes,
        })

    internal_lanes: list[dict[str, Any]] = []

    for element in root.findall(".//edge[@function='internal']"):
        for lane in element.findall("lane"):
            internal_lanes.append({
                "id": lane.get("id", ""),
                "width": float(lane.get("width", "3.2")),
                "shape": _parse_shape(lane.get("shape")),
            })

    location = root.find("location")

    result = {
        "junctions": junctions,
        "edges": edges,
        "internal_lanes": internal_lanes,
        "bounds": {
            "conv_boundary": (
                location.get("convBoundary", "")
                if location is not None else ""
            ),
            "orig_boundary": (
                location.get("origBoundary", "")
                if location is not None else ""
            ),
        },
    }

    log.info(
        "SUMO 路网几何加载完成: junctions=%d, edges=%d, "
        "lanes=%d, internal_lanes=%d",
        len(junctions),
        len(edges),
        sum(len(edge["lanes"]) for edge in edges),
        len(internal_lanes),
    )

    return result

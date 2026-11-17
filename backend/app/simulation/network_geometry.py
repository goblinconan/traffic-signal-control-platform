"""SUMO 路网几何解析模块。

从 SUMO 生成的 intersection.net.xml 读取道路、车道和路口几何。
静态几何只需在应用启动时加载一次。

输入：simulation/network/intersection.net.xml
输出：可通过 FastAPI JSON 序列化的路网几何字典。
"""
from __future__ import annotations

import hashlib
import logging
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _parse_shape(shape_text: str | None) -> list[dict[str, float]]:
    """解析 SUMO shape 字符串为坐标数组，只保留有限数值坐标。"""
    if not shape_text:
        return []

    points: list[dict[str, float]] = []
    for item in shape_text.strip().split():
        coordinates = item.split(",")
        if len(coordinates) < 2:
            continue

        try:
            x = float(coordinates[0])
            y = float(coordinates[1])
        except ValueError:
            log.warning("忽略无效的 SUMO shape 坐标: %s", item)
            continue

        if not math.isfinite(x) or not math.isfinite(y):
            log.warning("忽略非有限的 SUMO shape 坐标: %s", item)
            continue

        points.append({"x": x, "y": y})

    return points


def get_network_version(net_file: str | Path) -> str:
    """以 net.xml 内容 SHA256 标识静态路网版本。"""
    path = Path(net_file).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SUMO 路网文件不存在: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_network_file(sumo_config: str | Path) -> Path:
    """从 SUMO 配置文件解析 net.xml 的绝对路径。"""
    config_path = Path(sumo_config).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"SUMO 配置文件不存在: {config_path}")
    root = ET.parse(config_path).getroot()
    net_element = root.find("./input/net-file")
    if net_element is None or not net_element.get("value"):
        raise ValueError("SUMO 配置文件缺少有效的 input/net-file")
    net_path = Path(net_element.get("value", ""))
    if not net_path.is_absolute():
        net_path = (config_path.parent / net_path).resolve()
    if not net_path.is_file():
        raise FileNotFoundError(f"SUMO 路网文件不存在: {net_path}")
    return net_path


def load_network_geometry(net_file: str | Path) -> dict[str, Any]:
    """读取 SUMO net.xml，提取前端绘制所需的静态几何。"""
    path = Path(net_file).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SUMO 路网文件不存在: {path}")

    root = ET.parse(path).getroot()
    junctions: list[dict[str, Any]] = []
    for element in root.findall("junction"):
        junction_id = element.get("id", "")
        x = float(element.get("x", "0"))
        y = float(element.get("y", "0"))

        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(
                f"路口坐标包含非有限数值: junction={junction_id}, x={x}, y={y}"
            )

        junctions.append({
            "id": junction_id,
            "type": element.get("type", ""),
            "x": x,
            "y": y,
            "shape": _parse_shape(element.get("shape")),
        })

    edges: list[dict[str, Any]] = []
    for element in root.findall("edge"):
        edge_id = element.get("id", "")
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
        "network_version": get_network_version(path),
        "junctions": junctions,
        "edges": edges,
        "internal_lanes": internal_lanes,
        "bounds": {
            "conv_boundary": location.get("convBoundary", "") if location is not None else "",
            "orig_boundary": location.get("origBoundary", "") if location is not None else "",
        },
    }
    log.info(
        "SUMO 路网几何加载完成: junctions=%d, edges=%d, lanes=%d, internal_lanes=%d",
        len(junctions), len(edges), sum(len(edge["lanes"]) for edge in edges), len(internal_lanes),
    )
    return result

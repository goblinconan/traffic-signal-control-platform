"""路口静态网络资源 REST 接口。
输入：intersection_id。
输出：带内容版本号的 SUMO 静态路网几何。
依赖：RuntimeStateService。
调用方：前端二维/三维视图资源加载。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.runtime_state import NetworkResource

router = APIRouter(prefix="/intersections", tags=["intersections"])


@router.get("/{intersection_id}/network", response_model=NetworkResource)
async def get_network(intersection_id: str, request: Request) -> dict:
    state_service = request.app.state.state_service
    if intersection_id != state_service.intersection_id:
        raise HTTPException(status_code=404, detail="unknown intersection_id")
    try:
        return await request.app.state.lifecycle.read_state(state_service.network_resource)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

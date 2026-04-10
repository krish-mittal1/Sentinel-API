import httpx 
from fastapi import APIRouter, Request, Response, HTTPException

from ..config import settings

router = APIRouter()

SERVICE_MAP = {
    "/auth": settings.AUTH_SERVICE_URL,
    "/users": settings.USER_SERVICE_URL,
    "/rest": settings.DATA_SERVICE_URL,
}

async def _proxy(request: Request, service_url: str, path: str) -> Response:
    target_url = f"{service_url}/{path}"

    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ("host", "content-length", "transfer-encoding"):
            headers[key] = value

    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Downstream service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Downstream service timeout")

    excluded = {"content-encoding", "content-length", "transfer-encoding"}
    resp_headers = {
        k: v for k, v in response.headers.items() if k.lower() not in excluded
    }

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=resp_headers,
    )

@router.api_route(
    "/auth/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_auth(request: Request, path: str):
    return await _proxy(request, settings.AUTH_SERVICE_URL, path)

@router.api_route(
    "/users/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_users(request: Request, path: str):
    return await _proxy(request, settings.USER_SERVICE_URL, path)

@router.api_route(
    "/users",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_users_root(request: Request):
    return await _proxy(request, settings.USER_SERVICE_URL, "")

@router.api_route(
    "/rest/v1/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_data_api(request: Request, path: str):
    return await _proxy(request, settings.DATA_SERVICE_URL, f"rest/v1/{path}")

@router.api_route(
    "/rest/v1",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_data_api_root(request: Request):
    return await _proxy(request, settings.DATA_SERVICE_URL, "rest/v1")

import os
import time
from uuid import uuid4 
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from fastapi.responses import JSONResponse


app = FastAPI()

POD = os.environ.get("POD_ID", "local")
DATACENTER = os.environ.get("DATACENTER", "local")
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latency of HTTP requests",
    labelnames=["pod", "datacenter", "handler"],
)
REQUESTS = Counter(
    "http_requests_total",
    "HTTP responses",
    labelnames=["pod", "datacenter", "handler", "status"],
)
SKIP = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/handlers", "/docs/oauth2-redirect"}

items: dict[str, dict] = {}

class Item(BaseModel):
    name: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/items")
def create_item(body: Item):
    item_id = str(uuid4())
    item = {"id": item_id, "name": body.name}
    items[item_id] = item
    return item

@app.get("/items/{item_id}")
def get_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]

@app.put("/items/{item_id}")
def update_item(item_id: str, body: Item):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    items[item_id] = {"id": item_id, "name": body.name}
    return items[item_id]

@app.delete("/items/{item_id}")
def delete_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    del items[item_id]

@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    forced = request.headers.get("x-force-status")
    if forced in {"404", "500"}:
        response = JSONResponse(status_code=int(forced), content={"detail": "forced error"})
    route = request.scope.get("route")
    if route is None or route.path in SKIP:
        return response
    handler = f"{request.method} {route.path}"
    elapsed = time.perf_counter() - started
    REQUEST_LATENCY.labels(pod=POD, datacenter=DATACENTER, handler=handler).observe(elapsed)
    REQUESTS.labels(
        pod=POD,
        datacenter=DATACENTER,
        handler=handler,
        status=str(response.status_code),
    ).inc()
    return response

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/handlers")
def list_handlers():
    found = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods or route.path in SKIP or route.path == "/handlers":
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            found.append(f"{method} {route.path}")
    return found


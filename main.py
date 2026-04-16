import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api import kb, query, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag.main")

app = FastAPI(title="LightRAG Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    latency = int((time.time() - start) * 1000)
    logger.info("%s %s %d %dms", request.method, request.url.path, response.status_code, latency)
    return response

app.include_router(health.router, prefix="/api")
app.include_router(kb.router, prefix="/api/kb")
app.include_router(query.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_excludes=[".venv", "data"])
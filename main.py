import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api import kb, query, health
from core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag.main")

if settings.internal_secret == "hello":
    logger.warning("⚠️  INTERNAL_SECRET 使用默认值 'hello'，请在生产环境中设置强密钥！")
if not settings.default_index_api_key:
    logger.warning("⚠️  DEFAULT_INDEX_API_KEY 未设置，索引功能将不可用")
if not settings.default_embedding_api_key:
    logger.warning("⚠️  DEFAULT_EMBEDDING_API_KEY 未设置，向量检索功能将不可用")

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
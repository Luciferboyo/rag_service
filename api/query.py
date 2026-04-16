import time
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from models.schemas import QueryRequest, QueryResponse
from services import rag_manager
from api.deps import verify_token

router = APIRouter(tags=["查询"])
logger = logging.getLogger("rag.query")


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(verify_token)])
async def query(req: QueryRequest):
    if not req.tenantId:
        raise HTTPException(400, "tenantId 不能为空")
    if not req.question.strip():
        raise HTTPException(400, "question 不能为空")

    trace_id = req.traceId or str(uuid.uuid4())
    kb_id = req.kbId or "default"
    start = time.time()

    logger.info("Query start | trace=%s tenant=%s kb=%s mode=%s q=%s",
                trace_id, req.tenantId, kb_id, req.mode.value, req.question[:50])

    try:
        result = await rag_manager.query(
            tenant_id=req.tenantId,
            kb_id=kb_id,
            question=req.question,
            mode=req.mode.value,
            top_k=req.topK,
            query_model_cfg=req.queryModel,
        )
    except Exception as e:
        logger.error("Query failed | trace=%s tenant=%s kb=%s error=%s", trace_id, req.tenantId, kb_id, str(e))
        raise HTTPException(500, f"查询失败: {str(e)}")

    latency = int((time.time() - start) * 1000)
    logger.info("Query done | trace=%s tenant=%s kb=%s latency=%dms", trace_id, req.tenantId, kb_id, latency)

    return QueryResponse(
        traceId=trace_id,
        answer=result["answer"],
        sources=result.get("sources", []),
        entities=result.get("entities", []),
        latencyMs=latency,
    )

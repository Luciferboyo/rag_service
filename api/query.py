import time
import uuid
from fastapi import APIRouter, HTTPException
from models.schemas import QueryRequest, QueryResponse
from services import rag_manager

router = APIRouter(tags=["查询"])


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    if not req.tenantId:
        raise HTTPException(400, "tenantId 不能为空")
    if not req.question.strip():
        raise HTTPException(400, "question 不能为空")

    trace_id = req.traceId or str(uuid.uuid4())
    kb_id = req.kbId or "default"
    start = time.time()

    try:
        result = await rag_manager.query(
            tenant_id=req.tenantId,
            kb_id=kb_id,
            question=req.question,
            mode=req.mode.value,
            top_k=req.topK,
            query_model_cfg=req.queryModel,  # 请求级别覆盖模型
        )
    except Exception as e:
        raise HTTPException(500, f"查询失败: {str(e)}")

    return QueryResponse(
        traceId=trace_id,
        answer=result["answer"],
        sources=result.get("sources", []),
        entities=result.get("entities", []),
        latencyMs=int((time.time() - start) * 1000),
    )
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional
from models.schemas import CreateKbRequest, KbResponse, UploadResponse, RagModelConfig
from services import parser, chunker, rag_manager
from api.deps import verify_token
import json

router = APIRouter(tags=["知识库"])


@router.post("/create", response_model=KbResponse, dependencies=[Depends(verify_token)])
async def create_kb(req: CreateKbRequest):
    kb_id = f"kb_{uuid.uuid4().hex[:12]}"
    # 预初始化实例（验证模型配置是否可用）
    await rag_manager.get_or_create(req.tenantId, kb_id, req.modelConfig)
    return KbResponse(
        kbId=kb_id,
        tenantId=req.tenantId,
        name=req.name,
        description=req.description,
    )


@router.post("/{kb_id}/upload", response_model=UploadResponse,dependencies=[Depends(verify_token)])
async def upload_document(
    kb_id: str,
    tenantId: str = Form(...),
    file: UploadFile = File(...),
    # 用户可以上传时指定模型配置（JSON 字符串）
    modelConfig: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB 限制
        raise HTTPException(400, "文件不能超过 50MB")

    # 解析文档 → 文本
    try:
        text = parser.parse(file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(text.strip()) < 20:
        raise HTTPException(400, "文档内容为空或解析失败")

    # 语义分块
    chunks = chunker.chunk_document(file.filename, text)
    if not chunks:
        raise HTTPException(400, "文档分块失败，内容太少")

    # 解析可选的模型配置
    cfg = None
    if modelConfig:
        try:
            cfg = RagModelConfig.model_validate(json.loads(modelConfig))
        except Exception:
            raise HTTPException(400, "modelConfig 格式错误")

    # 插入知识图谱（异步，可能耗时几十秒）
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    try:
        count = await rag_manager.insert_chunks(tenantId, kb_id, chunks, cfg)
    except Exception as e:
        raise HTTPException(500, f"索引失败: {str(e)}")

    return UploadResponse(
        docId=doc_id,
        fileName=file.filename,
        chunkCount=count,
        status="indexed",
    )


@router.delete("/{kb_id}",dependencies=[Depends(verify_token)])
async def delete_kb(kb_id: str, tenantId: str):
    await rag_manager.delete_kb(tenantId, kb_id)
    return {"ok": True}
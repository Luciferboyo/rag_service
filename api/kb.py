import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional
from models.schemas import CreateKbRequest, KbResponse, UploadResponse, RagModelConfig, KbDetail, DocItem
from services import parser, chunker, rag_manager
from services import meta_store
from api.deps import verify_token
import json

router = APIRouter(tags=["知识库"])


@router.post("/create", response_model=KbResponse, dependencies=[Depends(verify_token)])
async def create_kb(req: CreateKbRequest):
    kb_id = f"kb_{uuid.uuid4().hex[:12]}"
    await rag_manager.get_or_create(req.tenantId, kb_id, req.modelConfig)
    await meta_store.create_kb(req.tenantId, kb_id, req.name, req.description)
    return KbResponse(
        kbId=kb_id,
        tenantId=req.tenantId,
        name=req.name,
        description=req.description,
    )


@router.get("/list", response_model=list[KbDetail], dependencies=[Depends(verify_token)])
async def list_kbs(tenantId: str):
    kbs = meta_store.list_kbs(tenantId)
    return [
        KbDetail(
            kbId=kb["kbId"],
            name=kb["name"],
            description=kb.get("description"),
            createdAt=kb["createdAt"],
            docs=[DocItem(**d) for d in kb.get("docs", [])],
        )
        for kb in kbs
    ]


@router.get("/{kb_id}/docs", response_model=list[DocItem], dependencies=[Depends(verify_token)])
async def list_docs(kb_id: str, tenantId: str):
    docs = meta_store.list_docs(tenantId, kb_id)
    return [DocItem(**d) for d in docs]


@router.post("/{kb_id}/upload", response_model=UploadResponse, dependencies=[Depends(verify_token)])
async def upload_document(
    kb_id: str,
    tenantId: str = Form(...),
    file: UploadFile = File(...),
    modelConfig: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过 50MB")

    try:
        text = parser.parse(file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(text.strip()) < 20:
        raise HTTPException(400, "文档内容为空或解析失败")

    chunks = chunker.chunk_document(file.filename, text)
    if not chunks:
        raise HTTPException(400, "文档分块失败，内容太少")

    cfg = None
    if modelConfig:
        try:
            cfg = RagModelConfig.model_validate(json.loads(modelConfig))
        except Exception:
            raise HTTPException(400, "modelConfig 格式错误")

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    try:
        count = await rag_manager.insert_chunks(tenantId, kb_id, chunks, cfg)
    except Exception as e:
        raise HTTPException(500, f"索引失败: {str(e)}")

    await meta_store.add_doc(tenantId, kb_id, doc_id, file.filename, count)

    return UploadResponse(
        docId=doc_id,
        fileName=file.filename,
        chunkCount=count,
        status="indexed",
    )


@router.delete("/{kb_id}", dependencies=[Depends(verify_token)])
async def delete_kb(kb_id: str, tenantId: str):
    await rag_manager.delete_kb(tenantId, kb_id)
    await meta_store.delete_kb(tenantId, kb_id)
    return {"ok": True}

import uuid
import hashlib
import logging
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException, Depends
from typing import Optional, List
from models.schemas import CreateKbRequest, KbResponse, PatchKbRequest, UploadResponse, RagModelConfig, KbDetail, DocItem
from services import parser, chunker, rag_manager
from services import meta_store
from api.deps import verify_token
import json

logger = logging.getLogger("rag.kb")

router = APIRouter(tags=["知识库"])


async def _do_index(
    tenant_id: str,
    kb_id: str,
    doc_id: str,
    chunks: list[str],
    cfg: RagModelConfig | None,
    rag_doc_ids: list[str],
):
    try:
        await rag_manager.insert_chunks(tenant_id, kb_id, chunks, cfg, rag_doc_ids)
        await meta_store.update_doc_status(tenant_id, kb_id, doc_id, "indexed")
        logger.info("Indexing done | tenant=%s kb=%s doc=%s", tenant_id, kb_id, doc_id)
    except Exception as e:
        logger.error("Indexing failed | tenant=%s kb=%s doc=%s error=%s", tenant_id, kb_id, doc_id, str(e))
        await meta_store.update_doc_status(tenant_id, kb_id, doc_id, "error", error=str(e))


@router.post("/create", response_model=KbResponse, dependencies=[Depends(verify_token)])
async def create_kb(req: CreateKbRequest):
    kb_id = f"kb_{uuid.uuid4().hex[:12]}"
    await rag_manager.get_or_create(req.tenantId, kb_id, req.modelConfig)
    model_config_dict = req.modelConfig.model_dump(mode="json") if req.modelConfig else None
    await meta_store.create_kb(req.tenantId, kb_id, req.name, req.description, model_config_dict)
    logger.info("KB created | tenant=%s kb=%s name=%s", req.tenantId, kb_id, req.name)
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


@router.patch("/{kb_id}", response_model=KbResponse, dependencies=[Depends(verify_token)])
async def patch_kb(kb_id: str, req: PatchKbRequest):
    if not meta_store.kb_exists(req.tenantId, kb_id):
        raise HTTPException(404, f"知识库 {kb_id} 不存在")
    if req.name is None and req.description is None:
        raise HTTPException(400, "name 和 description 至少提供一个")
    await meta_store.update_kb(req.tenantId, kb_id, req.name, req.description)
    kb = meta_store.get_kb(req.tenantId, kb_id)
    logger.info("KB updated | tenant=%s kb=%s", req.tenantId, kb_id)
    return KbResponse(kbId=kb_id, tenantId=req.tenantId, name=kb["name"], description=kb.get("description"))


@router.get("/{kb_id}/docs", response_model=list[DocItem], dependencies=[Depends(verify_token)])
async def list_docs(kb_id: str, tenantId: str):
    if not meta_store.kb_exists(tenantId, kb_id):
        raise HTTPException(404, f"知识库 {kb_id} 不存在")
    docs = meta_store.list_docs(tenantId, kb_id)
    return [DocItem(**d) for d in docs]


@router.post("/{kb_id}/upload", response_model=List[UploadResponse], dependencies=[Depends(verify_token)])
async def upload_document(
    kb_id: str,
    background_tasks: BackgroundTasks,
    tenantId: str = Form(...),
    files: List[UploadFile] = File(...),
    modelConfig: Optional[str] = Form(None),
):
    if not meta_store.kb_exists(tenantId, kb_id):
        raise HTTPException(404, f"知识库 {kb_id} 不存在")

    cfg = None
    if modelConfig:
        try:
            cfg = RagModelConfig.model_validate(json.loads(modelConfig))
        except Exception:
            raise HTTPException(400, "modelConfig 格式错误")

    results = []
    for file in files:
        if not file.filename:
            raise HTTPException(400, "文件名不能为空")

        file_bytes = await file.read()
        if len(file_bytes) > 50 * 1024 * 1024:
            raise HTTPException(400, f"文件 {file.filename} 不能超过 50MB")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        existing = meta_store.get_doc_by_hash(tenantId, kb_id, file_hash)
        if existing:
            raise HTTPException(409, f"文件 {file.filename} 内容已存在，docId={existing['docId']}")

        try:
            text = parser.parse(file.filename, file_bytes)
        except ValueError as e:
            raise HTTPException(400, str(e))

        if len(text.strip()) < 20:
            raise HTTPException(400, f"文档 {file.filename} 内容为空或解析失败")

        chunks = chunker.chunk_document(file.filename, text)
        if not chunks:
            raise HTTPException(400, f"文档 {file.filename} 分块失败，内容太少")

        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        rag_doc_ids = [f"{doc_id}_{i}" for i in range(len(chunks))]

        await meta_store.add_doc(tenantId, kb_id, doc_id, file.filename, len(chunks), rag_doc_ids, status="indexing", file_hash=file_hash)
        background_tasks.add_task(_do_index, tenantId, kb_id, doc_id, chunks, cfg, rag_doc_ids)
        logger.info("Indexing queued | tenant=%s kb=%s file=%s doc=%s chunks=%d", tenantId, kb_id, file.filename, doc_id, len(chunks))

        results.append(UploadResponse(
            docId=doc_id,
            fileName=file.filename,
            chunkCount=len(chunks),
            status="indexing",
        ))

    return results


@router.get("/{kb_id}/docs/{doc_id}/status", response_model=DocItem, dependencies=[Depends(verify_token)])
async def get_doc_status(kb_id: str, doc_id: str, tenantId: str):
    if not meta_store.kb_exists(tenantId, kb_id):
        raise HTTPException(404, f"知识库 {kb_id} 不存在")
    doc = meta_store.get_doc(tenantId, kb_id, doc_id)
    if doc is None:
        raise HTTPException(404, f"文档 {doc_id} 不存在")
    return DocItem(**doc)


@router.delete("/{kb_id}/docs/{doc_id}", dependencies=[Depends(verify_token)])
async def delete_doc(kb_id: str, doc_id: str, tenantId: str):
    if not meta_store.kb_exists(tenantId, kb_id):
        raise HTTPException(404, f"知识库 {kb_id} 不存在")
    doc = meta_store.get_doc(tenantId, kb_id, doc_id)
    if doc is None:
        raise HTTPException(404, f"文档 {doc_id} 不存在")
    if doc.get("status") == "indexing":
        raise HTTPException(409, f"文档 {doc_id} 正在索引中，请等待完成后再删除")

    rag_doc_ids = doc.get("ragDocIds", [])
    if rag_doc_ids:
        try:
            await rag_manager.delete_document(tenantId, kb_id, rag_doc_ids)
        except Exception as e:
            # LightRAG 侧删除失败只记 warning，继续清理 meta，避免数据永久不一致
            logger.warning("Doc delete partial failure | tenant=%s kb=%s doc=%s error=%s", tenantId, kb_id, doc_id, str(e))

    await meta_store.delete_doc(tenantId, kb_id, doc_id)
    logger.info("Doc deleted | tenant=%s kb=%s doc=%s", tenantId, kb_id, doc_id)
    return {"ok": True}


@router.delete("/{kb_id}", dependencies=[Depends(verify_token)])
async def delete_kb(kb_id: str, tenantId: str):
    if not meta_store.kb_exists(tenantId, kb_id):
        raise HTTPException(404, f"知识库 {kb_id} 不存在")
    await rag_manager.delete_kb(tenantId, kb_id)
    await meta_store.delete_kb(tenantId, kb_id)
    logger.info("KB deleted | tenant=%s kb=%s", tenantId, kb_id)
    return {"ok": True}

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class QueryMode(str, Enum):
    low = "low"       # 实体检索（精确匹配）
    high = "high"     # 概念检索（语义相似）
    hybrid = "hybrid" # 双层混合（推荐）

# ── 模型配置（用户可选） ─────────────────────────────────────

class ModelConfig(BaseModel):
    """单个模型配置（BaseURL + Key + Model 三件套）"""
    baseUrl: str
    apiKey: str
    model: str

class RagModelConfig(BaseModel):
    """三个独立的模型配置"""
    index: Optional[ModelConfig] = None      # 索引模型（建图谱用）
    query: Optional[ModelConfig] = None      # 查询模型（回答问题用）
    embedding: Optional[ModelConfig] = None  # Embedding 模型

# ── 知识库 ───────────────────────────────────────────────────

class CreateKbRequest(BaseModel):
    tenantId: str
    name: str
    description: Optional[str] = None
    modelConfig: Optional[RagModelConfig] = None  # 可覆盖默认模型

class KbResponse(BaseModel):
    kbId: str
    tenantId: str
    name: str
    description: Optional[str] = None

# ── 上传 ─────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    docId: str
    fileName: str
    chunkCount: int
    status: str  # "indexing" | "indexed" | "error"
    message: Optional[str] = None

# ── 查询 ─────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    traceId: Optional[str] = None
    tenantId: str
    kbId: Optional[str] = None
    question: str
    mode: QueryMode = QueryMode.hybrid
    topK: int = Field(default=5, ge=1, le=20)
    # 用户可在请求级别覆盖查询模型
    queryModel: Optional[ModelConfig] = None

class SourceItem(BaseModel):
    content: str
    docName: str
    score: float

class QueryResponse(BaseModel):
    traceId: Optional[str] = None
    answer: str
    sources: List[SourceItem] = []
    entities: List[str] = []
    tokenUsage: dict = {}
    cached: bool = False
    latencyMs: int = 0

# ── KB 列表 / 文档列表 ────────────────────────────────────────

class DocItem(BaseModel):
    docId: str
    fileName: str
    chunkCount: int
    uploadedAt: str

class KbDetail(BaseModel):
    kbId: str
    name: str
    description: Optional[str] = None
    createdAt: str
    docs: List[DocItem] = []

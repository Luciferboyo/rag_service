from pydantic import BaseModel, Field
from typing import Optional, List, Generic, TypeVar
from enum import Enum

T = TypeVar("T")

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
    tenantId: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    modelConfig: Optional[RagModelConfig] = None  # 可覆盖默认模型

class KbResponse(BaseModel):
    kbId: str
    tenantId: str
    name: str
    description: Optional[str] = None

class PatchKbRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

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
    tenantId: str = Field(min_length=1)
    kbId: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2000)
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
    latencyMs: int = 0

# ── KB 列表 / 文档列表 ────────────────────────────────────────

class DocItem(BaseModel):
    docId: str
    fileName: str
    chunkCount: int
    uploadedAt: str
    status: str = "indexed"          # "indexing" | "indexed" | "error"
    error: Optional[str] = None

class KbSummary(BaseModel):
    """知识库列表视图：只含文档数量，不含完整文档列表"""
    kbId: str
    name: str
    description: Optional[str] = None
    createdAt: str
    docCount: int = 0

class KbDetail(BaseModel):
    """知识库详情视图：含完整文档列表"""
    kbId: str
    name: str
    description: Optional[str] = None
    createdAt: str
    docs: List[DocItem] = []

class PagedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    pageSize: int
    items: List[T]

# Python RAG Service

基于 [LightRAG](https://github.com/HKUDS/LightRAG) 构建的多租户知识库检索增强生成（RAG）服务，提供文档上传、知识图谱索引与 LLM 问答能力，通过 REST API 对外暴露。

---

## 目录

- [功能特性](#功能特性)
- [架构概览](#架构概览)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [API 文档](#api-文档)
- [查询模式说明](#查询模式说明)
- [模型配置](#模型配置)
- [Docker 部署](#docker-部署)
- [项目结构](#项目结构)

---

## 功能特性

- **多租户隔离**：每个 `(tenantId, kbId)` 拥有独立的向量库与知识图谱
- **文档解析**：支持 PDF、TXT、Markdown，自动语义分块（512 token / 50 overlap）
- **异步索引**：上传后立即返回，后台建图，通过状态接口轮询进度
- **灵活模型**：索引、查询、嵌入模型均可独立配置（KB 级别或请求级别），支持任意 OpenAI 兼容 API
- **多种检索模式**：实体检索（low）、语义检索（high）、混合检索（hybrid）
- **知识图谱 + 向量双引擎**：由 LightRAG 提供，检索质量优于纯向量方案
- **重复文档防护**：基于文件内容 SHA-256 去重，避免知识图谱冗余
- **文档级删除**：可单独删除某篇文档，无需重建整个知识库
- **查询超时保护**：LLM 无响应超过阈值时返回 504，防止请求永久挂起
- **列表分页**：KB 列表与文档列表均支持分页，适合大规模场景

---

## 架构概览

```
┌─────────────┐     REST API      ┌──────────────────────────────────────┐
│   调用方     │ ───────────────▶  │  FastAPI  (main.py)                   │
└─────────────┘                   │                                        │
                                  │  /api/health   /api/kb   /api/query   │
                                  └────────────────┬─────────────────────┘
                                                   │
                              ┌────────────────────┼────────────────────┐
                              ▼                    ▼                    ▼
                        parser.py            chunker.py          rag_manager.py
                     (PDF/TXT/MD 解析)    (语义分块 512 tokens)  (LightRAG 实例管理)
                                                                        │
                                                          ┌─────────────┴─────────────┐
                                                          ▼                           ▼
                                                   向量检索 (high)          知识图谱 (low)
                                                          └─────────────┬─────────────┘
                                                                        ▼
                                                                  LLM 生成答案
                                                                (model_factory.py)
```

**数据存储路径**：`./data/{tenantId}/{kbId}/`

---

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> PDF 解析依赖 `PyMuPDF`，Windows/Mac 通过 pip 直接安装；Linux 需要系统库，参见 [Dockerfile](Dockerfile)。

### 2. 配置环境变量

复制并编辑 `.env`：

```bash
cp .env.example .env
```

最少需要填写以下 key（见[环境变量](#环境变量)）：

```
DEFAULT_INDEX_API_KEY=sk-...
DEFAULT_EMBEDDING_API_KEY=sk-...
INTERNAL_SECRET=your-strong-secret
```

### 3. 启动服务

```bash
python main.py
# 默认监听 http://0.0.0.0:8000
```

### 4. 运行测试

```bash
pip install -r requirements-dev.txt
python -m pytest
```

### 5. 快速验证

```bash
# 健康检查
curl http://localhost:8000/api/health

# 创建知识库
curl -X POST http://localhost:8000/api/kb/create \
  -H "Authorization: Bearer your-secret" \
  -H "Content-Type: application/json" \
  -d '{"tenantId": "demo", "name": "测试知识库"}'

# 上传文档（异步，立即返回）
curl -X POST http://localhost:8000/api/kb/{kbId}/upload \
  -H "Authorization: Bearer your-secret" \
  -F "tenantId=demo" \
  -F "files=@your_document.pdf"

# 轮询索引状态
curl "http://localhost:8000/api/kb/{kbId}/docs/{docId}/status?tenantId=demo" \
  -H "Authorization: Bearer your-secret"

# 提问
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer your-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "demo",
    "kbId": "{kbId}",
    "question": "文档的主要内容是什么？",
    "mode": "hybrid"
  }'
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_INDEX_BASE_URL` | `https://openrouter.ai/api/v1` | 索引/建图 LLM 的 API 地址 |
| `DEFAULT_INDEX_API_KEY` | — | 索引 LLM 的鉴权 Key |
| `DEFAULT_INDEX_MODEL` | `deepseek/deepseek-chat` | 索引模型名称 |
| `DEFAULT_QUERY_BASE_URL` | `https://openrouter.ai/api/v1` | 问答 LLM 的 API 地址 |
| `DEFAULT_QUERY_API_KEY` | — | 问答 LLM 的鉴权 Key |
| `DEFAULT_QUERY_MODEL` | `openai/gpt-4o-mini` | 问答模型名称 |
| `DEFAULT_EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | 嵌入模型 API 地址 |
| `DEFAULT_EMBEDDING_API_KEY` | — | 嵌入模型鉴权 Key |
| `DEFAULT_EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型名称 |
| `DEFAULT_EMBEDDING_DIM` | `1536` | 嵌入向量维度 |
| `COSINE_THRESHOLD` | `0.5` | 向量检索最低相似度阈值（0.0–1.0） |
| `QUERY_TIMEOUT` | `120` | 查询超时秒数，超时返回 504 |
| `STORAGE_DIR` | `./data` | 知识库数据存储根目录 |
| `INTERNAL_SECRET` | `hello` | 内部服务鉴权 Token（**生产环境务必修改**） |

---

## API 文档

所有接口均需在请求头中携带：
```
Authorization: Bearer {INTERNAL_SECRET}
```

---

### `GET /api/health`

健康检查，无需鉴权。

**响应**：`{ "status": "ok" }`

---

### `POST /api/kb/create`

创建知识库。

**请求体**：
```json
{
  "tenantId": "your_tenant",
  "name": "知识库名称",
  "description": "可选描述",
  "modelConfig": {
    "index":     { "baseUrl": "...", "apiKey": "...", "model": "..." },
    "query":     { "baseUrl": "...", "apiKey": "...", "model": "..." },
    "embedding": { "baseUrl": "...", "apiKey": "...", "model": "..." }
  }
}
```

> `modelConfig` 可选，不传则使用环境变量默认值。配置会持久化，服务重启后自动恢复。

**响应**：
```json
{ "kbId": "kb_a1b2c3d4", "tenantId": "your_tenant", "name": "知识库名称" }
```

---

### `GET /api/kb/list`

分页列出某租户下所有知识库（仅含概要信息，不含完整文档列表）。

**Query 参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `tenantId` | 必填 | 租户 ID |
| `page` | `1` | 页码（从 1 开始） |
| `pageSize` | `20` | 每页数量（1–100） |

**响应**：
```json
{
  "total": 2,
  "page": 1,
  "pageSize": 20,
  "items": [
    {
      "kbId": "kb_a1b2c3d4",
      "name": "香港劳动法",
      "description": "雇佣条例等法律文件",
      "createdAt": "2026-04-16T10:00:00Z",
      "docCount": 3
    }
  ]
}
```

---

### `GET /api/kb/{kbId}`

获取单个知识库详情，包含完整文档列表。

**Query 参数**：`tenantId`

**响应**：
```json
{
  "kbId": "kb_a1b2c3d4",
  "name": "香港劳动法",
  "description": "雇佣条例等法律文件",
  "createdAt": "2026-04-16T10:00:00Z",
  "docs": [
    {
      "docId": "doc_xxx",
      "fileName": "雇佣条例.pdf",
      "chunkCount": 320,
      "uploadedAt": "2026-04-16T10:05:00Z",
      "status": "indexed"
    }
  ]
}
```

---

### `PATCH /api/kb/{kbId}`

更新知识库名称或描述。

**请求体**：
```json
{
  "tenantId": "your_tenant",
  "name": "新名称",
  "description": "新描述"
}
```

> `name` 和 `description` 至少提供一个，只传其中一个时只更新对应字段。

**响应**：同 `POST /api/kb/create`。

---

### `DELETE /api/kb/{kbId}`

删除知识库及其全部文档和向量数据。

**Query 参数**：`tenantId`

**响应**：`{ "ok": true }`

---

### `GET /api/kb/{kbId}/docs`

分页列出某知识库下所有文档。

**Query 参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `tenantId` | 必填 | 租户 ID |
| `page` | `1` | 页码（从 1 开始） |
| `pageSize` | `20` | 每页数量（1–100） |

**响应**：
```json
{
  "total": 5,
  "page": 1,
  "pageSize": 20,
  "items": [
    {
      "docId": "doc_xxx",
      "fileName": "雇佣条例.pdf",
      "chunkCount": 320,
      "uploadedAt": "2026-04-16T10:05:00Z",
      "status": "indexed"
    }
  ]
}
```

---

### `POST /api/kb/{kbId}/upload`

上传并异步索引文档（支持 PDF / TXT / Markdown，最大 50MB，支持批量）。

**请求**：`multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `files` | File[] | 要上传的文档（支持多个） |
| `tenantId` | string | 租户 ID |
| `modelConfig` | JSON string | 可选，覆盖本次上传的模型配置 |

**响应**（立即返回，无需等待建图完成）：
```json
[
  {
    "docId": "doc_e5f6g7h8",
    "fileName": "report.pdf",
    "chunkCount": 42,
    "status": "indexing"
  }
]
```

> 上传相同内容的文件会返回 `409 Conflict`，并告知已存在的 `docId`。

---

### `GET /api/kb/{kbId}/docs/{docId}/status`

查询文档索引状态，用于轮询上传进度。

**Query 参数**：`tenantId`

**响应**：
```json
{
  "docId": "doc_e5f6g7h8",
  "fileName": "report.pdf",
  "chunkCount": 42,
  "uploadedAt": "2026-04-16T10:05:00Z",
  "status": "indexed"
}
```

| `status` 值 | 含义 |
|-------------|------|
| `indexing` | 后台建图中 |
| `indexed` | 索引完成，可以查询 |
| `error` | 索引失败，`error` 字段包含原因 |

---

### `DELETE /api/kb/{kbId}/docs/{docId}`

删除单篇文档及其在知识图谱中的所有数据。

**Query 参数**：`tenantId`

> 文档处于 `indexing` 状态时返回 `409`，请等待索引完成后再删除。

**响应**：`{ "ok": true }`

---

### `POST /api/query`

向知识库提问，返回 LLM 生成的答案。超过 `QUERY_TIMEOUT` 秒未响应时返回 504。

**请求体**：
```json
{
  "traceId": "optional-trace-id",
  "tenantId": "your_tenant",
  "kbId": "kb_a1b2c3d4",
  "question": "公司年假政策是什么？",
  "mode": "hybrid",
  "topK": 5,
  "queryModel": {
    "baseUrl": "...",
    "apiKey": "...",
    "model": "..."
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tenantId` | string | 必填 | 租户 ID |
| `kbId` | string | 必填 | 知识库 ID |
| `question` | string | 必填 | 问题（1–2000 字符） |
| `mode` | string | `hybrid` | 检索模式：`low` / `high` / `hybrid` |
| `topK` | int | `5` | 召回片段数（1–20） |
| `traceId` | string | 自动生成 | 链路追踪 ID，原样返回 |
| `queryModel` | object | KB 配置 → 环境变量 | 仅覆盖本次请求的问答模型 |

**响应**：
```json
{
  "traceId": "optional-trace-id",
  "answer": "根据公司规定，员工每年享有 10 天带薪年假……",
  "sources": [],
  "entities": [],
  "latencyMs": 1240
}
```

---

## 查询模式说明

| 模式 | 原理 | 适用场景 |
|------|------|----------|
| `low` | 实体提取 + 知识图谱精确匹配 | 实体/概念明确的问题 |
| `high` | 向量语义相似度检索 | 模糊/概念性问题 |
| `hybrid` | 两种方式结合 | **通用推荐，效果最好** |

---

## 模型配置

服务支持任意 **OpenAI 兼容** 的 API，包括但不限于：

- **OpenRouter**（默认，聚合多家模型）
- **OpenAI**（GPT-4o / GPT-4o-mini）
- **DeepSeek**（deepseek-chat / deepseek-reasoner）
- **Ollama**（本地模型，`baseUrl` 设为 `http://localhost:11434/v1`）

**模型优先级**（以 query 模型为例）：
1. 请求级别 `queryModel` 参数
2. 创建 KB 时的 `modelConfig.query`
3. 环境变量 `DEFAULT_QUERY_*`

Embedding 维度自动推断规则：

| 模型名包含 | 推断维度 |
|-----------|----------|
| `text-embedding-3-small` / `ada-002` | 1536 |
| `text-embedding-3-large` | 3072 |
| `jina` | 1024 |
| `nomic` | 768 |

---

## Docker 部署

### 使用 docker-compose（推荐）

```bash
# 确保 .env 文件中已填写 API Key
docker compose up -d

# 查看日志
docker compose logs -f
```

### 手动 docker run

```bash
docker build -t rag-service .

docker run -d \
  -p 8000:8000 \
  -e DEFAULT_INDEX_API_KEY="sk-..." \
  -e DEFAULT_EMBEDDING_API_KEY="sk-..." \
  -e INTERNAL_SECRET="your-strong-secret" \
  -v /host/data:/data/lightrag \
  --name rag-service \
  rag-service
```

> 数据持久化建议挂载 `/data/lightrag` 到宿主机目录，否则容器重启后知识库数据会丢失。

---

## 项目结构

```
python_rag_service/
├── main.py                  # FastAPI 入口，路由注册，启动检查
├── requirements.txt
├── requirements-dev.txt     # 测试依赖
├── Dockerfile
├── docker-compose.yml
│
├── api/
│   ├── deps.py              # Bearer Token 鉴权
│   ├── health.py            # GET  /api/health
│   ├── kb.py                # 知识库 & 文档 CRUD
│   └── query.py             # POST /api/query
│
├── core/
│   └── config.py            # Pydantic Settings，读取环境变量
│
├── services/
│   ├── rag_manager.py       # LightRAG 实例生命周期管理
│   ├── meta_store.py        # KB / 文档元数据持久化（JSON）
│   ├── model_factory.py     # LLM & Embedding 函数工厂
│   ├── parser.py            # PDF / TXT / MD 解析
│   └── chunker.py           # 语义分块（512 token / 50 overlap）
│
├── models/
│   └── schemas.py           # Pydantic 请求/响应 Schema
│
├── test/                    # 自动化测试（49 个用例）
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_kb.py
│   ├── test_docs.py
│   └── test_query.py
│
└── data/                    # 运行时生成，知识库存储根目录
    └── {tenantId}/
        ├── meta.json        # 该租户所有 KB 的元数据
        └── {kbId}/          # LightRAG 向量库 & 知识图谱文件
```

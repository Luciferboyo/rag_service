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
- **文档解析**：支持 PDF、TXT、Markdown，自动语义分块
- **灵活模型**：索引模型、查询模型、嵌入模型均可独立配置，支持任意 OpenAI 兼容 API
- **多种检索模式**：实体检索（low）、语义检索（high）、混合检索（hybrid）
- **知识图谱 + 向量双引擎**：由 LightRAG 提供，检索质量优于纯向量方案

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
DEFAULT_QUERY_API_KEY=sk-...
DEFAULT_EMBEDDING_API_KEY=sk-...
```

### 3. 启动服务

```bash
python main.py
# 默认监听 http://0.0.0.0:8000
```

### 4. 快速验证

```bash
# 健康检查
curl http://localhost:8000/api/health

# 创建知识库
curl -X POST http://localhost:8000/api/kb/create \
  -H "Content-Type: application/json" \
  -d '{"tenantId": "demo", "name": "测试知识库"}'

# 上传文档（返回 kbId 用于后续操作）
curl -X POST http://localhost:8000/api/kb/{kbId}/upload \
  -F "tenantId=demo" \
  -F "file=@your_document.pdf"

# 提问
curl -X POST http://localhost:8000/api/query \
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
| `DEFAULT_INDEX_MODEL` | `openai/gpt-4o-mini` | 索引模型名称 |
| `DEFAULT_QUERY_BASE_URL` | `https://openrouter.ai/api/v1` | 问答 LLM 的 API 地址 |
| `DEFAULT_QUERY_API_KEY` | — | 问答 LLM 的鉴权 Key |
| `DEFAULT_QUERY_MODEL` | `openai/gpt-4o-mini` | 问答模型名称 |
| `DEFAULT_EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | 嵌入模型 API 地址 |
| `DEFAULT_EMBEDDING_API_KEY` | — | 嵌入模型鉴权 Key |
| `DEFAULT_EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型名称 |
| `DEFAULT_EMBEDDING_DIM` | `1536` | 嵌入向量维度 |
| `COSINE_THRESHOLD` | `0.5` | 向量检索最低相似度阈值（0.0–1.0） |
| `STORAGE_DIR` | `./data` | 知识库数据存储根目录 |
| `INTERNAL_SECRET` | — | 内部服务鉴权 Token |

---

## API 文档

### `GET /api/health`

健康检查。

**响应示例**：
```json
{ "status": "ok" }
```

---

### `POST /api/kb/create`

创建知识库。

**请求体**：
```json
{
  "tenantId": "your_tenant",
  "name": "知识库名称",
  "description": "可选描述",
  "modelConfig": {           // 可选，不传则使用环境变量默认值
    "index": { "baseUrl": "...", "apiKey": "...", "model": "..." },
    "query": { "baseUrl": "...", "apiKey": "...", "model": "..." },
    "embedding": { "baseUrl": "...", "apiKey": "...", "model": "..." }
  }
}
```

**响应示例**：
```json
{
  "kbId": "kb_a1b2c3d4",
  "tenantId": "your_tenant",
  "name": "知识库名称"
}
```

---

### `POST /api/kb/{kbId}/upload`

上传并索引文档（支持 PDF / TXT / Markdown，最大 50MB）。

**请求**：`multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | File | 要上传的文档 |
| `tenantId` | string | 租户 ID |
| `modelConfig` | JSON string | 可选，覆盖模型配置 |

**响应示例**：
```json
{
  "docId": "doc_e5f6g7h8",
  "fileName": "report.pdf",
  "chunkCount": 42,
  "status": "indexed"
}
```

> 文档在服务端被分割为约 512 token 的语义块，再写入知识图谱与向量库，**首次上传较慢**（约数秒至数分钟，取决于文档大小和 LLM 速度）。

---

### `DELETE /api/kb/{kbId}`

删除知识库及其全部数据。

**请求参数**：`tenantId`（query string）

**响应示例**：
```json
{ "status": "deleted" }
```

---

### `POST /api/query`

向知识库提问，返回 LLM 生成的答案。

**请求体**：
```json
{
  "traceId": "optional-trace-id",
  "tenantId": "your_tenant",
  "kbId": "kb_a1b2c3d4",
  "question": "公司年假政策是什么？",
  "mode": "hybrid",
  "topK": 5,
  "queryModel": {             // 可选，仅覆盖本次请求的问答模型
    "baseUrl": "...",
    "apiKey": "...",
    "model": "..."
  }
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `mode` | `hybrid` | 检索模式：`low` / `high` / `hybrid` |
| `topK` | `5` | 召回片段数（1–20） |
| `queryModel` | 环境变量 | 仅覆盖本次问答 LLM |

**响应示例**：
```json
{
  "traceId": "optional-trace-id",
  "answer": "根据公司规定，员工每年享有 10 天带薪年假……",
  "sources": [
    { "content": "第三章 假期制度……", "score": 0.87 }
  ],
  "entities": ["年假", "带薪假期"],
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

模型维度自动推断规则（当 `DEFAULT_EMBEDDING_DIM` 未设置时）：

| 模型名包含 | 推断维度 |
|-----------|----------|
| `text-embedding-3-small` / `ada-002` | 1536 |
| `text-embedding-3-large` | 3072 |
| `jina` | 1024 |
| `nomic` | 768 |

---

## Docker 部署

```bash
docker build -t rag-service .

docker run -d \
  -p 8000:8000 \
  -e DEFAULT_INDEX_API_KEY="sk-..." \
  -e DEFAULT_QUERY_API_KEY="sk-..." \
  -e DEFAULT_EMBEDDING_API_KEY="sk-..." \
  -v /host/data:/data/lightrag \
  --name rag-service \
  rag-service
```

> 数据持久化建议挂载 `/data/lightrag` 到宿主机目录，否则容器重启后知识库数据会丢失。

---

## 项目结构

```
python_rag_service/
├── main.py                  # FastAPI 入口，注册路由
├── requirements.txt
├── Dockerfile
│
├── api/
│   ├── health.py            # GET  /api/health
│   ├── kb.py                # POST /api/kb/create  POST /api/kb/{id}/upload  DELETE /api/kb/{id}
│   └── query.py             # POST /api/query
│
├── core/
│   └── config.py            # Pydantic Settings，读取环境变量
│
├── services/
│   ├── rag_manager.py       # LightRAG 实例生命周期管理
│   ├── model_factory.py     # LLM & 嵌入函数工厂
│   ├── parser.py            # PDF / TXT / MD 解析
│   └── chunker.py           # 语义分块（512 token / 50 overlap）
│
├── models/
│   └── schemas.py           # Pydantic 请求/响应 Schema
│
└── data/                    # 运行时生成，知识库存储根目录
    └── {tenantId}/{kbId}/
```

import re
import tiktoken

# GPT tokenizer，用于精确计数 token
_enc = tiktoken.get_encoding("cl100k_base")

CHUNK_SIZE = 512      # 每块最大 token 数
CHUNK_OVERLAP = 50    # 相邻块重叠 token 数（保留上下文）


def _token_len(text: str) -> int:
    return len(_enc.encode(text))


def _split_by_tokens(text: str, chunk_size: int, overlap: int) -> list[str]:
    """固定 token 窗口切割（处理超长段落）"""
    tokens = _enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_text = _enc.decode(tokens[start:end])
        chunks.append(chunk_text.strip())
        start += chunk_size - overlap
    return [c for c in chunks if c]


def chunk_markdown(text: str) -> list[str]:
    """
    MD 文档：按标题（#/##/###）切割，保留标题到下一个同级标题的内容作为一个 chunk。
    超过 CHUNK_SIZE 的节再按 token 二次切割。
    """
    # 按 # 开头的行分割
    sections = re.split(r'(?=^#{1,3} )', text, flags=re.MULTILINE)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if _token_len(section) <= CHUNK_SIZE:
            chunks.append(section)
        else:
            # 节太长，再按段落切
            chunks.extend(chunk_plain(section))
    return chunks


def chunk_plain(text: str) -> list[str]:
    """
    纯文本/PDF：按段落（空行）切割，小段合并，大段拆分。
    """
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if _token_len(candidate) <= CHUNK_SIZE:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # 段落本身超长 → token 窗口切
            if _token_len(para) > CHUNK_SIZE:
                chunks.extend(_split_by_tokens(para, CHUNK_SIZE, CHUNK_OVERLAP))
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def chunk_document(filename: str, text: str) -> list[str]:
    """
    根据文件类型选择分块策略：
    - .md        → 按标题语义切割
    - .pdf/.txt  → 按段落语义切割
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "md":
        chunks = chunk_markdown(text)
    else:
        chunks = chunk_plain(text)

    # 过滤过短的 chunk（少于 20 token 没有检索价值）
    return [c for c in chunks if _token_len(c) >= 20]
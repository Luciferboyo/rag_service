from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 服务配置
    storage_dir: str = "./data"
    
    # 默认 LLM（用户未配置时的 fallback）
    default_index_base_url: str = "https://openrouter.ai/api/v1"
    default_index_api_key: str = ""
    default_index_model: str = "deepseek/deepseek-chat"

    default_query_base_url: str = "https://openrouter.ai/api/v1"
    default_query_api_key: str = ""
    default_query_model: str = "openai/gpt-4o-mini"

    default_embedding_base_url: str = "https://api.openai.com/v1"
    default_embedding_api_key: str = ""
    default_embedding_model: str = "text-embedding-3-small"
    default_embedding_dim: int = 1536

    # 向量检索相似度阈值
    cosine_threshold: float = 0.5

    # 内部鉴权（Node.js Bot 调用时传 header）
    internal_secret: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

"""
RAG 系统配置管理。

使用 pydantic-settings 统一管理环境变量和默认配置。
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """系统配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    # API 配置
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    glm_api_key: Optional[str] = None
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # Ollama 本地模型
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "qwen3-embedding"

    # 默认提供商
    default_embedding_provider: str = "ollama"
    default_llm_provider: str = "openai"

    # RAG 参数
    chunk_size: int = Field(default=500, gt=0)
    chunk_overlap: int = Field(default=100, ge=0)
    retrieval_top_k: int = Field(default=3, gt=0)
    retrieval_score_threshold: Optional[float] = Field(default=None, ge=0)
    llm_temperature: float = Field(default=0.7, ge=0, le=2)
    llm_max_tokens: int = Field(default=1000, gt=0)

    # 向量数据库配置
    chroma_persist_dir: str = "./data/chroma_db"
    collection_name: str = "rag_documents"

    # Web 服务配置。无认证时默认仅监听本机。
    server_host: str = "127.0.0.1"
    server_port: int = Field(default=7860, ge=1, le=65535)
    share_gradio: bool = False

    # 应用与日志配置
    service_name: str = "rag-web"
    app_env: str = "development"
    log_level: str = "INFO"
    log_file_path: str = "./logs/rag_{time:YYYY-MM-DD}.jsonl"
    log_rotation: str = "500 MB"
    log_retention: str = "10 days"
    log_console_format: str = "text"
    log_file_format: str = "json"

    # Metrics 配置。仅由应用主入口显式启动 HTTP 服务。
    metrics_enabled: bool = True
    metrics_host: str = "127.0.0.1"
    metrics_port: int = Field(default=8000, ge=1, le=65535)

    # Tracing 配置。默认关闭；endpoint 为空时不会创建网络导出器。
    tracing_enabled: bool = False
    otel_exporter_otlp_endpoint: Optional[str] = None

    # 文件上传配置
    upload_dir: str = "./data/uploads"
    max_upload_size_mb: int = Field(default=50, gt=0)
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".docx", ".txt"]
    )

    @field_validator("default_embedding_provider", "default_llm_provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        """提供商名称统一为小写，避免环境变量大小写导致匹配失败。"""
        return value.strip().lower()

    @field_validator("log_console_format", "log_file_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        """日志格式只允许开发友好的 text 或机器可读的 json。"""
        normalized = value.strip().lower()
        if normalized not in {"text", "json"}:
            raise ValueError("日志格式必须是 text 或 json")
        return normalized

    @field_validator("otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def normalize_optional_endpoint(cls, value):
        """空白 OTLP 地址按未配置处理，避免意外创建导出器。"""
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_extensions(cls, values: list[str]) -> list[str]:
        """扩展名统一为带点的小写格式并去重。"""
        normalized: list[str] = []
        for value in values:
            extension = value.strip().lower()
            if not extension.startswith("."):
                extension = f".{extension}"
            if extension and extension not in normalized:
                normalized.append(extension)
        if not normalized:
            raise ValueError("allowed_extensions 不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        """重叠长度必须小于分块长度。"""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取缓存后的全局配置实例。"""
    return Settings()


settings = get_settings()


if __name__ == "__main__":
    print("=" * 60)
    print("RAG 系统配置")
    print("=" * 60)
    print(f"Embedding Provider: {settings.default_embedding_provider}")
    print(f"LLM Provider: {settings.default_llm_provider}")
    print(f"Chunk: {settings.chunk_size} / overlap {settings.chunk_overlap}")
    print(f"Retrieval: top_k={settings.retrieval_top_k}, threshold={settings.retrieval_score_threshold}")
    print(f"Server: {settings.server_host}:{settings.server_port}")
    print(f"Log Level: {settings.log_level}")

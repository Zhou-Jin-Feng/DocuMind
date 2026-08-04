"""
RAG 系统配置管理
使用 pydantic-settings 统一管理所有配置项
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """系统配置"""
    
    # ============================================
    # API 配置
    # ============================================
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
    
    # ============================================
    # 默认提供商
    # ============================================
    default_embedding_provider: str = "ollama"
    default_llm_provider: str = "openai"
    
    # ============================================
    # RAG 参数
    # ============================================
    # 文档分块
    chunk_size: int = 500
    chunk_overlap: int = 100
    
    # 检索
    retrieval_top_k: int = 3
    retrieval_score_threshold: Optional[float] = None
    
    # 生成
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1000
    
    # ============================================
    # 向量数据库配置
    # ============================================
    chroma_persist_dir: str = "./data/chroma_db"
    collection_name: str = "rag_documents"
    
    # ============================================
    # Web 服务配置
    # ============================================
    server_host: str = "0.0.0.0"
    server_port: int = 7860
    share_gradio: bool = False
    
    # ============================================
    # 日志配置
    # ============================================
    log_level: str = "INFO"
    log_file_path: str = "./logs/rag_{time:YYYY-MM-DD}.log"
    log_rotation: str = "500 MB"
    log_retention: str = "10 days"
    
    # ============================================
    # 文件上传配置
    # ============================================
    upload_dir: str = "./data/uploads"
    max_upload_size_mb: int = 50
    allowed_extensions: list = [".pdf", ".docx", ".txt"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略.env中的额外字段


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例（用于依赖注入）"""
    return settings


if __name__ == "__main__":
    """测试配置加载"""
    print("=" * 60)
    print("RAG 系统配置")
    print("=" * 60)
    
    print(f"\n[API 配置]")
    print(f"  OpenAI API Key: {'已配置' if settings.openai_api_key else '未配置'}")
    print(f"  OpenAI Base URL: {settings.openai_base_url}")
    print(f"  Anthropic API Key: {'已配置' if settings.anthropic_api_key else '未配置'}")
    
    print(f"\n[默认提供商]")
    print(f"  Embedding: {settings.default_embedding_provider}")
    print(f"  LLM: {settings.default_llm_provider}")
    
    print(f"\n[RAG 参数]")
    print(f"  分块大小: {settings.chunk_size}")
    print(f"  分块重叠: {settings.chunk_overlap}")
    print(f"  检索数量: {settings.retrieval_top_k}")
    print(f"  LLM 温度: {settings.llm_temperature}")
    
    print(f"\n[数据库配置]")
    print(f"  存储路径: {settings.chroma_persist_dir}")
    print(f"  集合名称: {settings.collection_name}")
    
    print(f"\n[服务配置]")
    print(f"  服务地址: {settings.server_host}:{settings.server_port}")
    print(f"  日志级别: {settings.log_level}")
    
    print("\n" + "=" * 60)

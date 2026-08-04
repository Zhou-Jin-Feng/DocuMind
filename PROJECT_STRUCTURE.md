# DocuMind - v1.2 完整结构说明

## 📁 项目目录树

```
DocuMind/                          # 项目根目录
│
├─── 📦 核心应用代码 ───────────────────
│   app/                               # 应用核心包
│   ├── __init__.py                    # 包初始化，导出 settings
│   ├── config.py                      # ⭐ 统一配置管理（新增）
│   │
│   ├── core/                          # 核心业务模块
│   │   ├── __init__.py
│   │   ├── document_loader.py         # 文档加载器（PDF/Word/TXT）
│   │   ├── document_chunker.py        # 文档分块器
│   │   ├── embedding_client.py        # 向量嵌入客户端（OpenAI/Ollama等）
│   │   ├── vector_store.py            # 向量数据库（ChromaDB）
│   │   ├── retriever.py               # 检索器（语义搜索）
│   │   └── generator.py               # 生成器（LLM 回答生成）
│   │
│   └── utils/                         # 工具模块
│       ├── __init__.py
│       ├── logger.py                  # ⭐ 统一日志系统（新增）
│       └── monitoring.py              # ⭐ 性能监控工具（新增）
│
├─── 📂 数据和日志 ─────────────────────
│   data/                              # 统一数据目录（新增）
│   ├── chroma_db/                     # 向量数据库存储
│   └── uploads/                       # 用户上传的文件
│
│   logs/                              # 日志输出目录（新增）
│   └── rag_YYYY-MM-DD.log             # 按日期轮转的日志文件
│
├─── 🧪 测试和备份 ─────────────────────
│   tests/                             # 单元测试目录（新增）
│   └── __init__.py
│
│   backup/                            # 旧文件备份（迁移后自动生成）
│   ├── document_loader.py
│   ├── document_chunker.py
│   ├── embedding_client.py
│   ├── vector_store.py
│   ├── retriever.py
│   └── generator.py
│
├─── 🌐 Web 应用 ────────────────────────
│   web_app.py                         # ⭐ Gradio Web 界面入口（已更新）
│
├─── 📝 依赖和配置 ──────────────────────
│   requirements.txt                   # ⭐ 精简版依赖（25个包）
│   requirements-dev.txt               # ⭐ 开发环境依赖（新增）
│   .env                               # 环境变量配置（API Keys）
│   .gitignore                         # Git 忽略规则（已更新）
│
├─── 📚 文档 ────────────────────────────
│   README.md                          # 项目说明（原有）
│   MIGRATION_GUIDE.md                 # ⭐ 迁移指南（新增）
│   DEPENDENCIES.md                    # ⭐ 依赖说明（新增）
│
├─── 🔧 工具脚本 ─────────────────────────
│   migrate_modules.py                 # ⭐ 自动迁移脚本（新增）
│   verify_refactor.py                 # ⭐ 重构验证脚本（新增）
│   test_dependencies.py               # ⭐ 依赖测试脚本（新增）
│
├─── 📄 测试数据 ─────────────────────────
│   knowledge_base.txt                 # 示例知识库文档
│   test_document.txt                  # 测试文档1
│   test_chunking_document.txt         # 测试文档2
│   test_vector_store.txt              # 测试文档3
│
└─── 🗑️ 旧版本（待清理）──────────────────
    demo_chroma_db/                    # 旧向量库1（可删除）
    rag_web_chroma_db/                 # 旧向量库2（可删除）
    retrieval_chroma_db/               # 旧向量库3（可删除）
    integrated_chroma_db/              # 旧向量库4（可删除）
```

---

## 📖 核心文件详解

### 🔹 **app/config.py** (NEW - 统一配置管理)
```python
# 使用 pydantic-settings 管理所有配置
class Settings(BaseSettings):
    # API 配置
    openai_api_key: Optional[str] = None
    default_embedding_provider: str = "ollama"
    
    # RAG 参数
    chunk_size: int = 500
    chunk_overlap: int = 100
    
    # 数据库配置
    chroma_persist_dir: str = "./data/chroma_db"
    
    # Web 服务配置
    server_host: str = "0.0.0.0"
    server_port: int = 7860
```

**作用**：
- 从 `.env` 自动加载配置
- 类型安全，自动验证
- 全局单例，统一访问

---

### 🔹 **app/core/document_loader.py** (文档加载器)
```python
class UniversalDocumentLoader:
    """通用文档加载器，支持 PDF、Word、TXT"""
    
    def load_document(self, file_path: str) -> List[Document]:
        # 自动识别文件类型
        # 返回 LangChain Document 对象列表
```

**支持格式**：
- PDF (`.pdf`)
- Word (`.docx`, `.doc`)
- 文本 (`.txt`)

---

### 🔹 **app/core/document_chunker.py** (文档分块器)
```python
class DocumentChunker:
    """文档分块器，将长文档切分为小片段"""
    
    def chunk_documents_recursive(self, documents: List[Document]):
        # 递归分块：段落 → 句子 → 字符
        # 保留重叠部分，避免上下文丢失
```

**分块策略**：
- 默认大小：500 字符
- 重叠：100 字符
- 智能分割：优先按段落和句子

---

### 🔹 **app/core/embedding_client.py** (向量嵌入客户端)
```python
class UniversalEmbeddingClient:
    """统一嵌入客户端，支持多个 API 提供商"""
    
    支持的提供商：
    - OpenAI (text-embedding-3-small)
    - Ollama (本地，qwen3-embedding)
    - DeepSeek (deepseek-embedding)
    - 智谱GLM (embedding-2)
```

**功能**：
- 单文本向量化
- 批量向量化（带进度条）
- 自动重试和错误处理

---

### 🔹 **app/core/vector_store.py** (向量数据库)
```python
class VectorStore:
    """向量存储管理器，基于 ChromaDB"""
    
    def add_documents(self, documents, embeddings):
        # 添加文档到向量库
    
    def search(self, query_embedding, n_results=5):
        # 相似度搜索
```

**特性**：
- 持久化存储
- 元数据过滤
- 相似度搜索

---

### 🔹 **app/core/retriever.py** (检索器)
```python
class Retriever:
    """检索器，封装多种检索策略"""
    
    def retrieve_semantic(self, query: str, top_k: int = 5):
        # 语义检索（向量相似度）
    
    def rerank_results(self, results, query):
        # 重排序（提升精度）
```

**检索策略**：
- 语义检索（向量相似度）
- 重排序（结合关键词匹配）
- 结果格式化（供 LLM 使用）

---

### 🔹 **app/core/generator.py** (生成器)
```python
class UniversalLLMClient:
    """统一 LLM 客户端"""
    支持：OpenAI、Claude、DeepSeek、GLM

class RAGGenerator:
    """RAG 生成器，结合检索结果和 LLM"""
    
    def generate_answer_stream(self, query, retrieval_results):
        # 流式生成答案
```

**功能**：
- 多 LLM 支持
- 流式输出
- 引用溯源

---

### 🔹 **app/utils/logger.py** (NEW - 统一日志)
```python
from loguru import logger

# 同时输出到控制台和文件
logger.info("操作成功", user_id=123, elapsed="0.5s")
```

**特性**：
- 彩色控制台输出
- 文件持久化
- 自动轮转（500MB）
- 结构化日志

---

### 🔹 **app/utils/monitoring.py** (NEW - 性能监控)
```python
@track_time
def slow_function():
    # 自动记录执行时间
    pass

with Timer("数据库查询"):
    # 手动计时
    pass
```

**功能**：
- 装饰器追踪函数耗时
- 上下文管理器手动计时
- 自动日志记录

---

### 🔹 **web_app.py** (Web 应用入口)
```python
class RAGWebApp:
    """RAG Web 应用，Gradio 界面"""
    
    功能：
    - 文档上传和索引
    - 对话式问答
    - 来源引用显示
```

**特性**：
- 使用新的模块路径（`app.core.*`）
- 从 `settings` 读取配置
- 使用 `logger` 记录日志
- 流式答案生成

---

## 📋 重要配置文件

### 🔹 **requirements.txt** (精简版依赖)
```
核心依赖（25个）：
- langchain + langchain-community
- chromadb
- openai + anthropic
- pypdf + python-docx
- gradio
- python-dotenv
- rich
- pydantic + pydantic-settings
```

### 🔹 **.env** (环境变量)
```bash
# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=...
GLM_API_KEY=...

# 默认提供商
DEFAULT_EMBEDDING_PROVIDER=ollama
DEFAULT_LLM_PROVIDER=openai

# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding
```

---

## 🎯 使用流程

### 1️⃣ **安装依赖**
```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2️⃣ **配置环境变量**
```bash
# 复制模板
# 创建本地 .env 并按本版本配置填写环境变量；不要提交真实凭据。

# 编辑 .env，填入 API Keys
```

### 3️⃣ **启动 Web 应用**
```bash
python web_app.py
```

### 4️⃣ **使用流程**
1. 访问 http://localhost:7860
2. 上传文档（PDF/Word/TXT）
3. 等待索引完成
4. 开始提问

---

## 🆚 新旧版本对比

| 特性 | 旧版本 | 新版本 v1.2 |
|------|--------|-------------|
| **文件组织** | 扁平，所有 .py 在根目录 | 分层，app/core/ 结构 |
| **配置管理** | 散落在各个文件 | 统一在 app/config.py |
| **日志系统** | rich.console 打印 | loguru 结构化日志 |
| **依赖包** | 115 个（~2GB） | 25 个（~500MB） |
| **ChromaDB 目录** | 4 个不同目录 | 1 个统一目录 |
| **可测试性** | 全局状态，难测试 | 依赖注入，易测试 |
| **性能监控** | 无 | 装饰器自动追踪 |

---

## 📚 学习路径

### 📖 **初学者**
1. 阅读 `README.md` - 了解项目背景
3. 运行 `python web_app.py` - 体验功能
4. 查看 `app/core/` 各模块 - 学习实现

### 🔧 **开发者**
2. 阅读 `app/config.py` - 学习配置管理
3. 阅读 `app/utils/logger.py` - 学习日志系统
4. 运行 `python verify_refactor.py` - 验证环境

### 🚀 **高级用户**
1. 阅读 `MIGRATION_GUIDE.md` - 学习迁移技术
2. 查看 `app/utils/monitoring.py` - 性能优化
3. 添加单元测试到 `tests/`
4. 实现容器化（Dockerfile）

---

## 🎊 总结

本版本采用模块化组织，主要结构特点如下：

✅ **清晰的分层架构** - 便于维护  
✅ **集中配置管理** - 可直接应用  
✅ **完善的日志系统** - 便于调试  
✅ **精简的依赖** - 快速部署  
✅ **详细的文档** - 5 个 Markdown 文档  

非常适合：
- 🎓 学习 RAG 系统实现
- 🔬 研究检索增强生成技术
- 🚀 作为生产项目的起点
- 📦 容器化和云部署的基础

---

**版本**: v1.2.0  
**最后更新**: 2026-08-04

# 项目结构（v1.2）

```text
DocuMind/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── document_loader.py
│   │   ├── document_chunker.py
│   │   ├── embedding_client.py
│   │   ├── vector_store.py
│   │   ├── retriever.py
│   │   └── generator.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── monitoring.py
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_document_pipeline.py
│   ├── test_embedding_client.py
│   ├── test_vector_store.py
│   ├── test_retriever.py
│   ├── test_generator.py
│   ├── test_web_app.py
│   └── *.txt
├── data/                  # 本地运行数据，Git 忽略
├── logs/                  # 日志，Git 忽略
├── .env                   # 本地密钥，Git 忽略
├── .env.example           # 无密钥模板
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── ARCHITECTURE.md
├── DEPENDENCIES.md
├── PROJECT_STRUCTURE.md
└── web_app.py
```

## 模块职责

| 文件 | 职责 |
|---|---|
| `app/config.py` | 环境变量加载、默认值和参数验证 |
| `document_loader.py` | PDF/DOCX/TXT 加载、稳定文档 ID、页码元数据 |
| `document_chunker.py` | 文档分块、稳定 Chunk ID、空块过滤 |
| `embedding_client.py` | Ollama 和 API Embedding 统一调用 |
| `vector_store.py` | Chroma 持久化、upsert、search、delete |
| `retriever.py` | Query Embedding、距离阈值、轻量重排 |
| `generator.py` | OpenAI 兼容/Anthropic 消息适配和流式生成 |
| `web_app.py` | 上传校验、同步索引、问答编排和 UI |
| `logger.py` | 当前基础日志配置；v1.3 将进一步结构化 |
| `monitoring.py` | 基础耗时工具，不等同于完整 Metrics/Tracing |

## 运行数据边界

以下目录不得提交到 Git：

- `data/chroma_db/`
- `data/uploads/`
- `logs/`
- `venv/`
- `__pycache__/`
- `.env`

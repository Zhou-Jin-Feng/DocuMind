# DocuMind - RAG 知识库问答系统（v1.2）

这是一个采用 Python Package 分层结构的本地单用户 RAG 本地单用户项目，支持文档加载、稳定分块、向量索引、语义检索、流式生成和来源展示。

> 当前版本：**v1.2 收尾版**。本版本暂不提供 Docker 启动方式。

## 当前能力

- 支持 PDF、DOCX、TXT 文档；不支持旧版 `.doc`。
- 文档和 Chunk 使用稳定 ID，相同文件重复上传通过 Chroma `upsert` 更新，不重复增加 Chunk。
- 检索结果明确使用 **distance（距离，越小越相关）**，并支持最大距离阈值。
- PDF 页面统一显示为从 1 开始的页码。
- OpenAI、Anthropic Claude、DeepSeek、GLM 生成接口，以及 Ollama/OpenAI 兼容 Embedding。
- 上传扩展名、上传大小、分块、检索和 LLM 参数统一从 `app/config.py` 与 `.env` 读取。
- 默认 Web 服务仅监听 `127.0.0.1`。

## 项目结构

```text
DocuMind/
├── app/
│   ├── config.py                 # Pydantic Settings 配置
│   ├── core/
│   │   ├── document_loader.py    # PDF/DOCX/TXT 加载与文档元数据
│   │   ├── document_chunker.py   # 分块与稳定 Chunk ID
│   │   ├── embedding_client.py   # 多 Provider Embedding
│   │   ├── vector_store.py       # Chroma upsert/search/delete
│   │   ├── retriever.py          # 距离阈值与轻量重排
│   │   └── generator.py          # 多 Provider 流式生成
│   └── utils/
│       ├── logger.py
│       └── monitoring.py
├── tests/                        # unittest 自动化测试和示例文本
├── data/                         # 运行数据（Git 忽略）
├── logs/                         # 日志（Git 忽略）
├── .env.example                 # 无密钥配置模板
├── requirements.txt
├── requirements-dev.txt
└── web_app.py                    # Gradio 入口
```

## 环境要求

- Windows PowerShell（以下命令以 Windows 为例）
- Python 3.11 或更高版本
- 至少配置一个 LLM Provider
- 默认 Embedding 使用本地 Ollama，需要 Ollama 服务和对应模型

## 快速开始

### 1. 创建并激活虚拟环境

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

若需要测试与代码质量工具：

```powershell
pip install -r requirements-dev.txt
```

### 3. 创建配置文件

```powershell
Copy-Item .env.example .env
```

不要把真实 API Key 写入 `.env.example`，也不要提交 `.env`。

### 4. 准备 Provider

默认 Embedding Provider 是 Ollama：

```powershell
ollama serve
ollama pull qwen3-embedding
```

然后在 `.env` 中为所选 LLM 填写 API Key。例如使用 OpenAI 时填写：

```dotenv
DEFAULT_LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
```

### 5. 启动 Web 应用

```powershell
python web_app.py
```

默认访问地址：`http://127.0.0.1:7860`。

## 关键配置

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `CHUNK_SIZE` | `500` | Chunk 字符长度 |
| `CHUNK_OVERLAP` | `100` | Chunk 重叠长度，必须小于 `CHUNK_SIZE` |
| `RETRIEVAL_TOP_K` | `3` | 返回候选数量 |
| `RETRIEVAL_SCORE_THRESHOLD` | 空 | Chroma 最大距离；越小越严格 |
| `LLM_TEMPERATURE` | `0.7` | 生成温度，范围 0–2 |
| `LLM_MAX_TOKENS` | `1000` | 最大生成 Token 数 |
| `MAX_UPLOAD_SIZE_MB` | `50` | 上传大小限制 |
| `SERVER_HOST` | `127.0.0.1` | 无认证时不要改为公网监听 |

`ALLOWED_EXTENSIONS` 是 JSON 数组，例如：

```dotenv
ALLOWED_EXTENSIONS=[".pdf", ".docx", ".txt"]
```

## 测试与检查

项目测试使用标准库 `unittest`，不依赖 pytest 也可运行：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q app web_app.py
python -m pip check
```

## 数据和索引

- Chroma 默认目录：`data/chroma_db/`
- 上传临时目录配置：`data/uploads/`
- 日志目录：`logs/`
- 上述运行数据均应保持在 Git 之外。

相同文件名且内容完全相同的文档会得到相同 `document_id` 和 `chunk_id`，重复上传不会增加 Chunk。

### 清空并重建本地索引

先停止 Web 服务，再执行：

```powershell
Remove-Item -Recurse -Force .\data\chroma_db
```

下次启动并重新上传文档时会创建新索引。该操作会删除本地全部向量数据，请先确认不需要保留。

## 已知限制

- 对话历史目前只用于 UI 展示，尚未参与 Query Rewrite 或历史感知检索。
- 当前只保证“完全相同文件”的重复上传幂等；同名文件内容更新后的旧版本清理属于 v1.5 文档生命周期能力。
- 尚未保存并校验索引的 Embedding 模型、维度和分块策略版本；更换 Embedding 模型前应重建索引。
- 目前是本地单用户应用，没有认证、租户隔离和生产级限流。
- v1.3 才会正式增加结构化日志、Metrics 和 Tracing；`monitoring.py` 目前只是基础计时工具。

## 常见问题

### 系统初始化失败

检查：

1. `.env` 中选定的 Provider 是否有 API Key；
2. Ollama 是否正在运行，Embedding 模型是否已下载；
3. `pip check` 是否通过；
4. `logs/` 中是否有完整异常。

### 上传后没有结果

- 确认文档有可提取文本；扫描版 PDF 暂不包含 OCR。
- 如果配置了 `RETRIEVAL_SCORE_THRESHOLD`，可适当调大或暂时留空。
- “系统错误”和“无检索结果”已分开处理，系统错误请查看日志。

### 更换 Embedding 模型后查询失败

不同模型的向量维度可能不同。停止服务、清空 `data/chroma_db/` 并重新上传文档，避免新旧向量混用。

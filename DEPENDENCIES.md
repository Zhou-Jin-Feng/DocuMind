# 依赖说明（v1.2）

## 核心直接依赖

| 分类 | 依赖 | 用途 |
|---|---|---|
| LangChain | `langchain-core` | `Document` 数据结构 |
| LangChain | `langchain-community` | PDF、DOCX、TXT Loader |
| LangChain | `langchain-text-splitters` | 字符和递归分块 |
| Embedding | `langchain-ollama` | 本地 Ollama Embedding |
| Vector DB | `chromadb` | 持久化向量索引 |
| LLM | `openai` | OpenAI、DeepSeek、GLM 兼容客户端 |
| LLM | `anthropic` | Claude 客户端 |
| Documents | `pypdf` | PDF 文本提取 |
| Documents | `docx2txt` | `Docx2txtLoader` 的直接运行依赖 |
| Web | `gradio` | Web UI |
| Config | `pydantic-settings` | `.env` 和配置验证 |
| Logging | `loguru` | 应用日志 |
| Utilities | `tiktoken`, `rich` | 分块分析和终端展示 |

`requirements.txt` 只声明直接依赖，不等同于完整锁文件。当前阶段不在同一次结构收尾中批量锁定或升级所有版本。

## 安装

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

开发依赖：

```powershell
pip install -r requirements-dev.txt
```

`requirements-dev.txt` 已通过 `-r requirements.txt` 包含核心依赖，无需重复执行两次安装命令。

## 验证

```powershell
python -m pip check
python -m unittest discover -s tests -p "test_*.py" -v
```

## 可复现性说明

当前仓库尚未引入锁文件。若后续需要严格可复现部署，建议在 Docker 阶段确定 Python 基础镜像后，再生成并验证锁文件，避免把本机完整 `pip freeze` 直接当作直接依赖清单。

# 依赖包精简说明

## 📊 精简结果对比

| 项目 | 原版本 | 新版本 | 减少 |
|------|--------|--------|------|
| 依赖包数量 | 115个 | **25个** | ⬇️ 78% |
| 预估安装大小 | ~2GB | **~500MB** | ⬇️ 75% |

## 🗑️ 删除的包及原因

### 1. **LangChain 冗余包**
删除：`langgraph`, `langgraph-checkpoint`, `langgraph-sdk`, `langchain-protocol`, `langsmith`
- **原因**：你只用了基础的文档加载、分块和OpenAI集成，不需要 LangGraph（工作流）和 LangSmith（追踪）

### 2. **未使用的大型依赖**
删除：`kubernetes`, `torch`, `transformers`, `datasets`, `evaluate`
- **原因**：你没有本地模型推理，完全依赖 API

### 3. **OpenTelemetry 监控包**
删除：`opentelemetry-*` 系列包（7个）
- **原因**：生产级监控，本地单用户项目不需要。后续用 `loguru` 就够了

### 4. **其他未使用的包**
删除：`orjson`, `ormsgpack`, `jsonpatch`, `jsonpointer` 等
- **原因**：代码里完全没用到

### 5. **间接依赖**
删除：很多如 `h11`, `httpcore`, `certifi` 等
- **原因**：会被主依赖自动安装，不需要显式列出

## ✅ 保留的核心包

### **LangChain 生态**
- `langchain-core`: 核心抽象（Document 类）
- `langchain-community`: 文档加载器（PDF、Word、TXT）
- `langchain-text-splitters`: 文本分块器
- `langchain-openai`: OpenAI 集成

### **向量数据库**
- `chromadb`: 轻量级向量存储

### **LLM API 客户端**
- `openai`: OpenAI/DeepSeek/GLM（兼容格式）
- `anthropic`: Claude

### **Web 框架**
- `gradio`: 快速搭建对话界面

### **工具库**
- `rich`: 终端美化输出
- `python-dotenv`: 环境变量管理
- `tiktoken`: Token 计数

## 🚀 安装指南

### 生产环境
```bash
pip install -r requirements.txt
```

### 开发环境（包含测试和代码质量工具）
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 推荐：使用虚拟环境
```bash
# 创建虚拟环境
python -m venv venv

# 激活（Windows）
venv\Scripts\activate

# 激活（Linux/Mac）
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 🔄 迁移步骤

如果你已经安装了旧版依赖，建议重新创建虚拟环境：

```bash
# 1. 停用当前环境
deactivate

# 2. 删除旧虚拟环境
Remove-Item -Recurse -Force venv

# 3. 创建新虚拟环境
python -m venv venv

# 4. 激活
venv\Scripts\activate

# 5. 安装新依赖
pip install -r requirements.txt
```

## 📝 版本说明

- 所有版本号都固定到具体版本（不使用 `>=`），确保环境一致性
- 选择的都是截至 2026 年 8 月的稳定版本
- 如果未来出现兼容性问题，可以逐个升级测试

## ⚙️ 可选增强（按需安装）

```bash
# 如果需要本地 Ollama 支持
pip install langchain-ollama

# 如果需要处理更多文档格式
pip install unstructured  # 支持更多文档类型
pip install pillow        # 图片处理

# 如果需要 FastAPI 替代 Gradio
pip install fastapi uvicorn

# 如果需要任务队列
pip install celery redis
```

## 🐛 常见问题

### Q1: 安装失败，提示缺少某个包
**A**: 可能是依赖版本冲突，尝试：
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

### Q2: 运行时报错 `ModuleNotFoundError`
**A**: 确认你激活了正确的虚拟环境：
```bash
which python  # Linux/Mac
where python  # Windows
```

### Q3: ChromaDB 初始化失败
**A**: 可能需要额外的系统依赖：
```bash
# Windows: 安装 Visual C++ Redistributable
# Linux: sudo apt-get install build-essential
```

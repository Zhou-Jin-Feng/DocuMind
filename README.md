# DocuMind - RAG知识库问答系统 - 本地单用户项目

## 项目简介
RAG（检索增强生成）知识库问答系统，提供文档处理、检索与回答生成能力。

## 快速开始

### 1. 配置API Key
创建本地 `.env`，按本版本配置填写所需环境变量；不要提交真实凭据。
```bash
# 创建本地 .env 并按本版本配置填写环境变量；不要提交真实凭据。
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 测试API连接
```bash
python test_api_connections.py
```

## 项目结构
```
DocuMind/
├── .env                          # API配置文件（不提交到Git）
# 创建本地 .env 并按本版本配置填写环境变量；不要提交真实凭据。
├── requirements.txt              # Python依赖
├── test_api_connections.py       # API连接测试脚本
└── README.md                     # 本文件
```

## 课程大纲
1. ✅ 环境准备
2. ⏳ 文档加载
3. ⏳ 文档分块
4. ⏳ 向量化与嵌入
5. ⏳ 向量数据库存储
6. ⏳ 检索
7. ⏳ 生成
8. ⏳ Web服务封装

## 注意事项
- 不要将 `.env` 文件提交到Git仓库
- 建议使用虚拟环境隔离依赖
- 至少需要一个LLM API和一个Embedding API才能运行完整系统

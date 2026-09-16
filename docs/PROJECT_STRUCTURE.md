# 项目结构与文件职责

本页描述当前源码组织；安装与使用见根目录 [README](../README.md)，设计约束见 [ARCHITECTURE](ARCHITECTURE.md)。运行生成物与私人材料不属于源码交付内容。

## 顶层布局

```text
DocuMind/
├── app/                   # Python 后端
├── frontend/              # React/Vite 工作台
├── tests/                 # 后端测试与安全合成样例
├── evaluation/            # 评测工具、固定输入和历史证据
├── docs/                  # 正式工程说明与契约
├── infra/milvus/          # 独立 Milvus 基础栈配置
├── data/.gitignore        # 运行数据目录入口
├── logs/.gitignore        # 日志目录入口
├── artifacts/.gitignore   # 新生成报告目录入口
├── .github/workflows/     # CI 定义
├── .env.example           # 无真实凭据的配置样例
├── Dockerfile
├── compose.yaml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

目录树列出职责边界，不逐行重复所有源码文件。未列出的模块以实际工作树为准。

## 后端分层

| 位置 | 责任 |
|---|---|
| `app/config.py` | 配置验证、项目根相对路径解析和显式目录准备 |
| `app/application.py` | 依赖生命周期、初始化失败清理和 readiness 聚合 |
| `app/api/` | FastAPI 路由、请求校验、公开错误与 SSE 协议；入口为 `python -m app.api` |
| `app/services/` | 文档管理、流式问答和单文档纯检索服务 |
| `app/lifecycle/` | Registry、内容版本/索引状态机、CLI 与持久化源文件 |
| `app/core/` | 加载、分块、Embedding、向量存储、检索、生成及离线增强组件 |
| `app/observability/` | 请求上下文、日志、指标和追踪 |
| `app/utils/` | 兼容工具和公共辅助函数 |

路由依赖服务层，服务层调用核心组件；React 只通过 HTTP/SSE 合约交互。新版不提供独立 Gradio 启动入口，旧架构只在对应历史快照中使用。

## 测试与评测

| 位置 | 责任 |
|---|---|
| `tests/test_api.py` | HTTP 契约、就绪状态、上传/检索及错误响应 |
| `tests/test_services.py`、`tests/test_service_regressions.py` | 服务事件、来源字段、失败语义和幂等指标 |
| `tests/test_runtime_paths.py` | cwd、配置覆盖、目录创建与报告输出位置 |
| `tests/test_observability_events.py`、`tests/test_tracing.py` | 日志链、Context 与 Span 层级和脱敏 |
| `frontend/src/` 中的测试 | 前端请求与状态逻辑 |
| `frontend/e2e/` | 基于 Mock API 的浏览器流程 |
| `evaluation/datasets/`、`evaluation/baselines/` | 固定语料、Gold、split、qrels 和回归参照 |
| `evaluation/reports/` | 已提交的历史评测证据；不是默认临时输出位置 |
| `docs/contracts/` | Provider/Consumer JSON Schema 与固定契约样例 |

## 运行文件边界

- `data/` 保存 Registry 和上传内容；默认上传目录为 `data/uploads/`。
- `logs/` 保存应用 JSONL 日志。
- `artifacts/` 保存新生成的验证/评测结果；普通离线 runner 在未指定输出时只打印。
- `_private/` 可用于个人资料，`agent/` 可用于本地工作记录；二者均被 Git 和 Docker 排除，不作为使用项目的前置条件。
- 目录骨架由 `.gitignore` 文件保留，真实内容默认忽略。测试使用临时目录，不共享正式数据。
- 默认应用路径以项目根解析，显式 CLI 路径仍尊重调用者选择；Docker 的持久化位置由 Compose 命名卷确定。

这些规则不自动迁移、删除或修复旧数据。备份、恢复和真实维护操作需要确认精确目标，不能用文件整理替代数据一致性检查。

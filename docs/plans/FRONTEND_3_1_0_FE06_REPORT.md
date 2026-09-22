# DocuMind 前端 3.1.0 FE-06 整体验证、版本收尾和交付

日期：2026-09-21

状态：FE-06 PASS WITH NOTES；形成待复审的 3.1.0 源码候选，未执行发布动作。

## 1. 范围与版本边界

FE-06 汇总 FE-01 至 FE-05 的实现、性能、视觉、键盘、依赖和契约证据，并把当前运行时与当前契约示例同步到 3.1.0。没有全仓替换 3.0.0；历史报告、3.0 迁移说明、旧发布记录、第三方依赖版本和会话 localStorage key 均保留。Schema 1.0 与 dense-v1 未改变。

当前代码是 3.1.0 源码候选，不代表 Git tag、GitHub Release、正式部署或真实服务验收。用户已授权连续完成 FE-05/FE-06；仍未授权 commit、push、tag、Release 或部署。

## 2. 版本同步清单

- app/__init__.py：应用版本 3.1.0。
- frontend/package.json 与 package-lock.json 根项目字段：3.1.0；依赖节点中的 3.0.0 版本保持原样。
- frontend/e2e/mock-api.mjs、frontend/benchmarks/fe01-mock-api.mjs：当前 health 示例 3.1.0。
- app/api/schemas.py、docs/contracts/retrieve-v1.schema.json、retrieve-v1.fixtures.json：当前 service_version 示例 3.1.0。
- tests/test_version_consistency.py、tests/test_config.py：当前期望版本 3.1.0。
- README.md、docs/RETRIEVE_API.md、docs/SCHOLARTRACE_INTEGRATION.md：当前源码候选说明更新；保留 3.0.0 迁移入口。
- docs/VERSION_HISTORY.md：新增 3.1.0 源码候选条目，明确未发布 Release。

## 3. 最终验证

| 检查 | 结果 |
|---|---|
| npm ci | 通过 |
| npm test | 38/38 |
| npm run typecheck | 通过 |
| npm run build | 通过；JS 650,266 B / gzip9 201,545 B；CSS 26,146 B / gzip9 5,744 B |
| FE-03 固定高频夹具 | 1/1；修补后性能证据单独写入 review-r3-r7 路径，历史 Markdown 0、无 Long Task |
| FE-04 + FE-05 定向 E2E | 22/22 |
| R3-R7 reviewer 边界 | 6/6；含窄屏引用焦点 |
| 全量 Playwright | 52/52（包含正式新增矩阵 11/11） |
| Python 版本/检索契约专项 | 9 passed，13 subtests |
| Python 全量 | 334 passed，1 skipped，186 subtests |
| Black | 117 files unchanged |
| compileall | 通过 |
| Compose 两份配置 | 通过 |
| 确定性评测 | 8 cases，regression gate PASS |
| npm ls --all | 退出码 0 |
| npm audit --omit=dev | 0 vulnerabilities |
| npm audit | 既有 Vitest/@vitest-mocker 2 moderate；修复会强制升级 Vitest 5，未在本阶段扩大范围 |
| git diff --check | 通过，仅 Windows 换行提示 |

Python 全量测试有 4 个环境/依赖警告：Starlette/httpx 弃用、langchain-community sunset、子进程编码警告以及 pytest cache 目录已存在提示；没有失败。

## 4. 构建与性能影响

FE-03 normal 构建基线为 JS 426,039 B / gzip9 131,805 B、CSS 24,143 B / gzip9 5,278 B。FE-04 normal 为 JS 468,028 B / gzip9 146,012 B、CSS 24,896 B / gzip9 5,496 B。FE-06 修补后包含 FE-05/R3-R7 的 normal 构建为 JS 650,266 B / gzip9 201,545 B、CSS 26,146 B / gzip9 5,744 B。相对 FE-03 合计增加 224,227 B raw / 69,740 B gzip9；该增量是 Radix、rehype-highlight、FE-04/FE-05 实现和本轮边界修补共同组成，不能归因于单个依赖。

修补后最终普通产物 SHA-256：JS a1c69e1afa80da48915b10ca8f8172233ede03ae957a648a767fb8d2e4a836d3；CSS 376a5c19f50c7ba6f11ab03ab0d225ffadd9d689d7ff79bd287ade640b7d83ab。

修补后性能证据：artifacts/frontend-3.1.0/fe03/streaming-review-r3-r7.json。另保留 R2 输出证据 streaming-after-r2.json。夹具为 50 条历史消息、10,000 字正文、200 token、10ms 目标分块；最终正文 SHA 与历史 Markdown 隔离保持正确。合成 Mock 不能外推真实 Provider、后台标签页或所有设备。

## 5. 交付与兼容

- FE-01～FE-05 报告、过程记录、项目记忆和 FE-06 交付入口已保留在仓库/本地忽略证据目录。
- 3.0.0 rag-workbench-conversations-v1 数据结构、12 会话/60 消息上限和 generating/retrieving 兼容行为未清空或迁移；FE-06 没有以清空 localStorage 作为升级步骤。
- 当前服务协议、SSE 事件、纯检索 Schema 1.0、dense-v1、来源 rank 约定未改变。
- 真实模型、真实 Milvus、真实屏幕阅读器、CI Node 22/Python 3.11 环境尚未在本机复刻；本机为 Node 24.18.0、Python 3.14.6/venv，报告按边界陈述。

## 6. 未关闭但不阻断的事项

- 完整 npm audit 的 2 个 moderate 属开发依赖 Vitest 链路；升级 Vitest 5 是潜在主版本变更，未擅自处理。
- FE-04 阶段 SMTP 完成通知因 DNS 解析失败未送达；未无限重试。
- FE-04 实验浏览器 profile 位于 agent/fe04-browser-*，Windows 终端策略拒绝递归删除；不影响源码、服务和证据。
- 860→861 反向动态断点已纳入正式 fe05-focus-boundaries.spec.ts 并通过；历史 FE-04 报告中的“未单列”只描述当时阶段状态，不代表当前缺口。

## 7. 最终结论

FE-06 结论：PASS WITH NOTES。当前工作树具备可复审的 3.1.0 源码候选和完整本机证据；没有未关闭的功能必验项。候选尚未提交、推送、打 tag、发布或部署；下一步必须由人工复审决定是否允许这些外部动作。

## FE-04～FE-06 独立复审补充

本轮新增 FE-05 边界复审发现 R3～R7 并已修复：规范编号校验、reference-style link 边界、普通锚点冒充防护、重复点击重新定位和跨会话高亮清理。新增边界与窄屏焦点矩阵通过，FE-05 公开报告已同步。修补后 npm test 38/38、typecheck/build、reviewer 边界 6/6、FE-05 合计 9/9、正式新增矩阵 11/11、全量 Playwright 52/52、最终高亮性能夹具 1/1 均通过；FE-06 结论维持 PASS WITH NOTES。

## 最终 notes 收尾

- N01：已关闭；可信 HEAD 配对 baseline/after、源码/依赖/夹具指纹、create-only archive 与哈希保护已形成。
- N02：已关闭；复审矩阵已迁入正式 frontend/e2e 与标准 Mock，默认全量 Playwright 执行。
- N03：已关闭；公开报告、执行状态、项目记忆和 notes 收尾结果已统一到最终计数与证据路径。
- N04：未验证；无提交/远端 CI 授权，不能把本机结果冒充 Linux Node 22/Python 3.11。
- N05：未验证；未启动真实服务、真实知识库或真实屏幕阅读器；保留明确后续条件。
- N06～N10：按维护备注保留，不擅自升级依赖、重发邮件或绕过清理策略。
- N11～N13：按设计边界保留，不作为未修 bug。

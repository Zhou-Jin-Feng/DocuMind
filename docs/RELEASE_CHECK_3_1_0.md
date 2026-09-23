# 3.1.0 发布前检查记录

- 日期：2026-09-24（补录最终候选身份与本地链路证据）
- 状态：`PASS WITH NOTES`（提交前检查；不是 Git tag、GitHub Release 或部署验收）
- 适用范围：DocuMind `3.1.0` 源码候选
- 说明：本记录用于固化源码、依赖、容器镜像和当前版本重跑证据；未执行 commit、tag、Release 或部署。

## 1. 源码与版本身份

| 项目 | 值 |
|---|---|
| 当前 Git HEAD | `b83194454771a0524f603cff566ae684fea366af` |
| 后端版本 | `3.1.0` |
| 前端版本 | `3.1.0` |
| 纯检索 Schema | `1.0` |
| 检索版本 | `dense-v1` |
| 数据库迁移 | 本轮未新增迁移脚本；Registry schema 和 Milvus 数据结构未改变 |

检查基线为 HEAD `b83194454771a0524f603cff566ae684fea366af`，生成清单时工作树为 dirty。当前候选差异含 19 个代码、测试、依赖、构建配置及相关文档文件；另记录 10 个未修改的依赖/构建基线输入。逐文件字节数和 SHA-256 见 [`RELEASE_CHECK_3_1_0_CANDIDATE_MANIFEST.json`](RELEASE_CHECK_3_1_0_CANDIDATE_MANIFEST.json)，清单 SHA-256：`c0b18a120da0134c3350584766906fa768529682a8dda7a314b9536637858547`。

清单不含凭据或本地环境值；排除运行数据、生成产物、缓存、用户浏览器配置/个人状态，以及与发布无关的本地文件。仓库自有 `frontend/playwright.real.config.ts` 是真实服务验收测试的可复核输入，已纳入清单，不属于用户浏览器配置。发布检查记录自身及清单文件不相互纳入哈希：检查记录引用清单指纹以避免循环依赖；记录自身最终 SHA-256 保存在私有过程记录中。该清单描述 HEAD 加指定工作树候选差异，不等于最终发布提交身份；正式发布前应根据最终提交重新生成并复核候选身份。

## 2. Python 依赖锁定

| 项目 | 值 |
|---|---|
| 锁定文件 | `requirements.lock` |
| SHA-256 | `cb75c974054aaa3bfee5c9306fc126b28635a7e37540ae2a23b365809478d37a` |
| 行数 | 131 |
| 来源镜像 | `documind-r6-sandbox-api`，镜像 ID `sha256:b8dd589399fd420a8e7e26eaca12180d5844d7762710b2a89247e0d7a7c886e6` |
| Python 基座 | `python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7` |

验证命令（Python 3.11 基座容器）：

```powershell
python -m pip install --dry-run --no-deps --ignore-installed `
  --extra-index-url https://download.pytorch.org/whl/cpu `
  -r requirements.lock
```

结果：`PASS`。全部 123 个已解析包均可从 PyPI 与 PyTorch CPU 索引解析；`torch==2.14.0+cpu` 需要 `https://download.pytorch.org/whl/cpu`。`requirements.txt` 仍是直接依赖输入，`requirements.lock` 是用于复核已构建 Python 3.11 环境的完整快照。

## 3. 容器镜像身份

| 用途 | 固定引用 |
|---|---|
| Python 构建基座 | `python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7` |
| Node 构建基座 | `node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85` |
| Milvus | `milvusdb/milvus:v2.6.4@sha256:27f1732a6668c813ee96d21364e3ba220ce1dd1d6e07660106d646dc33d1c654` |
| etcd | `quay.io/coreos/etcd:v3.5.18@sha256:d0a641d5fbcc89678c931a61b7de7b8a1cf097149f135c9c73bc81d076a1494b` |
| MinIO | `minio/minio:RELEASE.2025-04-22T22-12-26Z@sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e` |

容器身份文件：

- `compose.yaml` SHA-256 `4c441eef69977f38cfc9c2487c7ac32c5da9d2349f3f27aae562ac6aa05be466`
- `Dockerfile` SHA-256 `1d9c130b9bb8335eb5fe4ea042280f4546651b96be4af834c0dd15a18ce51703`
- `frontend/Dockerfile` SHA-256 `0c4c88e465a1286a86bf40a7142f4aa57c35ceb02512cd2c1be2a14c4d6a85bc`

验证：`docker compose config` 通过；使用固定 Python 基座重新构建 API 通过。R6 运行镜像为 `sha256:b8dd589399fd420a8e7e26eaca12180d5844d7762710b2a89247e0d7a7c886e6`；固定基座重建后得到 `sha256:264ce8de3c2b46c44284396b407db77bb5d2feeb46d0ef91fa9b7570e55b1c10`，两者共享相同层/config 摘要 `c4067bdc8a116214ca3617cb65007c43cfb03d4e27b67be0f841f5340eb60545` 与 `daa0bbab7fe8fea59c1f8fe70fc944c977210082fb1bcdba7b98c5a5823f6f12`。

## 4. 当前版本确定性重跑

当前源码重跑命令：

```powershell
python -m evaluation.runner `
  --output-json artifacts/evaluation/current-3.1.0-remediation.json `
  --output-markdown artifacts/evaluation/current-3.1.0-remediation.md

python -m evaluation.regression_runner `
  --baseline evaluation/baselines/deterministic_dense_v2.json `
  --current artifacts/evaluation/current-3.1.0-remediation.json
```

结果：

- 报告 JSON SHA-256：`00e54dcfa7116c9f4b1d7d564a2cbebc8e8ec24a7360d2457f3312c254924925`
- 报告 Markdown SHA-256：`30a2c394f5dc391273b18fbb7e5096526c7fb65781a72524a417fbd03006cb12`
- 回归门禁：`PASS`，检查 `mrr_at_k`、`no_answer_retrieval_accuracy`、`precision_at_k`、`recall_at_k`、`successful_case_rate`、`top_k_hit_rate`
- 当前确定性指标：Recall@K `0.8333`、MRR@K `0.7500`、successful_case_rate `1.0`、P95 `1.0751 ms`

`artifacts/` 是可再生成的本地输出，不进入 Git；发布检查以报告哈希和复跑命令为准。

## 5. 前端生产构建与真实浏览器边界

- `npm run typecheck`：PASS。
- `npm run build`：PASS；`dist/assets/index-DA7tabYf.js` 650,266 B，SHA-256 `a1c69e1afa80da48915b10ca8f8172233ede03ae957a648a767fb8d2e4a836d3`；`dist/assets/index-D6CMbHgn.css` 26,146 B，SHA-256 `376a5c19f50c7ba6f11ab03ab0d225ffadd9d689d7ff79bd287ade640b7d83ab`。与 FE-06 报告中的最终普通产物哈希一致。

### 本地 SSE 客户端断连终态观测

- 源码身份按上述候选清单逐文件绑定：`app/services/rag_service.py` SHA-256 `e55dc4ba56b31f3062cb9ba2511f941342dc5c6c8239f178b89b6aab29f1e1af`；对应单元测试 `tests/test_observability_events.py` SHA-256 `aafd60c0af0a1973970c06b25542483695dc4d3a43639a42a7ee2e3a7317b5ef`；真实断连测试 `frontend/e2e-real/real-sse-disconnect.spec.ts` SHA-256 `2494f1b66d6f355e6257c03703434cd13bd6b58b6ca01f3dcf7ecb7a751a90c1`；字段说明 `docs/OBSERVABILITY.md` SHA-256 `49e418037dbc7af8d22767480d3ba95837a5ec92d76190b612d00ba909d7f73a`。
- 留存的本地隔离链路证据：真实客户端收到首个 token 后发出 abort；HTTP 200；服务端按同一 request ID `7aa2da8cba8840bf8d69ac345b3624f9` 观察到唯一 `response_stream_terminated` 事件，`status=client_disconnected`、`terminal_event=none`，未观察到该请求的其他终态事件。样例文档清理后列表为 0、详情请求返回 404。单元测试 5/5 通过，真实 Playwright 用例 1/1 通过；本记录引用已保存证据，没有重新启动 Compose 或发送在线请求。
- 身份限制：保存的断连证据包含 Compose 项目名、日志事件和 request ID，但没有 API 容器镜像 ID或构建上下文摘要，因此无法事后以密码学证据将该日志精确绑定到某个镜像字节。上述 SHA-256 识别的是本次候选工作树中的实现、测试和字段文档；不将历史 R6 镜像摘要倒推为该次断连运行的镜像身份。历史镜像及报告继续保持各自原始时间和适用范围。
- 该验证只证明本地服务观察到客户端关闭响应流并记录事件；不证明上游 Provider 已停止计算或已停止计费，也不等同 Provider 飞行中任务取消。

- 可选真实浏览器验收：`DOCUMIND_REAL_API=http://127.0.0.1:8011 npm run test:e2e:real`；测试 `frontend/e2e-real/real-sse-isolation.spec.ts` 验证真实 SSE 下的跨回答来源面板隔离和新建对话零残留。
- 本次运行：1 passed；真实 SSE HTTP 200；新回答来源面板只显示新文档来源且不包含旧来源，新建对话无旧引用/高亮残留。
- 生成质量边界：本轮本地 Ollama 生成返回空文本，API 记录 `RuntimeError: LLM stream returned no text`，浏览器新回答显示 `service_unavailable`；citation chip 高亮检查跳过。引用隔离通过，生成质量不作为通过项。
- 本地生成不可用路径另有隔离链路验证：移除本地 Ollama OpenAI 兼容别名后，纯检索仍返回 HTTP 200 和 Chunk，流式问答返回 `service_unavailable`、`partial=false`、`retryable=true`。这是应用对本地 Provider 不可用的错误映射验证，不证明外部 Provider 可用性或 Provider 取消能力。
- 生成质量负例：R6 扩展 run2 返回 `done(success)` 并有来源事件，但答案内容截断为“控制项……的保留期为 ”，缺少文档中的数值；该案例明确保留为生成完整性负例，不按成功终态推定答案质量通过。
- 空生成时 citation chip 数量为 0，因此高亮断言跳过；该项仍未验证，不得表述为高亮验收通过。
- 外部 Provider：本轮未进行外部付费生成验证；Provider 可用性、账单、生产部署、Release/tag、SLA/压力仍未验证。

## 6. 历史证据与当前证据边界

- `evaluation/reports/` 中的 DS-04、DS-05、DS-06 和 P2-01 报告是 `v2.2.0` 历史证据，不是 `3.1.0` 当前版本重跑。
- 本文第 4 节是当前源码的确定性重跑证据，不能与 DS-06 真实 holdout 指标直接互比。
- 历史 R6 镜像及重建摘要仅标识原始历史镜像/重建，不证明新增 SSE 关闭事件实现已包含在这些镜像中；SSE 实现由当前候选文件 SHA-256 标识，而实际断连证据缺少镜像 ID，来源到镜像的精确映射不可恢复。
- DA-03 v2、DA-04/DA-05 真实语义对照、DP-03/04/05 阴性结论和 R6 真实最小链路属于候选期间的私有复核证据，不替代公开 Release 报告；`docs/EVALUATION.md` 已用正式语言总结结构化上下文候选未采用、Dense-only baseline 不变。
- 独立文档题集补充复核：15 题（14 可回答、1 无答案边界），源文档及事实族与 DA-03 冻结输入无重合；真实 Ollama Embedding 下 baseline 与候选均为 14/14 完整证据单元命中、MRR@3 `0.8929`、执行失败 0。边界题两方案都返回 3 条候选，无答案空结果准确率 `0.0000`；该结果不是拒答、答案生成或生产 SLA 通过证据，baseline 选择维持不变。明细和冻结身份见项目私有 `agent/过程记录/DA-04-实验/holdout-20260923/`。
- R6 已在隔离沙箱完成一次真实上传、active、流式问答、来源返回、证据不足问题和删除清理；使用本地 Ollama OpenAI 兼容别名，不代表外部付费 Provider 或生产部署已验证。

## 7. 结论与剩余边界

**发布前检查结论：** `PASS WITH NOTES`。源码版本、依赖快照、容器镜像身份和当前版本确定性回归均有可复核记录；已具备候选版本审查所需的源码与验证记录。

剩余边界：

- 未执行 commit、tag、Release、部署或生产环境验收。
- 外部 OpenAI/Anthropic/DeepSeek/GLM Provider、Provider 飞行中任务取消、生产部署、压力/SLA 未验证。本地生成不可用错误映射与 SSE 客户端断连日志已验证，但均不证明 Provider 上游计算/计费已停止。
- R6 run2 的答案截断及真实浏览器空生成仍是生成质量负例；citation chip 高亮断言因空生成而跳过，仍未验证。
- DA-03 final 集合已被观察，不构成跨集合或生产单文档泛化结论。补充文档题集仅覆盖两份文档，不构成跨语料或生产 SLA 证据。
- 正式发布前应记录最终提交哈希、镜像身份和报告指纹。

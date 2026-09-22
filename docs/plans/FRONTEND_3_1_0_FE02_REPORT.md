# DocuMind 前端 3.1.0 FE-02 组件与状态必要拆分

日期：2026-09-21

状态：FE-02 `PASS`，等待人工确认；未进入 FE-03。

适用计划：`docs/plans/FRONTEND_3_1_0_PLAN.md`

## 1. 范围与结论边界

FE-02 只完成既定的视图拆分、会话状态归并和流请求生命周期整理，并修复跨会话旧请求
污染风险。本阶段不实现 token 缓冲、消息 memo、滚动策略、视觉变量、弹窗焦点、正文引用
定位或代码高亮，也不安装新依赖、不修改 3.0.0 版本号、不提交、不推送、不发布或部署。

阶段结论为 `PASS`：本阶段验收项均有自动检查与独立只读复审证据，未发现未关闭的
FE-02 缺陷。FE-03 仍需单独获得人工确认后才能开始。

## 2. 实现结果

### 2.1 视图与页面组装

以下既有视图已从 `App.tsx` 移出，保留原有 DOM 语义、class、文案和交互：

- `components/MessageList.tsx`：`MessageList`、`MessageItem` 和 Markdown 呈现。
- `components/Composer.tsx`：受控输入、Enter 发送、停止/发送状态。
- `components/ConversationHistory.tsx`：本地历史列表及选择/删除命令。
- `components/Documents.tsx`：文档项、上传进度、详情与删除确认。
- `components/ConfirmationDialog.tsx`：会话清理确认。
- `components/SourceItem.tsx`：来源片段呈现。

`App.tsx` 保留查询、mutation、页面组装和少量协调逻辑。文件由阶段前约 1,315 行缩减为
771 行，但阶段完成依据是职责与行为验证，不是行数。

### 2.2 会话状态模块

新增 `features/chat/conversationState.ts`。模块通过单一 `conversationReducer` 接口隐藏会话、
消息、标题、终态和不可变更新细节；异步回答更新必须携带
`conversationId + answerId`。

已验证的不变量：

- `turn/start` 原子插入 user/assistant 消息，重复或缺失身份返回原 state。
- 只替换目标 message、messages 数组和 conversation，非目标引用保持稳定。
- `done` / `error` 为终态，迟到的 status、sources、token、stop 或其他终态更新 no-op。
- stop、complete 和 fail 保留已接收 partial；无正文时才使用对应 fallback。
- 删除、清空和 inactive conversation 操作均基于 reducer 收到的最新 state。
- reducer 内不读取时间、不执行 I/O；`updatedAt` 由命令显式注入。

### 2.3 流请求模块

新增 `features/chat/streamController.ts`。对 App 只暴露 `start`、`stop`、`dispose`，生产
transport 继续使用现有 `streamChat`；内部持有
`requestId + conversationId + answerId`、AbortController 和 active run。

FE-02 仍直接转发 token，不启用约 50ms 缓冲。已验证：

- 同时最多一个逻辑 active run；`start(B)` 会先同步 settle/abort A，再登记 B。
- event、reject、resolve 和异常 EOF 都先核对 active run 与 requestId。
- stop 的可观察顺序为：写 stop 终态 -> active identity 置空 -> abort transport。
- SSE error、APIError、普通网络错误和无终态 EOF 都只形成一个错误终态。
- `dispose` 静默 abort 并永久拒绝后续回调，不向已卸载页面写终态。

### 2.4 App 接线与来源归属

每轮请求在创建时生成独立 requestId、conversationId、answerId。来源选择保存为
`{ conversationId, answerId }`，面板内容从对应回答派生；旧请求不能再覆盖一个全局 sources
数组。新建、切换、删除和清空当前会话均先停止活动流，再发送 reducer 命令。

controller 在 effect setup 中创建并写入 ref，cleanup 只 dispose 该次 setup 的实例。这个
生命周期满足 React 开发态 StrictMode 的 `setup -> cleanup -> setup` 重放，也保持
`dispose` 的永久语义。

本阶段未新增运行依赖，TanStack Query 仍单独管理服务状态、文档列表与详情数据。

## 3. 受控竞态证据

新增浏览器场景确定性制造以下顺序：

1. A 收到自己的 source 与 partial，随后用户新建会话；A 被逻辑 stop。
2. 测试闸门暂缓把 A 的 abort 传给底层 fetch，使 A 的 Promise 尚未 reject。
3. B 启动并进入 pending，停止按钮和 B 的 source 已可见。
4. 释放 A 的 abort，使 A 的旧 rejection 晚于 B 激活；B 的 active 状态和来源保持不变。
5. 释放 B，B 正常完成；localStorage 中 A 为 partial + done + source A，B 为完整正文 +
   done + source B。
6. 切回 A 后只显示 A 的正文和来源，B 内容不可见。

Mock 控制器位于 `e2e/mock-api.mjs`，浏览器用例位于 `e2e/workbench.spec.ts`。该场景同时
覆盖旧 finally/rejection 不清除 B、partial 可恢复以及来源不跨回答串写。

## 4. 持久化与 3.0.0 兼容

`conversations.ts` 的生产实现未变，仍使用键 `rag-workbench-conversations-v1`，最多保存
12 个会话、每个会话最近 60 条消息。

新增测试直接加载 3.0.0 结构的序列化数据，包含 `generating` partial 和来源，确认不会
静默清空或迁移；另有显式测试固定既有 key 与 12/60 截断规则。旧
`retrieving/generating` 记录目前按原值恢复，不在 FE-02 擅自改写终态；最终产品处理仍按
计划留到 FE-06 交代。

## 5. 验证结果

| 检查 | 最终结果 |
|---|---|
| `npm ls --depth=0` | 退出码 0；依赖树完整，无 FE-02 新依赖 |
| `npm test` | 退出码 0；4 个文件、28/28 测试通过 |
| reducer + controller 定向测试 | 2 个文件、21/21 通过 |
| `npm run typecheck` | 退出码 0 |
| `npm run build` | 退出码 0；CSS 23.70 kB / gzip 5.21 kB；JS 423.81 kB / gzip 131.22 kB |
| 普通产物隔离 | JS 423,811 B，SHA-256 `CC60A1FF...27670D59`；无 FE-01 计数标记 |
| `node --check e2e/mock-api.mjs` | 退出码 0 |
| `npx playwright test --list` | 收集 1 个文件、7 条用例 |
| `npm run test:e2e` | 退出码 0；7/7 通过，最终复跑 14.9s |
| `npm run build:fe01` | 退出码 0；专用 profiling 构建通过 |
| `npm run test:fe01` | 退出码 0；专用高频流式用例 1/1 通过 |
| `git diff --check` | 退出码 0；仅 Git LF -> CRLF 提示 |

一次最终 E2E 复跑在收集前因上一轮 4174 端口尚未释放而拒绝启动；只读检查时监听已自行
退出，未结束任何未知进程，随后同一命令 7/7 通过。该现象归类为测试清理时序注记，不是
产品失败。

专用性能用例此前可能刷新忽略目录中的 FE-01 基线文件。R1/R2 修补后，FE-01/FE-03 配置显式声明各自报告路径，缺少输出配置时直接失败，不再静默覆盖基线。本阶段历史复跑只用于验证拆分后测量链路，不把其数字冒充 FE-01 原始基线或 FE-03 优化收益；FE-01 已发布汇总仍以 `FRONTEND_3_1_0_FE01_REPORT.md` 为准。

## 6. 复审与剩余边界

主线自检及 reducer、controller/App、浏览器竞态三个并行子任务均完成。两份独立只读复审
结论均为 `PASS`，未发现需要报告的代码缺陷。

以下内容是既定后续范围，不属于 FE-02 未完成项：

- FE-03：首 token 后约 50ms 合并、MessageItem memo、滚动所有权及同夹具性能对照。
- FE-04：设计变量、可读性、弹窗/抽屉焦点和提示语义。
- FE-05：回答级引用定位、代码高亮和空状态。
- FE-06：整体验证、旧中间态最终说明和 3.1.0 版本同步。

本机为 Node 24，CI 目标为 Node 22；本阶段未触发远端 CI，最终候选仍需由 CI 复核。

## 7. 阶段结论

FE-02 结论：`PASS`。组件职责、状态定位和请求生命周期已按 FE-01 冻结接口落地；现有
文档、会话、SSE、停止、持久化与来源行为无回退，受控跨会话竞态已通过。

当前停在 FE-02 人工闸门。获得明确确认前，不进入 FE-03，不执行 Git commit/push、版本
同步、发布或部署。

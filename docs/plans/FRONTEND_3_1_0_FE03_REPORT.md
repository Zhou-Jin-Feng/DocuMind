# DocuMind 前端 3.1.0 FE-03 流式与滚动优化

日期：2026-09-21

状态：FE-03 `PASS`，等待人工确认；未进入 FE-04。

适用计划：`docs/plans/FRONTEND_3_1_0_PLAN.md`

## 1. 范围与结论

FE-03 完成了 token 合并、终态尾字处理、历史 Markdown 渲染隔离、聊天滚动所有权、
停止后持久化以及固定夹具性能对照。本阶段没有安装依赖，没有修改后端、检索行为、版本号、
引用语法、弹窗焦点或视觉变量，也没有执行 Git commit/push、发布或部署。

阶段结论为 `PASS`。最终正文和请求身份保持正确，所有性能门槛、浏览器行为和回归检查通过。
FE-04 仍需单独人工确认后才能开始。

## 2. 诊断反馈环

实施前先建立三条能捕获原缺陷的确定性反馈环：

| 反馈环 | 修复前信号 | 已确认根因 |
|---|---|---|
| stream controller fake scheduler | 16 条中 8 条失败；后续 token 逐个转发，pending/timer 不存在 | token 事件直接 dispatch，没有批次和统一终态 flush |
| 真实 Chromium MessageList 渲染 | 只替换当前回答时，两条历史消息各新增 1 次 Markdown 渲染 | `MessageItem` 未 memo，App 的来源 callback 每次 render 变化 |
| Playwright 滚动场景 | 6 条中 5 条失败；窄屏 `window.scrollY=5415`、上滚后漂移 139px、无“回到最新”、3 次 smooth、reduced-motion 仍 smooth | `[messages]` 无条件 `scrollIntoView({smooth})` 与 CSS smooth 抢占滚动位置 |

修复后独立审查还发现一项 start 重入竞态：A 被 B 替换时，A 的同步 stop 回调若启动 C，
外层 B 会覆盖 C，留下未 abort 的孤儿 transport。新增回归测试先稳定得到 `A,C,B`，再以
controller 级 start generation 修复为 `A,C`。

## 3. 实现结果

### 3.1 流式 controller

- 第一个非空 token 同步派发，空 token 不创建更新。
- 后续 token 使用单个 one-shot timer，默认间隔 50ms；timer 触发后一次合并派发 pending。
- done、SSE error、network/API rejection、异常 EOF 和 manual stop 统一执行：取消 timer、
  同步 flush pending、写终态、清活动身份；manual stop 最后 abort transport。
- dispose 只取消 timer、丢弃 pending、abort 并永久拒绝回调，不向卸载页面写终态。
- timer generation、active run/request identity 和 start generation 共同隔离旧 timer、event、
  promise completion 与同步重入 start。
- controller 对 App 的命令接口仍为 `start/stop/dispose`；计时回调是可选 profiling 接缝。

### 3.2 消息渲染

- `MessageItem` 使用标准浅比较 `memo`，继续依赖 reducer 保持非目标消息对象引用稳定。
- App 的 `onOpenSources` 使用 `useCallback`，只在 active conversation identity 变化时更新。
- `remarkPlugins` 使用模块级稳定数组；Markdown 安全默认值未改，不启用原始 HTML。
- 真实 Chromium 测试验证当前回答 Markdown 正常更新，同时两条未变化历史消息新增解析均为 0。

### 3.3 滚动所有权

- `.message-list` 是唯一聊天滚动容器；删除 App 的全局 `scrollIntoView` effect 和 CSS
  `scroll-behavior: smooth`。
- 距底不超过 64px 时跟随；滚轮、触摸、指针或键盘上滚离底后停止跟随并显示“回到最新”。
- 自动流式跟随直接设置容器 `scrollTop`，不逐批启动 smooth 动画。
- 点击“回到最新”才使用 smooth；`prefers-reduced-motion: reduce` 时改为 auto。
- 点击后先把焦点移交给带可访问名称的消息列表，再卸载“回到最新”按钮，避免键盘焦点退回页面。
- 新问题增加 tail identity、切换会话或显式回底会恢复跟随；窄屏不再滚动整个 window。
- 按钮可见性以 ref 去重，避免每个 scroll event 重复提交相同 React state。

### 3.4 持久化与测量

- 生产保存策略仍只在非流式期间写 `rag-workbench-conversations-v1`，没有逐 token 写盘。
- slow 流浏览器测试确认连续新增至少 3 个字符期间目标 key 写入数不变；停止后 storage 正文
  与 DOM 尾字逐字一致、stage 为 done，reload 后完整恢复。
- profiling 分开记录原始 token 接收与 first/timer/terminal 正文批次，延迟从原始 token 到
  下一次消息 DOM mutation 计算，避免把 50ms 缓冲漏出测量窗口。
- FE-03 使用独立构建、Playwright 输出和 `streaming-after.json`，没有覆盖 FE-01 路径。

## 4. 固定夹具性能对照

条件与 FE-01 相同：50 条已完成历史消息、10,000 字固定 Markdown、200 个 50 字分块、
Mock 目标间隔 10ms、Vite production profiling、headless Chromium、1280x720、三轮。
本机实际服务端分块间隔中位数为 15.546-15.576ms，必须与 10ms 目标值分开陈述。

FE-01 前测采用已发布报告 `FRONTEND_3_1_0_FE01_REPORT.md` 的冻结汇总。忽略目录中的
`fe01/streaming-baseline.json` 曾在 FE-02 测量设施复跑时刷新，因此不把当前动态文件冒充
原始前测。FE-03 执行期间该文件 SHA-256 始终保持
`7EC1C47609BAACEF1830FE2CA5A122AB1E467E0B2CC814AB28D6CB82BA47C152`，未再次覆盖。

| 指标 | FE-01 范围 / 中位数 | FE-03 范围 / 中位数 | 结论 |
|---|---:|---:|---|
| React commit | 172-182 / 172 | 52 / 52 | 中位数下降约 69.8% |
| 历史 Markdown 重渲染 | 8,600-9,100 / 8,600 | 0 / 0 | 不随 token 增长 |
| 正文批次数 | 基线逐 token 更新 | 50 / 50 | 200 token 被合并 |
| 常规 timer 批次频率 | 未单独计量 | 15.60-15.80/s / 15.71/s | 低于约 20/s 门槛 |
| 首 token 可见延迟 | 未单独计量 | 5.8-17.4ms / 7.2ms | 首段及时显示 |
| 各轮可见延迟中位数 | 14.4-16.0ms / 15.6ms | 42.0-42.6ms / 42.1ms | 增量在 100ms 预算内 |
| 各轮可见延迟 P95 | 19.6-20.5ms / 19.6ms | 64.9-65.3ms / 65.0ms | 三轮均低于 100ms |
| 单 token 最大可见延迟 | 前测未汇总 | 67.2-72.9ms / 72.2ms | 三轮均低于 100ms |
| 总耗时 | 3,380.2-3,491.6ms / 3,442.5ms | 3,612.4-3,702.6ms / 3,650.5ms | 中位数增加约 6.0% |
| Long Task 数 | 0 | 0 | 无新增 Long Task |
| frame duration 中位数 | 前测未汇总 | 16.7ms / 16.7ms | 仅限本机合成场景 |
| frame duration 最大值 | 最大 33.5ms | 16.8ms / 16.8ms | 无 >50ms frame |

三轮均收到 200 个原始 token；正文长度均为 10,000，SHA-256 均为
`c231263722368c8cf37a5c1400e05c25b8233ee8adae757fae81dd92d2116856`。每轮 first 批次均为
1；timer 批次均为 48；terminal flush 均为 1；所有批次字符总和均为 10,000。

总耗时增加是明确的取舍，不隐藏为收益：50ms 合并把通常等待从约 15ms 提高到约 42ms，
换取 commit 和历史 Markdown 工作量大幅下降。所有可见延迟仍低于既定 100ms 门槛。
这些数字只代表本机隔离 Mock，不能外推真实 Provider、后台标签页或所有用户设备。

修补后后测：`artifacts/frontend-3.1.0/fe03/streaming-after-r2.json`。FE-03 Playwright 配置显式设置该路径，benchmark 缺少输出配置时拒绝运行，不再默认写入 FE-01 基线。

## 5. 验证结果

| 检查 | 最终结果 |
|---|---|
| controller 定向测试 | 17/17 通过，含 50ms、五类终态、dispose、stale timer 和 start 重入 |
| `npm test` | 5 个文件、38/38 通过；含真实 Chromium Markdown 隔离 |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过；CSS 24.14 kB / gzip 5.31 kB；JS 426.04 kB / gzip 132.02 kB |
| 普通产物隔离 | JS 426,039 B，SHA-256 `62245290...9E20C8A`；无 profiling 标记 |
| `npm run test:e2e` | 13/13 通过；原 7 条 + FE-03 滚动 6 条 |
| `npm run build:fe03` | 独立 production profiling 构建通过 |
| `npm run test:fe03` | 1/1 通过；内部执行三轮并强制性能门槛 |
| controller 独立复审 | PASS；重入修复、同步 throw、stop/dispose/timer 无新增发现 |
| 消息与滚动独立复审 | PASS；按钮卸载前焦点移交、真实 scrollTo reduced-motion 覆盖均关闭 |

Playwright 仅出现 `NO_COLOR` 被 `FORCE_COLOR` 忽略的提示，不影响结果。一次并行运行中，
内嵌 Chromium 渲染测试的 5 秒导航上限受资源竞争超时；独跑已通过，测试上限调整为 15 秒后
完整 `npm test` 通过。该现象属于测试进程竞争，不计为产品通过证据，也不掩盖失败。

## 6. 剩余边界

- 真实后端、真实模型、后台标签页冻结和低性能设备未在 FE-03 重测。
- dispose 按设计丢弃尚未 flush 的 pending；正常 done/error/reject/EOF/stop 才承诺同步保留。
- 旧 3.0.0 `retrieving/generating` 持久记录仍原样兼容，最终说明留在 FE-06。
- FE-04 的视觉变量、字体、焦点管理和弹窗/来源抽屉可访问性尚未开始。
- 当前工作树仍包含 FE-01/FE-02/FE-03 未提交成果；本阶段未获 commit/push 授权。

## 7. 阶段结论

FE-03 结论：`PASS`。正文完整性、跨请求隔离、终态尾字、历史渲染、持久化、滚动所有权、
焦点移交、reduced motion 和固定夹具性能门槛均已通过，独立复审没有未关闭问题。

当前停在 FE-03 人工闸门。获得明确确认前，不进入 FE-04，不执行 Git commit/push、版本同步、
发布或部署。

## 8. FE-01～FE-03 独立复审修补补充

R1：CI 与本地可复制命令先安装 Chromium，再运行 npm test；MessageList 渲染测试在浏览器 launch、Vite listen 和页面测试外层统一 finally 清理。干净浏览器缓存先安装 Chromium 后，定向测试 1/1 与完整 npm test 38/38 通过。

R2：FE-03 配置默认将 benchmark 报告写入 `artifacts/frontend-3.1.0/fe03/streaming-after-r2.json`；缺少路径配置时 benchmark 直接失败，FE-01 baseline 不再被静默覆盖。工作树中原始 FE-01 JSON 已不可恢复，现有 baseline 文件不被重新解释为原始前测；冻结汇总保留其历史边界。随后在可信 HEAD 3a9bf0c 隔离 worktree 上重建 `fe01-baseline-rebuilt`，与最终候选组成 `paired-measurement-rebuilt-20260921.json`，同一夹具的源码/依赖/环境指纹可复核。修补后 FE-03 三轮复测的正文 SHA、token 数和历史 Markdown 隔离均通过。

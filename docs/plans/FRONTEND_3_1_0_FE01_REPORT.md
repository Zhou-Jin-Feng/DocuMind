# DocuMind 前端 3.1.0 FE-01 基线与实施设计

日期：2026-09-20

状态：FE-01 `PASS WITH NOTES`，已于 2026-09-20 获人工确认；FE-02 已开始。

适用计划：`docs/plans/FRONTEND_3_1_0_PLAN.md`

## 1. 范围与结论边界

FE-01 只建立可复现基线、确认现有问题并确定后续实施接口。除仅在专用构建中启用的
测量设施外，本阶段不改变产品行为，不安装候选运行依赖，不同步 3.1.0 版本，也不执行
提交、推送、发布或部署。

本报告中的性能数字来自本机隔离 Mock 和生产模式 profiling 构建，只用于后续同夹具
前后对照，不能外推到真实 Provider、真实数据或所有用户设备。视觉结论只覆盖列出的
视口、状态和控件。

## 2. 起始状态与环境

| 项目 | 实测值 |
|---|---|
| 分支 / 起始 HEAD | `main` / `3a9bf0c9980f4109482f078ee697c527a99e44ae` |
| 开始前工作树 | `?? docs/plans/`，属于开始前已有内容，本阶段保留 |
| 应用源码版本 | `3.0.0`；目标 `3.1.0` 只在 FE-06 同步 |
| Node / npm | `24.18.0` / `11.16.0` |
| Python | `3.14.6` |
| Playwright / Chromium | `1.62.1` / `151.0.7922.34` |
| CI 目标环境 | Node 22 / Python 3.11 |

公开计划与交接文档内嵌副本去除首尾空白后逐字符一致，长度均为 9,769 字符。CI 与本机
主版本不同，后续候选仍需由 CI 复核，不能仅凭本机结果宣称跨环境通过。

## 3. 现有检查基线

| 检查 | 结果 |
|---|---|
| `npm ls --depth=0` | 退出码 0，依赖树完整 |
| `npm test` | 退出码 0；2 个文件、5 个测试通过 |
| `npm run typecheck` | 退出码 0 |
| `npm run build` | 退出码 0；CSS 23.70 kB / gzip 5.21 kB；JS 419.80 kB / gzip 129.26 kB |
| `npm run test:e2e` | 最终完整运行 6/6 通过 |

这里的构建表采用 Vite 控制台口径。第 8 节的精确字节采用 Node
`zlib.gzipSync(buffer, { level: 9 })`；两种数字都正确但算法/显示口径不同，不能相互换算后
作差。FE-06 只使用固定 zlib 算法的前后精确字节比较。

当前进程存在 `HTTP_PROXY/HTTPS_PROXY`，而 `NO_PROXY` 初始为空。Playwright 对回环服务的
探测会因此阻塞；只对测试进程设置 `NO_PROXY=127.0.0.1,localhost` 后可运行，未修改系统
代理。一次完整运行在 Chromium 加载应用前出现 `net::ERR_NO_BUFFER_SPACE`，当轮 5/6；
失败用例随后定向 3/3 通过，再次完整运行 6/6 通过。该现象暂记为本机资源波动，不计为
已确认产品缺陷。

普通生产构建恢复原始 JS 哈希 `index-DkVSiWcY.js`，且不含 FE-01 计数标记；profiling
开关在普通 Vite 配置中编译为 `0`，测量实现只进入专用构建。

## 4. 高频流式基线

### 4.1 固定输入与复现

- 50 条已完成历史消息。
- 10,000 字固定 Markdown 回答，包含中文段落、列表、表格、代码和引用。
- 200 个分块，每块 50 字，Mock 目标间隔 10ms。
- 最终正文 SHA-256：
  `c231263722368c8cf37a5c1400e05c25b8233ee8adae757fae81dd92d2116856`。
- 三轮均收到 200 个 token 事件；保存正文长度和 SHA-256 与发送端一致。

```powershell
cd frontend
npm run build:fe01
$env:NO_PROXY='127.0.0.1,localhost'
$env:no_proxy='127.0.0.1,localhost'
# 默认 FE-01 archive 为 create-only；已有归档时命令会明确拒绝覆盖。
npm run test:fe01
# 新建配对基线时必须指定新 archive 路径和 measurementKind，不得覆盖既有归档。
```

测量条件为 Vite production profiling 构建、React 19.2.8、React DOM 19.2.8、
react-markdown 10.1.0、headless Chromium 151.0.7922.34、`1280x720`。源码保留
StrictMode，但生产模式不执行开发期双调用。

### 4.2 三轮结果

| 指标 | 范围 | 三轮中位数 |
|---|---:|---:|
| React commit | 172-182 | 172 |
| 50 条历史消息 Markdown 重渲染 | 8,600-9,100 | 8,600 |
| 总耗时 | 3,380.2-3,491.6ms | 3,442.5ms |
| 各轮可见延迟中位数 | 14.4-16.0ms | 15.6ms |
| 各轮可见延迟 P95 | 19.6-20.5ms | 19.6ms |
| 服务端分块间隔中位数 | 15.534-15.574ms | 15.572ms |

目标计时器间隔为 10ms，但本机实际服务端分块间隔约 15.5ms，因此两者必须分开陈述。
三轮均未观察到 Long Task，记录的 frame duration 最大值为 33.5ms。这不证明当前实现
没有性能问题：基线明确显示未变化的 50 条历史消息在每次顶层更新时重复解析 Markdown，
且 200 个 token 导致约 172 次 React commit。

原始数据：`artifacts/frontend-3.1.0/fe01/streaming-baseline.json`。

## 5. 视觉、滚动与键盘基线

实测视口为 `1440x900`、`390x844`、`320x844`，覆盖初始页面、来源区域、文档详情、
文档删除确认和会话确认。完整探针、报告与 20 张截图位于
`artifacts/frontend-3.1.0/fe01/visual-agent/`。

| 编号 | 已复现现状 | 后续阶段 |
|---|---|---|
| KBD-01 | 文档详情打开后焦点留在背景；Tab/Shift+Tab 可逃逸；探针的 Escape/关闭按钮路径未恢复触发点 | FE-04 |
| KBD-02 | 会话确认没有安全初始焦点或焦点循环；键盘可进入背景；探针的 Escape/取消路径未恢复触发点 | FE-04 |
| KBD-03 | 窄屏来源抽屉 Escape 不关闭，首次 Tab 进入背景 textarea，关闭按钮路径后焦点落到 body | FE-04 |
| KBD-04 | composer textarea 匹配 `:focus-visible`，但最终无 outline/box-shadow | FE-04 |
| SCROLL-01 | `390x844` 和 `320x844` 恢复历史后 `window.scrollY=306`；桌面为 0 | FE-03 |
| ESC-01 | 文档内删除确认按 Escape 会关闭整个文档详情 | FE-04 决定一致行为 |
| LAYOUT-01 | 所测状态无整页横向溢出、关键控件重叠或左右越界 | 各阶段持续回归 |

静态代码与实测相符：messages 变化时无条件执行 smooth `scrollIntoView`，与窄屏
`scrollY=306` 的现象关联一致，但本阶段未做代码消融来证明单一因果；弹窗没有完整
焦点管理；窄屏来源区域有遮罩但无模态键盘行为；`.composer textarea { outline: 0; }`
覆盖通用焦点样式。探针验证的是键盘焦点可穿透和列出的关闭路径，没有覆盖遮罩下的背景
指针点击或每一种关闭顺序。视觉子任务完整主运行 3/3 视口有效；第二次运行完成桌面和 390px 后，
在 320px 页面导航前遇到 `ERR_NO_BUFFER_SPACE`，因此 320px 不写成双跑通过。

## 6. 后续实施接口

设计采用两个深模块：调用方只跨越小接口，消息不可变更新、请求身份、终态、计时器和
错误处理细节留在各自实现内部。FE-02 先保证身份和终态正确；FE-03 在同一流式接口内部
加入缓冲，不要求 App 再次改接入方式。

### 6.1 `conversationReducer`

建议位置：`frontend/src/features/chat/conversationState.ts`。持久化键和 12/60 截断规则仍由
`conversations.ts` 持有，不复制到 reducer。

```ts
export interface ConversationState {
  activeId: string;
  items: ConversationRecord[];
}

export interface AnswerTarget {
  conversationId: string;
  answerId: string;
}

export type AnswerUpdate =
  | { kind: "status"; stage: "retrieving" | "generating" }
  | { kind: "sources"; items: SourceReference[] }
  | { kind: "append"; text: string }
  | { kind: "complete"; fallback?: string }
  | { kind: "fail"; message: string }
  | { kind: "stop"; fallback?: string };

export type ConversationCommand =
  | { type: "conversation/new"; conversation: ConversationRecord }
  | { type: "conversation/select"; conversationId: string }
  | {
      type: "conversation/delete";
      conversationId: string;
      fallback: ConversationRecord;
    }
  | { type: "conversation/clear"; conversationId: string; at: string }
  | { type: "conversation/clear-all"; fallback: ConversationRecord }
  | {
      type: "turn/start";
      conversationId: string;
      userId: string;
      answerId: string;
      question: string;
      at: string;
    }
  | {
      type: "answer/update";
      target: AnswerTarget;
      update: AnswerUpdate;
      at: string;
    };

export function conversationReducer(
  state: ConversationState,
  command: ConversationCommand,
): ConversationState;
```

`ConversationCommand` 必须覆盖新建、选择、删除、清空、原子开始一轮问答和
`answer/update`。所有异步更新显式携带 `AnswerTarget`，不得读取执行当时的
`state.activeId` 决定写入位置。

核心不变量：

- `items` 至少一项，`activeId` 始终指向现存会话。
- `turn/start` 原子加入 user/assistant 两条消息，避免半完成状态。
- 目标不存在、身份重复、空追加或终态后的迟到事件均返回原 state 引用。
- 实际更新只替换目标 message、messages 数组和 conversation，其他引用保持稳定。
- `done/error` 为终态；迟到 token/status/sources 不得回退状态或修改正文。
- `updatedAt` 由 command 的 `at` 注入，reducer 内不读取时间或执行 I/O。
- 删除和清空必须基于 reducer 收到的最新 state，不能使用事件处理器的旧闭包快照。

### 6.2 `streamController`

建议位置：`frontend/src/features/chat/streamController.ts`。现有 `streamChat` 作为生产
transport 注入；测试使用可控 deferred fake。timer scheduler 是内部测试接缝，不进入
调用方日常操作面。

```ts
export interface ChatRunIdentity extends AnswerTarget {
  requestId: string;
}

export type ChatTransport = (
  question: string,
  callbacks: { onEvent: (event: ChatEvent) => void },
  signal: AbortSignal,
) => Promise<void>;

export interface TimerScheduler {
  setTimeout(
    callback: () => void,
    delayMs: number,
  ): ReturnType<typeof globalThis.setTimeout>;
  clearTimeout(handle: ReturnType<typeof globalThis.setTimeout>): void;
}

export interface ChatStreamControllerOptions {
  transport: ChatTransport;
  onUpdate(target: AnswerTarget, update: AnswerUpdate): void;
  onActiveChange(identity: ChatRunIdentity | null): void;
  scheduler?: TimerScheduler;
  flushIntervalMs?: number;
}

export interface ChatStreamController {
  start(input: { identity: ChatRunIdentity; question: string }): void;
  stop(): void;
  dispose(): void;
}

export function createChatStreamController(
  options: ChatStreamControllerOptions,
): ChatStreamController;
```

核心不变量：

- controller 内部身份是权威；React active identity 只是 UI 投影。
- event、catch、finally 和 timer 回调均先核对 request identity；旧请求不得清除新请求。
- 同时最多一个逻辑 active run；重复 stop/dispose 幂等。
- status/sources 不缓冲；FE-03 只缓冲 token，第一个非空 token 立即显示，后续采用 one-shot
  timer，任一 run 最多一个 timer。
- done、SSE error、network error、异常 EOF 和 manual stop 等用户可观察终止路径统一为：
  取消 timer -> flush pending -> 写终态 -> settle identity；manual stop 随后 abort transport。
- transport 正常 EOF 但没有 done/error 事件时形成错误终态，不能悄然留下 generating。
- `start(B)` 遇到仍活跃的 A 时，先同步 settle/abort A，再登记 B；A 的旧 Promise 后续为 no-op。
- `dispose` 是卸载清理：取消 timer、丢弃尚未派发的 pending、abort、禁止后续回调，不写终态；
  它不承诺浏览器在流式中途刷新时恢复未 flush 内容。

### 6.3 视图职责

- App 保留页面组装、TanStack Query 与少量协调，不复制服务端数据。
- MessageList/MessageItem 接收稳定身份和最小 props；历史消息 memo 隔离在 FE-03 用基线验证，
  不能仅因存在 `memo` 就宣称生效。FE-01 的 render/Markdown 计数调用必须移入
  MessageItem 的实际函数体和 Markdown 路径，不能继续放在父列表 map 中误计被 memo 跳过的 child。
- Composer 只负责输入与提交/停止命令，不持有流式实现细节。
- 来源选择保存所属 `conversationId + answerId`，展示数据从该回答的 `sources` 派生；
  FE-05 再实现 AST 引用节点和具体来源定位。
- Dialog 的焦点与背景隔离统一留在 FE-04，FE-02 不为拆文件创建不完整通用弹窗。

## 7. 依赖决定

FE-01 只决定候选，不安装依赖：

| 依赖 | 推荐版本 | 用途 | 替代方案与决定 |
|---|---:|---|---|
| `@radix-ui/react-dialog` | `1.1.23` | FE-04 弹窗焦点圈定、焦点恢复、背景隔离 | 原生 `<dialog>` 或继续手写均可行，但嵌套确认、focus trap/restore 和 inert 行为需要持续自维护；选择 Radix 的最小接入 |
| `rehype-highlight` | `7.0.2` | FE-05 Markdown 代码语法高亮 | 无高亮不满足范围；直接 lowlight + 精选 grammar 需自写 AST 插件，Shiki/Prism 会引入另一套引擎与额外复杂度；先选现成 rehype 插件，若 FE-06 体积不达标再评估精选 grammar 方案 |

兼容证据：Radix 1.1.23 的 peer 明确包含 React/React DOM 19，提供 ESM/CJS exports 且
`sideEffects:false`；react-markdown 10.1.0 的 React peer 为 `>=18` 并提供 `rehypePlugins`，
rehype-highlight 7.0.2 是 ESM rehype 插件且没有 React/Vite peer。当前 lock 为 React/DOM
19.2.8、react-markdown 10.1.0、Vite 7.3.6；两次 `npm install --dry-run` 解析均为
changed/remove 0。Vite 7.3.6 要求 Node `^20.19 || >=22.12`；本机 Node 24.18 满足，CI
的浮动 Node 22 当前应满足，但以后若固定小版本不得低于 22.12。

Bundlephobia 在 2026-09-20 给出的独立包估算为 Radix Dialog `12,585 B gzip`
（12.6 kB / 12.3 KiB）、rehype-highlight `48,636 B gzip`（48.6 kB / 47.5 KiB）。这不是
当前应用的实际增量：rehype 估算可能包含当前树已有的 unified/vfile 依赖，真实结果还受
Vite 去重、tree-shaking 和主题 CSS 影响。FE-06 必须以同一源码基线的真实生产构建差复核。
`rehype-highlight` 默认静态引入 common grammars，即使运行配置限制语言，也不能预先宣称
bundle 会按语言子集缩小；它不自带主题 CSS，最终选择的主题样式也必须计入 CSS 增量。

当前 manifest、lock root、lock package 节点和 node_modules 四处均无这两个候选；lockfile
工作树 blob 与 HEAD 均为 `b9ee56c9e54897d386f68e44db787e683afb1c5c`。`package.json`
只新增 FE-01 两个测量脚本，没有 dependencies 变化。获准进入对应阶段后，应按仓库惯例把
`^1.1.23` / `^7.0.2` 写为 production direct dependencies，并让 lock 固定精确解析版本。

保留 Markdown 安全默认值：不启用原始 HTML，不用字符串拼接注入 HTML；未知语言退化为
纯文本。React、react-markdown 和 Vite 本轮不升级。reducer/controller 无需新增依赖。

## 8. 后续阶段详细任务与验证

### FE-02：组件与状态必要拆分

1. 实现 reducer，修复显式会话/回答定位和删除旧闭包覆盖风险。
2. 实现 controller 的请求身份、停止、异常 EOF、旧 finally 隔离和幂等清理；本阶段 token
   仍可直接转发，先保证语义正确。
3. 抽出 MessageList、MessageItem、Composer 及已有独立视图，App 以组装为主；不改视觉。
4. reducer 定向测试覆盖：A 流中 select B 后 target A 只更新 A 且 active 仍为 B；删除/清空 A
   后的迟到事件返回同一 state 引用且不改 B；append 后删除 inactive B 不丢 A 正文；
   done/error 后迟到事件 no-op；非目标引用保持，重复 ID/空 append no-op。
5. controller 用 fake transport 覆盖 A stop 后立即 start B、旧事件/旧 finally、异常 EOF、
   dispose 幂等；stop/switch 后 partial 为 done，save/load 后正文完整且既有 key/12/60 规则不变。
6. 增加 controlled-Mock E2E：A 流中切换并立即发送 B，验证 B 的停止按钮、完成和来源不被
   旧 finally/sources 破坏；同时运行现有 5 个 Vitest 与 6 个 E2E 回归。

### FE-03：流式与滚动优化

1. 在 controller 内实现首 token 立即显示、后续约 50ms 合并；测试 done/error/stop/network
   reject/异常 EOF 前的尾字 flush、no-token done.message fallback、连续 status/sources、
   stop A 后立即 start B、旧 timer/finally 失效、dispose pending 和零遗留 timer。
2. 让未变化 MessageItem 跳过 Markdown 解析，固定 callback/plugin 引用。
3. 明确移动端和桌面的聊天 scroll owner；接近底部才跟随，向上阅读时显示“回到最新”，
   不逐批启动 smooth 动画，并尊重 reduced motion。
4. 验证停止/完成后 reload 正文完整，流中不逐 token `localStorage.setItem`。
5. 用同一 FE-01 夹具前后至少各跑 3 轮，最终正文长度/SHA 必须一致；常规 token 批次通常
   `<=20/s`（首批和终端 flush 单列），前台新增可见等待 `<=100ms`，历史 Markdown 次数不随
   token 增长，并报告 commit、frame/Long Task 的中位数与范围。完整边界与阈值以主计划
   FE-03 为规范，本摘要不缩减其验收项。

### FE-04：设计变量、可读性、弹窗和提示

1. 在现有 CSS 体系补足有限的颜色、字号、间距、圆角、阴影和焦点变量。
2. 接入统一 Dialog 行为；确认弹窗默认安全焦点，嵌套删除确认不与外层 Escape 冲突。
3. 窄屏来源抽屉按模态交互处理，桌面来源面板保持非模态；统一 Notice 语义。
4. 检查 `1440x900`、`860x900`、`390x844`、`320px` 和 200% 缩放，完成截图与键盘验收。

### FE-05：引用、代码高亮和空状态

1. 用 react-markdown v10 兼容的 AST 方案只转换有效 `[文档N]`，排除 code、fenced code、
   link；用 messageId/rank/chunkId 绑定所属回答。
2. 点击引用后选择所属回答 sources，待目标挂载再滚动/高亮；覆盖跨回答同编号和 sources 晚到。
3. 引入单一高亮引擎并设置 `detect:false`；验证 Python、JS/TS、JSON、Bash 及 js/ts/sh
   aliases，无语言和未知/未注册语言必须保持纯文本；长代码自身滚动。
4. 增加克制的空状态建议，并在高亮后重跑关键性能样例。

### FE-06：整体验证与交付

1. 完整回归、视觉/键盘复核、构建体积与性能对照；确认无调试计数器或 console 噪声。
2. 按版本一致性测试逐项同步 3.1.0，不全仓替换历史 `3.0.0`，保持 Schema `1.0` 和
   `dense-v1`。
3. 运行计划规定的前端、Python、契约、格式、编译、Compose 和确定性评测门禁。
4. 形成待复审候选报告，区分本机 Mock、真实服务未验证范围和未关闭风险。

FE-06 体积对照只比较普通 `npm run build`，不用 profiling 产物。当前精确基线为 JS
`419,799 B raw / 129,049 B gzip(level 9)`、CSS `23,697 B / 5,179 B`。最终应在相同
Node/npm、mode/env 下记录所有 JS/CSS chunk 的原始字节、固定 gzip level 9 字节和 SHA-256；
功能实现与依赖同时进入时，差值必须标为“依赖 + 实现”，不能伪装成纯依赖体积。
同时核对 `npm ls rehype-highlight @radix-ui/react-dialog`、manifest/lock 的直接依赖范围与
精确解析版本；记录所有 JS chunks，防止 code splitting 隐藏增量。

## 9. 已知风险与待后续验证

- FE-01 没有证实优化收益；50ms 只是假设初值，必须由 FE-03 同夹具数据决定。
- `<=860px` 当前页面滚动结构可能使 window 和 message-list 同时争夺滚动所有权。
- 页面仍存活且终端/stop 回调已执行时，终端同步 flush 不依赖 timer 准时触发；页面冻结或
  终端前卸载遵循 dispose 的丢弃语义，后台性能不验收。
- 旧 localStorage 中若存在 `retrieving/generating` 消息，不得静默清库；FE-02 记录兼容行为，
  FE-06 交代最终处理。
- FE-05 高亮会改变 Markdown 成本，必须重跑性能样例，不能直接沿用 FE-03 数字。
- `parseSSEBlock` 当前仍以类型断言接受未知 event/data；除非后续测试复现实际故障，
  不在 FE-02 扩成完整运行时 Schema 重构。
- `ERR_NO_BUFFER_SPACE` 与回环代理是本机环境注记；不修改系统代理、不结束未知进程。

## 10. FE-01 交付证据

- 高频流式原始数据：`artifacts/frontend-3.1.0/fe01/streaming-baseline.json`
- 视觉报告：`artifacts/frontend-3.1.0/fe01/visual-agent/BASELINE_REPORT.md`
- 视觉结构化数据：`artifacts/frontend-3.1.0/fe01/visual-agent/baseline-probe.json`
- 测量设施：`frontend/src/fe01Metrics.ts`、`frontend/benchmarks/`、
  `frontend/vite.fe01.config.ts`、`frontend/playwright.fe01.config.ts`
- 私有阶段记录：`agent/过程记录/FE-01-前端3.1.0基线与实施设计.md`

## 11. 最终自检与阶段结论

最终同一工作树状态检查：

| 命令 | 结果 |
|---|---|
| `npm test` | 2 个文件、5 个测试通过 |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过；产物哈希恢复基线，FE-01 标记不存在 |
| `npm run build:fe01` | 通过；专用 profiling 产物生成 |
| `npm run test:fe01` | 1 个性能用例通过，内部完成 3 轮固定样例 |
| `npm run test:e2e` | 6/6 通过 |
| `git diff --check` | 通过；只有 Git 的 LF→CRLF 工作树提示，无内容错误 |

阶段结论：`PASS WITH NOTES`。

FE-01 要求的现状核对、可复跑性能夹具、视觉/键盘证据、模块接口、依赖选择、后续任务、
风险和私有经验沉淀均已完成。Notes：性能只代表本机隔离 Mock；CI 的 Node/Python 主版本
不同；320px 第二次重复运行受导航前 `ERR_NO_BUFFER_SPACE` 阻断，但完整主运行有效；本阶段
确认的滚动与键盘缺陷按计划留到 FE-03/FE-04 修复。这些注记不阻断 FE-01 设计闸门，
但不得写成优化已完成或所有环境已通过。

人工阶段闸门已于 2026-09-20 确认，后续工作从 FE-02 开始；该确认不包含 FE-03、
Git commit/push、发布或部署授权。

## 12. FE-01～FE-03 独立复审补充

R1 已修补：依赖 Chromium 的 MessageList 渲染测试仍保留在 Vitest，但 CI 和本地可复现命令已在 npm test 前显式安装 Playwright Chromium；测试启动失败时会通过 finally 清理浏览器和 Vite server。干净缓存先安装浏览器后，定向 1/1 与完整 npm test 38/38 通过。

R2 已修补：FE-01/FE-03 Playwright 配置显式声明性能报告输出路径；缺少配置时 benchmark 直接失败，不再默认写入 FE-01 基线。当前 FE-01 原始性能 JSON 已无法从工作树恢复，现有 baseline 文件不再被当作原始前测；原报告冻结汇总仍有效，但历史精确收益比例不能从当前 JSON 独立复算。修补复测写入 FE-03 独立证据 `artifacts/frontend-3.1.0/fe03/streaming-after-r2.json`。随后使用可信优化前 HEAD 3a9bf0c 的隔离 worktree，以测量-only overlay 重建新的 FE-01 baseline `artifacts/frontend-3.1.0/fe01/archives/streaming-baseline-rebuilt-20260921.json`，并与最终候选形成配对证据 `artifacts/frontend-3.1.0/fe01/archives/paired-measurement-rebuilt-20260921.json`；该配对明确标记为 rebuilt，不冒充原始 2026-09-20 JSON。

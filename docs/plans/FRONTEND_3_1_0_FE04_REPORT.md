# DocuMind 前端 3.1.0 FE-04 设计变量与基础交互

日期：2026-09-21

状态：FE-04 `PASS`，等待人工确认；未进入 FE-05。

适用计划：`docs/plans/FRONTEND_3_1_0_PLAN.md`

## 1. 范围与结论

FE-04 完成了有限设计变量、正文与辅助文字可读性、统一 Notice、统一 Modal、文档与会话确认、
窄屏来源模态抽屉、焦点管理和响应式布局验证。阶段内新增直接依赖
`@radix-ui/react-dialog@1.1.23`，没有修改后端、检索协议、引用语法或应用版本。

阶段结论为 `PASS`。最终单元测试、类型检查、生产构建、32 条全量浏览器回归、14 条 FE-04
无障碍交互、5 视口布局矩阵和真实浏览器 200% 缩放均通过。25 张布局图和 7 张真实缩放图已
保存到稳定 artifact 目录并完成人工复核。未执行 Git commit/push、版本同步、发布或部署。

## 2. 诊断与反馈环

FE-01 基线已确定以下缺陷：弹窗打开后焦点留在背景、Tab 可逃逸、关闭不恢复触发点；窄屏来源
表现为遮罩抽屉却没有模态行为；composer 无可见焦点环；有效信息仍有 9-10px 字号。

FE-04 以浏览器行为而不是组件存在性作为反馈环：

| 反馈环 | 修复前信号 | 验证目标 |
|---|---|---|
| 会话与文档确认 | 初始焦点、循环、Escape、遮罩和恢复不一致 | 安全初始焦点、焦点圈定、关闭后恢复或回退 |
| pending 删除 | 关闭入口和外层操作仍可能参与焦点顺序 | 唯一焦点为 busy 状态，Escape/遮罩无效，请求只发一次 |
| 来源断点 | 窄屏抽屉背景可操作，861→860 焦点可能丢失 | 桌面非模态、窄屏模态，动态切换安全关闭并恢复入口 |
| Notice 语义 | 状态提示样式和 live-region 规则分散 | error/assertive、普通状态/polite、历史状态/off |
| 字号与对比度 | 9-10px 有效信息、composer 无焦点环 | 可见有效信息至少 11px，普通文字 4.5:1，焦点指示 3:1 |
| 布局与缩放 | 长标题、表格、代码和嵌套弹窗缺少矩阵证据 | 5 视口 × 5 状态无越界/重叠，宽内容局部滚动 |

最终独立复审还暴露了四个证据缺口：真实 200% 截图被 Playwright 裁成半屏、旧 PASS 可能在
失败后残留、布局截图会被下一轮 Playwright 清空、对比度只扫描初始工作台。收尾中分别改为
CDP 物理裁剪并断言尺寸/字节、运行前失效旧 evidence、稳定 artifact 目录和弹窗/Notice 多状态
扫描。新增扫描首先复现了“程序化初始焦点没有可见焦点环”，修复后再转绿。

## 3. 实现结果

### 3.1 设计变量与可读性

- 在原语义色基础上补齐 sidebar、success/warning/danger、focus、surface 和 border 变量。
- 字号层级固定为 dense 11px、supporting 12px、body 14px；有效信息不再使用 9-10px。
- 间距限定为 4/8/12/16/24px，圆角为 4/6/8px，并统一 raised/modal 阴影。
- 正文保持 14px 和 1.72 行高；长文件名、会话标题和版本标识使用可控省略或换行。
- 全局键盘焦点使用 2px 白色内描边和 4px 语义焦点环；Modal 内程序化初始焦点同样可见。
- Markdown 表格和代码块保持自身横向滚动，不扩大 document/body 宽度。

### 3.2 统一 Modal

`frontend/src/components/Modal.tsx` 基于 Radix Dialog 封装三种变体：document、confirmation、
sheet。Radix 提供 portal、背景隔离和 focus scope，项目层补充：

- 显式初始焦点和 `aria-modal="true"`。
- Escape、遮罩和外部交互统一遵守 `dismissible`。
- 关闭后优先恢复真实触发点；触发点失效、删除或按业务要求跳过时使用明确 fallback。
- 恢复焦点使用 `preventScroll`，并以 lifecycle generation 避免 StrictMode 重放时的旧清理抢焦点。
- 嵌套删除确认只关闭自身；失败后外层详情保留，成功后两层关闭并回到文档列表。

破坏性确认默认聚焦“取消”。删除 pending 时焦点转移到带 `role="status"`、`aria-busy` 的状态区，
取消、确认和外层文档操作全部禁用，Tab/Shift+Tab 不逃逸，Escape/遮罩不能关闭。

### 3.3 统一 Notice

`frontend/src/components/Notice.tsx` 统一 success/error/warning/info 和 sidebar/banner/inline 外观。
error 默认 `role="alert"` 与 assertive；其他新状态默认 polite；`announce="off"` 保留视觉内容但
不创建 live region。历史索引错误因此不会在每次打开详情时作为新错误重播。

上传成功提示关闭后恢复上传入口，服务离线时回退“新建对话”；清空或删除会话导致原触发点
消失时也有同样的可聚焦回退。上传进度只播报阶段状态，不逐 token 或逐百分比播报。

### 3.4 来源区域语义

来源区域以 `(max-width: 860px)` 为单一断点：

- `>860px`：渲染可继续操作背景的非模态 `aside`，不声明 `aria-modal`。
- `<=860px`：渲染统一 Modal sheet，背景隔离、焦点进入关闭按钮并在关闭后恢复回答来源入口。
- 861→860 动态变化时先关闭原桌面区域并恢复可见切换按钮，不把非模态节点直接伪装成 dialog。

## 4. 行为验收

| 场景 | 最终行为 |
|---|---|
| 会话清空/删除 | 取消为初始焦点；循环焦点；Escape/遮罩关闭；触发点存在时恢复，否则回退新建对话 |
| 文档详情 | 关闭按钮为初始焦点；背景隔离；Escape/遮罩关闭并恢复文档入口 |
| 嵌套删除 | 取消为安全初始焦点；关闭内层不影响外层；焦点返回删除按钮 |
| 删除失败 | 绘制前关闭内层确认；外层显示 assertive 错误；可立即重新打开确认 |
| 删除 pending | busy 状态持有焦点；所有关闭/操作入口禁用；请求只发送一次 |
| 删除成功 | 两层弹窗关闭；触发文档消失后焦点落到可聚焦文档列表 |
| 上传提示 | live-region 语义一致；关闭后恢复上传按钮或离线 fallback |
| 历史索引错误 | 保持可见，但不作为新 alert/status 重复播报 |
| 来源区域 | 桌面非模态；窄屏 modal sheet；关闭和断点切换均恢复焦点 |

## 5. 视觉与真实缩放证据

### 5.1 布局矩阵

`frontend/e2e/fe04-layout.spec.ts` 覆盖 1440×900、860×900、390×844、320×844 和
720×450 五个 CSS 视口。每个视口检查 workspace、sources、document dialog、nested delete、
conversation confirm 五个状态，共 25 张图。

自动断言覆盖 document/body 横向溢出、关键控件越界、标题/操作重叠和表格/代码局部滚动。
最终 25 图位于 `artifacts/frontend-3.1.0/fe04/layout-matrix/`，文件数 25，单图
34,911-98,148 B；已抽查所有视口与状态类型，无裁切、遮挡、异常空白或操作入口丢失。

720×450 只代表 200% 场景下的 CSS 重排，不冒充真实浏览器缩放。

### 5.2 真实浏览器 200%

`frontend/benchmarks/fe04-real-zoom.mjs` 启动隔离 Chromium，在
`chrome://settings/appearance` 将页面缩放设置为 200%，再连接实际页面和 Mock API：

- Chromium 151.0.7922.34；设置值 2；`devicePixelRatio=2`。
- 外窗 1440×900；页面 CSS 视口 712×374；860px 紧凑断点真实生效。
- document 横向溢出 0；body 最大 1px 舍入差。
- 表格 `629/7286px`、代码 `629/8206px`，均在自身区域横向滚动。
- workspace、来源、文档详情、嵌套删除和会话确认五个几何状态均无控件越界。

动态网页缩放下 Playwright 默认截图只保留半个物理窗口。最终脚本直接使用
`Page.captureScreenshot`，将 CSS 裁剪矩形按 DPR 换算为物理像素，并对宽、高和最小像素数据量
做硬断言。运行前先删除旧 `evidence.json`，失败时不会保留过期 PASS。

最终 7 张图为 1409/1424×749，整页图为 1424×2426，均已人工复核；焦点图明确包含 composer
焦点环，来源与各弹窗图包含右侧关闭及操作入口。结构化结果和图片位于
`artifacts/frontend-3.1.0/fe04/real-zoom/`。

## 6. 最终验证

| 检查 | 最终结果 |
|---|---|
| `npm test` | 5 个文件、38/38 通过 |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过；CSS 24.90 kB / gzip 5.52 kB；JS 468.03 kB / gzip 146.24 kB |
| `npm run test:e2e` | 32/32 通过；6 条 FE-03、14 条 FE-04 accessibility、5 条布局、7 条原工作台 |
| FE-04 accessibility 定向 | 14/14 通过 |
| FE-04 layout 定向 | 5/5 通过，稳定生成 25 张截图 |
| pending 删除稳定性 | `--repeat-each=3`，3/3 通过 |
| 真实浏览器 200% | PASS；5 状态、7 图、尺寸和内容下限断言通过 |
| `npm ls --all` | 退出码 0；依赖树完整 |
| `npm audit --omit=dev` | 0 漏洞 |
| `npm audit` | 2 个 moderate，均为既有 Vitest/@vitest-mocker 开发链路 |
| `git diff --check` | 退出码 0；只有 Windows LF→CRLF 提示 |
| 新增/相关未跟踪文件尾随空白扫描 | 通过 |

Playwright 仅提示 `NO_COLOR` 被 `FORCE_COLOR` 忽略，不影响结果。回环地址测试进程继续显式设置
`NO_PROXY=127.0.0.1,localhost`，没有修改系统代理。

## 7. 依赖与产物影响

Radix Dialog 1.1.23 是直接生产依赖，peer 支持 React/ReactDOM 19；当前 React 19.2.8 全树去重。
锁文件包含 resolved 和 integrity。新增生产闭包共 25 个包，24 个 MIT、1 个 0BSD；没有 copyleft
或未知许可证。生产审计为 0 漏洞。

完整审计的 2 个 moderate 来自既有 Vitest 3.2.7 / `@vitest/mocker`，修复建议要求强制升级到
Vitest 5 主版本，不属于 Radix 生产链路，也不在 FE-04 擅自扩大升级范围。

按相同 gzip level 9 口径与 FE-03 normal artifact 比较：

| 产物 | FE-03 | FE-04 | 增量 |
|---|---:|---:|---:|
| JS raw | 426,039 B | 468,028 B | +41,989 B |
| JS gzip | 131,805 B | 146,012 B | +14,207 B |
| CSS raw | 24,143 B | 24,896 B | +753 B |
| CSS gzip | 5,278 B | 5,496 B | +218 B |
| 合计 | 450,182 B / 137,083 B gzip | 492,924 B / 151,508 B gzip | +42,742 B / +14,425 B gzip |

该增量是 Radix 及 FE-04 项目实现的总增量，不能全部归因于单一依赖。FE-06 仍会按完整候选快照
复核 bundle，不把当前阶段数字解释为最终发布体积。

## 8. 独立复审与剩余边界

- 依赖独立复审：`PASS`，无依赖级阻断。
- 实现复审未发现 Modal、Notice、pending、来源语义或焦点恢复的未关闭生产缺陷。
- 复审发现的截图裁切、旧 PASS、临时截图和多状态对比度缺口均已修复并重新验证。
- 本阶段只在本机 Chromium 与隔离 Mock 验证；没有使用真实模型、真实用户数据或真实屏幕阅读器。
- 已覆盖 861→860 切入紧凑模式及两个断点的直接加载；未单列 860→861 反向动态切换用例。
- 完整审计的 2 个 moderate 继续作为开发依赖 note，不阻断 FE-04。
- 当前工作树包含 FE-01～FE-04 未提交成果；版本仍为 3.0.0，统一同步属于 FE-06。

## 9. 阶段结论

FE-04 结论：`PASS`。设计变量、有效字号、普通文字与焦点对比度、Modal 行为、Notice 语义、
桌面/窄屏来源区域、长文本布局、局部横向滚动和真实 200% 缩放均已有可复现证据；没有未关闭
必验项。

当前停在 FE-04 人工闸门。获得明确确认前，不进入 FE-05，不执行 Git commit/push、版本同步、
发布或部署。

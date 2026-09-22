# DocuMind 前端 3.1.0 FE-05 引用、代码高亮和空状态

日期：2026-09-21

状态：FE-05 PASS；已按用户连续授权进入 FE-06。

## 1. 范围与结论

FE-05 完成正文 [文档N] 的 Markdown AST 引用转换、回答级来源绑定、来源目标滚动与高亮、单一代码高亮管线，以及有文档无对话时的克制提问建议。无效引用、代码块、行内代码和已有链接中的引用保持普通文本或原链接安全行为。

阶段结论为 PASS。初始 FE-05 浏览器用例 3/3 通过；R3-R7 补充边界与窄屏焦点用例合计 9/9；正式补充矩阵 11/11；G2 滚动保持与高亮清理矩阵 6/6；最终全量 Playwright 58/58 通过；流式性能夹具在修复高亮初始化和终态调度后 1/1 通过。

## 2. 实现结果

- frontend/src/features/chat/markdown.ts：递归处理 mdast text 节点，只把当前回答 sources 中唯一有效 rank 转成内部 citation link；跳过 link、inlineCode 和 fenced code。重复 rank、越界 rank、[文档0]、[文档01] 等保持普通文本。
- MessageList：正文引用渲染为键盘可达 button chip，点击携带 answerId 和 rank；回答末尾的全部来源按钮继续保留。
- App、SourcesPanel、SourceItem：来源选择仍绑定 conversationId + answerId，新增 rank 高亮；来源面板挂载后使用 requestAnimationFrame 定位目标卡片并滚动到 nearest，桌面和窄屏两种 FE-04 语义均保留。
- rehype-highlight 7.0.2：配置 detect=false，支持 Python、JavaScript、TypeScript、JSON、Bash 及 js/ts aliases；未知语言、无语言代码和未注册语言不生成 token span，保持纯文本。
- 高亮 transformer 为模块级单例；流式阶段和进入 done/error 的首帧不运行高亮，下一帧再补上最终语法样式，避免高亮成本进入 token/终态可见延迟。
- 空状态：知识库有文档但当前没有对话时显示 3 个提问建议，只填充 composer 并聚焦，不自动发送请求。

## 3. 诊断与修复

首次 FE-05 性能复跑发现单 token 最大可见延迟 113.6ms；进一步定位为每条 ReactMarkdown 实例反复创建 lowlight，以及流式终态同步高亮。修复为模块级 transformer、稳定态首帧延后一帧；最终 FE-03 固定夹具 1/1 通过，正文完整性、批次和历史 Markdown 隔离保持不变。

首次增量浏览器测试还暴露两个测试/布局问题：无效引用属于段落文本而非独立 DOM 节点，断言改为段落包含文本；窄屏提问按钮在 flex shrink 下发生文字竖排，改为明确宽度和单列布局。

## 4. 验证结果

| 检查 | 结果 |
|---|---|
| npm test | 38/38 |
| npm run typecheck | 通过 |
| FE-05 定向 Playwright | 3/3 |
| FE-04 + FE-05 定向 Playwright | 22/22 |
| G2 滚动保持与高亮清理矩阵 | 6/6 |
| 全量 Playwright | 58/58 |
| FE-03 固定性能夹具 | 1/1；高亮加入后修复并通过 100ms 门禁 |

## 5. 证据边界

- 引用定位使用隔离 Mock、合成会话和回答 sources；未使用真实用户数据。
- 代码高亮验证覆盖常用语言、aliases、未知/无语言退化和长代码既有局部滚动；不代表所有 highlight.js 语言均有主题设计。
- 高亮导致普通生产 bundle 明显增加，FE-06 报告记录完整 raw/gzip/SHA，不把增量伪装为纯依赖成本。
- FE-05 未改变后端引用协议、Schema 1.0、dense-v1、localStorage key 或 3.0.0 会话兼容结构。

## 6. 阶段结论

FE-05 PASS。用户已明确授权连续进入 FE-06；当前继续执行 FE-06 整体验证、版本收尾和候选交付。

## 7. FE-04～FE-06 独立复审补充修补

后续独立复审发现并修复 R3～R7：

- R3：引用编号先校验规范正整数形式，拒绝前导零、0、超大/非安全整数和不存在 rank。
- R4：mdast link、linkReference、inlineCode、code 均作为不可进入边界；reference-style link 内不再插入 citation chip。
- R5：citation AST 节点加入受控标记，renderer 不再仅凭 href 前缀接管普通 Markdown 锚点。
- R6：来源定位加入独立 requestId；重复点击同一引用会重新执行滚动和高亮。
- R7：切换回答/会话、新建、清空、删除或开始新回答时清除旧 rank 高亮，选择身份与当前回答上下文一致。

新增 reviewer-fe05-boundaries.spec.ts 覆盖规范编号、reference link、普通锚点、重复定位、跨会话高亮、窄屏 chip 焦点恢复，共 6/6；正式补充矩阵另有 11/11；现有 FE-05 用例补充常用语言 token span 断言。边界与 FE-05 合计用例 9/9 通过。

## 8. G2 最终回归补充

新增正式默认回归 `frontend/e2e/fe05-g2-regression.spec.ts`，共 6/6：桌面与窄屏分别覆盖首次、重复和跨回答引用定位时聊天阅读位置保持；另覆盖新建、清空、删除当前对话和开始新回答四个高亮清理入口，并在每条清理路径后确认新来源仍可主动选中。隔离 Mock 仅新增 `g2-citation` 回答分支以产生新的引用 chip，没有修改产品业务实现。补充后默认全量 Playwright 为 58/58。

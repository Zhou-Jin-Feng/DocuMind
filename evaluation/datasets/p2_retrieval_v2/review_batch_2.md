# DS-04 Human Review Batch 2

Cases: 50. Every case remains `assisted_unverified` until a human decision is recorded.

For each case, review the question, answerability, ambiguity and every proposed qrel. Record approve, modify or delete in `review_decisions.jsonl`; a batch-level approval is valid only after every case below has been inspected.

## 1. REP-T01-01

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 控制项 DM-UPLOAD-LIMIT-ACT 的当前冻结值和规则是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `22efd7ddb70c84148b8dd731981bfe6bd5610e404f934f837b3fb2722cab663a` / grade `3` / control `DM-UPLOAD-LIMIT-ACT` / quote: 单个上传文件的当前硬上限为 50 MiB；超限请求必须在解析前拒绝并返回稳定的客户端错误。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 2. REP-T01-02

- Proposed split: `validation`
- Category: `semantic`
- Question: 用户提交体积较大的知识文件时，系统应按什么边界接收或拒绝，现行规范要求怎样处理？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `0ea51be75ca124a56be8804d05da7ec8cc2afea0d736e760a44b645260d51a75` / grade `3` / control `DM-UPLOAD-LIMIT-ACT-PROC` / quote: 先读取声明长度并执行流式计数；达到 50 MiB 后立即停止接收，不创建 Registry 记录，也不保留部分文件。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 3. REP-T01-03

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: DM-UPLOAD-LIMIT-DRF 与 DM-UPLOAD-LIMIT-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `22efd7ddb70c84148b8dd731981bfe6bd5610e404f934f837b3fb2722cab663a` / grade `3` / control `DM-UPLOAD-LIMIT-ACT` / quote: 单个上传文件的当前硬上限为 50 MiB；超限请求必须在解析前拒绝并返回稳定的客户端错误。
  - source `t01-ingestion-draft.txt` / document `p2rep:document:be0f7276192eb18265409e8435b80790662857781ca75402532e09b815985ed6` / chunk `b534d7dda82ba02f3bbd7abfa51096b383115fca85fc8c96c2029f7de81ebc2d` / grade `1` / control `DM-UPLOAD-LIMIT-DRF` / quote: 草案建议将单文件上限提高到 80 MiB，但该值尚未完成内存峰值评审，不能用于线上接收。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 4. REP-T01-04

- Proposed split: `validation`
- Category: `non_plain_text`
- Question: 在 table_extract 摘录中，DM-UPLOAD-LIMIT-ACT 对应的配置值是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `0ea51be75ca124a56be8804d05da7ec8cc2afea0d736e760a44b645260d51a75` / grade `3` / control `DM-UPLOAD-LIMIT-ACT-DATA` / quote: 50 MiB
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 5. REP-T01-05

- Proposed split: `validation`
- Category: `authority_version`
- Question: “上传文件大小上限”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `22efd7ddb70c84148b8dd731981bfe6bd5610e404f934f837b3fb2722cab663a` / grade `3` / control `DM-UPLOAD-LIMIT-ACT` / quote: 单个上传文件的当前硬上限为 50 MiB；超限请求必须在解析前拒绝并返回稳定的客户端错误。
  - source `t01-ingestion-draft.txt` / document `p2rep:document:be0f7276192eb18265409e8435b80790662857781ca75402532e09b815985ed6` / chunk `b534d7dda82ba02f3bbd7abfa51096b383115fca85fc8c96c2029f7de81ebc2d` / grade `1` / control `DM-UPLOAD-LIMIT-DRF` / quote: 草案建议将单文件上限提高到 80 MiB，但该值尚未完成内存峰值评审，不能用于线上接收。
  - source `t01-ingestion-superseded.txt` / document `p2rep:document:264447078243583cee5a4bf5494cde4fb1df1795c464b4819d8bde76a8a26006` / chunk `bfc8f406d3f91217fcc6082b32f21eb1e3a242cea32d8f5b1d5e4907112cacf4` / grade `1` / control `DM-UPLOAD-LIMIT-OLD` / quote: 旧版本把单个上传文件限制为 20 MiB，该限制已被当前 50 MiB 控制项取代。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 6. REP-T01-06

- Proposed split: `validation`
- Category: `general_operations`
- Question: 执行“上传文件大小上限”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `0ea51be75ca124a56be8804d05da7ec8cc2afea0d736e760a44b645260d51a75` / grade `3` / control `DM-UPLOAD-LIMIT-ACT-PROC` / quote: 先读取声明长度并执行流式计数；达到 50 MiB 后立即停止接收，不创建 Registry 记录，也不保留部分文件。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 7. REP-T01-07

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 未生效控制项 DM-UPLOAD-LIMIT-DRF 提议的值是什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-draft.txt` / document `p2rep:document:be0f7276192eb18265409e8435b80790662857781ca75402532e09b815985ed6` / chunk `b534d7dda82ba02f3bbd7abfa51096b383115fca85fc8c96c2029f7de81ebc2d` / grade `3` / control `DM-UPLOAD-LIMIT-DRF` / quote: 草案建议将单文件上限提高到 80 MiB，但该值尚未完成内存峰值评审，不能用于线上接收。
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `22efd7ddb70c84148b8dd731981bfe6bd5610e404f934f837b3fb2722cab663a` / grade `1` / control `DM-UPLOAD-LIMIT-ACT` / quote: 单个上传文件的当前硬上限为 50 MiB；超限请求必须在解析前拒绝并返回稳定的客户端错误。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 8. REP-T01-08

- Proposed split: `validation`
- Category: `semantic`
- Question: 如果只讨论“上传文件大小上限”的下一版建议，草案准备怎样执行？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-draft.txt` / document `p2rep:document:be0f7276192eb18265409e8435b80790662857781ca75402532e09b815985ed6` / chunk `64e14ce08f21b1f6d326049440ac9fe1f3f549ab115a2c1212a9ed98a1572308` / grade `3` / control `DM-UPLOAD-LIMIT-DRF-PROC` / quote: 仅在隔离压测环境记录 80 MiB 样本的解析峰值和失败率；评审前不得修改生产配置。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 9. REP-T01-09

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: 历史控制项 DM-UPLOAD-LIMIT-OLD 与当前行为有什么区别，故障处理中能否继续使用旧值？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `22efd7ddb70c84148b8dd731981bfe6bd5610e404f934f837b3fb2722cab663a` / grade `3` / control `DM-UPLOAD-LIMIT-ACT` / quote: 单个上传文件的当前硬上限为 50 MiB；超限请求必须在解析前拒绝并返回稳定的客户端错误。
  - source `t01-ingestion-superseded.txt` / document `p2rep:document:264447078243583cee5a4bf5494cde4fb1df1795c464b4819d8bde76a8a26006` / chunk `bfc8f406d3f91217fcc6082b32f21eb1e3a242cea32d8f5b1d5e4907112cacf4` / grade `2` / control `DM-UPLOAD-LIMIT-OLD` / quote: 旧版本把单个上传文件限制为 20 MiB，该限制已被当前 50 MiB 控制项取代。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 10. REP-T01-10

- Proposed split: `validation`
- Category: `non_plain_text`
- Question: 从草案的 table_extract 摘录读取，DM-UPLOAD-LIMIT-DRF 配置了什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-draft.txt` / document `p2rep:document:be0f7276192eb18265409e8435b80790662857781ca75402532e09b815985ed6` / chunk `64e14ce08f21b1f6d326049440ac9fe1f3f549ab115a2c1212a9ed98a1572308` / grade `3` / control `DM-UPLOAD-LIMIT-DRF-DATA` / quote: 80 MiB
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 11. REP-T01-11

- Proposed split: `validation`
- Category: `authority_version`
- Question: DM-UPLOAD-LIMIT-OLD 记录的是哪个历史版本，当前为什么不能把它当作权威规则？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-superseded.txt` / document `p2rep:document:264447078243583cee5a4bf5494cde4fb1df1795c464b4819d8bde76a8a26006` / chunk `bfc8f406d3f91217fcc6082b32f21eb1e3a242cea32d8f5b1d5e4907112cacf4` / grade `3` / control `DM-UPLOAD-LIMIT-OLD` / quote: 旧版本把单个上传文件限制为 20 MiB，该限制已被当前 50 MiB 控制项取代。
  - source `t01-ingestion-active.txt` / document `p2rep:document:c895c4af52ea8786f9f140fe326d25466d2dded5dbc5d1c2d35e1f8f6f245117` / chunk `22efd7ddb70c84148b8dd731981bfe6bd5610e404f934f837b3fb2722cab663a` / grade `2` / control `DM-UPLOAD-LIMIT-ACT` / quote: 单个上传文件的当前硬上限为 50 MiB；超限请求必须在解析前拒绝并返回稳定的客户端错误。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 12. REP-T01-12

- Proposed split: `validation`
- Category: `general_operations`
- Question: 在复盘旧系统时，“上传文件大小上限”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t01-ingestion-superseded.txt` / document `p2rep:document:264447078243583cee5a4bf5494cde4fb1df1795c464b4819d8bde76a8a26006` / chunk `8f0b3bc026209fff8cc47ba55379123cfa7a7f0b45546daecedfb698201edc31` / grade `3` / control `DM-UPLOAD-LIMIT-OLD-PROC` / quote: 历史服务在读取到 20 MiB 时终止上传；该步骤只用于解释旧日志，不得用于当前容量判断。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 13. REP-T01-13

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 未收录控制项 DM-UPLOAD-LIMIT-UNKNOWN 的生产值是多少？
- Answerable: `false`
- Ambiguity: `unanswerable_absent`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 14. REP-T01-14

- Proposed split: `validation`
- Category: `semantic`
- Question: 明年尚未发布的“上传文件大小上限”最终政策会如何调整？
- Answerable: `false`
- Ambiguity: `unanswerable_future`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 15. REP-T01-15

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: 在三份文件都没有记录外部托管平台的情况下，该平台对“上传文件大小上限”的强制值是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_external`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 16. REP-T01-16

- Proposed split: `validation`
- Category: `general_operations`
- Question: 负责“上传文件大小上限”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 17. REP-T02-01

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 控制项 DM-FILE-TYPES-ACT 的当前冻结值和规则是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `4c913b808713fe87f91f034e37e527db31960ce47ee06fa7b156e73457092ac4` / grade `3` / control `DM-FILE-TYPES-ACT` / quote: 当前只接受 PDF、DOCX 和 UTF-8 TXT，扩展名与内容签名不一致时必须拒绝。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 18. REP-T02-02

- Proposed split: `validation`
- Category: `semantic`
- Question: 知识库导入时哪些扩展名属于当前受支持的输入，现行规范要求怎样处理？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `ae20411b77c7fe54ef34479fe11cc8502fd5cef96d0d50e02e2c5e5712dc6a59` / grade `3` / control `DM-FILE-TYPES-ACT-PROC` / quote: 依次校验扩展名、MIME 提示和文件头；三者通过后再交给对应加载器，其他类型返回不支持错误。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 19. REP-T02-03

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: DM-FILE-TYPES-DRF 与 DM-FILE-TYPES-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `4c913b808713fe87f91f034e37e527db31960ce47ee06fa7b156e73457092ac4` / grade `3` / control `DM-FILE-TYPES-ACT` / quote: 当前只接受 PDF、DOCX 和 UTF-8 TXT，扩展名与内容签名不一致时必须拒绝。
  - source `t02-ingestion-draft.txt` / document `p2rep:document:30934b7434427a4b8c4ed33b333b834eb4b0310f566349d0f92a5f4f4eb89c62` / chunk `820da1df20a9b93353877dab5809ae881980fb47abc35b169bf27df5491508d2` / grade `1` / control `DM-FILE-TYPES-DRF` / quote: 草案计划增加 Markdown 输入，但围栏代码与链接清洗规则尚未冻结。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 20. REP-T02-04

- Proposed split: `validation`
- Category: `non_plain_text`
- Question: 在 yaml_config 摘录中，DM-FILE-TYPES-ACT 对应的配置值是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `ae20411b77c7fe54ef34479fe11cc8502fd5cef96d0d50e02e2c5e5712dc6a59` / grade `3` / control `DM-FILE-TYPES-ACT-DATA` / quote: PDF,DOCX,TXT
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 21. REP-T02-05

- Proposed split: `validation`
- Category: `authority_version`
- Question: “可接收文档类型”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `4c913b808713fe87f91f034e37e527db31960ce47ee06fa7b156e73457092ac4` / grade `3` / control `DM-FILE-TYPES-ACT` / quote: 当前只接受 PDF、DOCX 和 UTF-8 TXT，扩展名与内容签名不一致时必须拒绝。
  - source `t02-ingestion-draft.txt` / document `p2rep:document:30934b7434427a4b8c4ed33b333b834eb4b0310f566349d0f92a5f4f4eb89c62` / chunk `820da1df20a9b93353877dab5809ae881980fb47abc35b169bf27df5491508d2` / grade `1` / control `DM-FILE-TYPES-DRF` / quote: 草案计划增加 Markdown 输入，但围栏代码与链接清洗规则尚未冻结。
  - source `t02-ingestion-superseded.txt` / document `p2rep:document:7c46c51d6d739a294e2a146e1d52c8aa1331b121b3c6362b899eb60845acba57` / chunk `9cb679f62182a4aede06c80d5dd459ac5415fdb479d92fababbfeea03d31367f` / grade `1` / control `DM-FILE-TYPES-OLD` / quote: 历史版本只支持 PDF 和 TXT，DOCX 当时会被拒绝；该列表已经废止。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 22. REP-T02-06

- Proposed split: `validation`
- Category: `general_operations`
- Question: 执行“可接收文档类型”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `ae20411b77c7fe54ef34479fe11cc8502fd5cef96d0d50e02e2c5e5712dc6a59` / grade `3` / control `DM-FILE-TYPES-ACT-PROC` / quote: 依次校验扩展名、MIME 提示和文件头；三者通过后再交给对应加载器，其他类型返回不支持错误。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 23. REP-T02-07

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 未生效控制项 DM-FILE-TYPES-DRF 提议的值是什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-draft.txt` / document `p2rep:document:30934b7434427a4b8c4ed33b333b834eb4b0310f566349d0f92a5f4f4eb89c62` / chunk `820da1df20a9b93353877dab5809ae881980fb47abc35b169bf27df5491508d2` / grade `3` / control `DM-FILE-TYPES-DRF` / quote: 草案计划增加 Markdown 输入，但围栏代码与链接清洗规则尚未冻结。
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `4c913b808713fe87f91f034e37e527db31960ce47ee06fa7b156e73457092ac4` / grade `1` / control `DM-FILE-TYPES-ACT` / quote: 当前只接受 PDF、DOCX 和 UTF-8 TXT，扩展名与内容签名不一致时必须拒绝。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 24. REP-T02-08

- Proposed split: `validation`
- Category: `semantic`
- Question: 如果只讨论“可接收文档类型”的下一版建议，草案准备怎样执行？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-draft.txt` / document `p2rep:document:30934b7434427a4b8c4ed33b333b834eb4b0310f566349d0f92a5f4f4eb89c62` / chunk `d56c7b04d65a93f692cd79ab08ace0abe7948f53f93a5c54cc707de9014d187e` / grade `3` / control `DM-FILE-TYPES-DRF-PROC` / quote: 使用合成 Markdown 文件离线验证标题、表格和代码块抽取；不得在公开上传入口声明支持。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 25. REP-T02-09

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: 历史控制项 DM-FILE-TYPES-OLD 与当前行为有什么区别，故障处理中能否继续使用旧值？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `4c913b808713fe87f91f034e37e527db31960ce47ee06fa7b156e73457092ac4` / grade `3` / control `DM-FILE-TYPES-ACT` / quote: 当前只接受 PDF、DOCX 和 UTF-8 TXT，扩展名与内容签名不一致时必须拒绝。
  - source `t02-ingestion-superseded.txt` / document `p2rep:document:7c46c51d6d739a294e2a146e1d52c8aa1331b121b3c6362b899eb60845acba57` / chunk `9cb679f62182a4aede06c80d5dd459ac5415fdb479d92fababbfeea03d31367f` / grade `2` / control `DM-FILE-TYPES-OLD` / quote: 历史版本只支持 PDF 和 TXT，DOCX 当时会被拒绝；该列表已经废止。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 26. REP-T02-10

- Proposed split: `validation`
- Category: `non_plain_text`
- Question: 从草案的 yaml_config 摘录读取，DM-FILE-TYPES-DRF 配置了什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-draft.txt` / document `p2rep:document:30934b7434427a4b8c4ed33b333b834eb4b0310f566349d0f92a5f4f4eb89c62` / chunk `d56c7b04d65a93f692cd79ab08ace0abe7948f53f93a5c54cc707de9014d187e` / grade `3` / control `DM-FILE-TYPES-DRF-DATA` / quote: PDF,DOCX,TXT,MD
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 27. REP-T02-11

- Proposed split: `validation`
- Category: `authority_version`
- Question: DM-FILE-TYPES-OLD 记录的是哪个历史版本，当前为什么不能把它当作权威规则？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-superseded.txt` / document `p2rep:document:7c46c51d6d739a294e2a146e1d52c8aa1331b121b3c6362b899eb60845acba57` / chunk `9cb679f62182a4aede06c80d5dd459ac5415fdb479d92fababbfeea03d31367f` / grade `3` / control `DM-FILE-TYPES-OLD` / quote: 历史版本只支持 PDF 和 TXT，DOCX 当时会被拒绝；该列表已经废止。
  - source `t02-ingestion-active.txt` / document `p2rep:document:d91e266d97d8d542ab26536bb020699a75a26f49f1779b917419d414fb053196` / chunk `4c913b808713fe87f91f034e37e527db31960ce47ee06fa7b156e73457092ac4` / grade `2` / control `DM-FILE-TYPES-ACT` / quote: 当前只接受 PDF、DOCX 和 UTF-8 TXT，扩展名与内容签名不一致时必须拒绝。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 28. REP-T02-12

- Proposed split: `validation`
- Category: `general_operations`
- Question: 在复盘旧系统时，“可接收文档类型”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t02-ingestion-superseded.txt` / document `p2rep:document:7c46c51d6d739a294e2a146e1d52c8aa1331b121b3c6362b899eb60845acba57` / chunk `29131a3245ee360ee17e7f0d2a6fa1b8639176a0f4e977f606e23b3358b53948` / grade `3` / control `DM-FILE-TYPES-OLD-PROC` / quote: 旧加载器按两个扩展名分派；仅在复现历史导入失败时使用该信息。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 29. REP-T02-13

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 未收录控制项 DM-FILE-TYPES-UNKNOWN 的生产值是多少？
- Answerable: `false`
- Ambiguity: `unanswerable_absent`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 30. REP-T02-14

- Proposed split: `validation`
- Category: `semantic`
- Question: 明年尚未发布的“可接收文档类型”最终政策会如何调整？
- Answerable: `false`
- Ambiguity: `unanswerable_future`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 31. REP-T02-15

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: 在三份文件都没有记录外部托管平台的情况下，该平台对“可接收文档类型”的强制值是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_external`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 32. REP-T02-16

- Proposed split: `validation`
- Category: `general_operations`
- Question: 负责“可接收文档类型”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 33. REP-T03-01

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 控制项 DM-OCR-TRIGGER-ACT 的当前冻结值和规则是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-active.txt` / document `p2rep:document:be886186eac420450fe1ce7a19ba1c4193e8b8e4b7bde437bfaa2dd79ad2e7d0` / chunk `20311967c21442c1047274d62b3da0be323908b0988b595fcad1fef303fce1aa` / grade `3` / control `DM-OCR-TRIGGER-ACT` / quote: 页面直接提取结果少于 24 个可见字符时标记为 OCR 候选，但当前服务不会自动调用外部 OCR。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 34. REP-T03-03

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: DM-OCR-TRIGGER-DRF 与 DM-OCR-TRIGGER-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-active.txt` / document `p2rep:document:be886186eac420450fe1ce7a19ba1c4193e8b8e4b7bde437bfaa2dd79ad2e7d0` / chunk `20311967c21442c1047274d62b3da0be323908b0988b595fcad1fef303fce1aa` / grade `3` / control `DM-OCR-TRIGGER-ACT` / quote: 页面直接提取结果少于 24 个可见字符时标记为 OCR 候选，但当前服务不会自动调用外部 OCR。
  - source `t03-parsing-draft.txt` / document `p2rep:document:b42f63113e2734b3cfd32725d73b58979a67ed1ab0ea4d8d18e0c24f37633713` / chunk `acb1816a126fd4c5038eb5a31e0601cf7479ac248497a6655ad9f2689d6d02ee` / grade `1` / control `DM-OCR-TRIGGER-DRF` / quote: 草案把 OCR 候选阈值提高到 40 个字符，同时计划增加图像覆盖率判断。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 35. REP-T03-04

- Proposed split: `validation`
- Category: `non_plain_text`
- Question: 在 json_log 摘录中，DM-OCR-TRIGGER-ACT 对应的配置值是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-active.txt` / document `p2rep:document:be886186eac420450fe1ce7a19ba1c4193e8b8e4b7bde437bfaa2dd79ad2e7d0` / chunk `2a73642bcd787d479acec78a7fa333365d50fb3f3dfe8aa28c34dae512d3f93f` / grade `3` / control `DM-OCR-TRIGGER-ACT-DATA` / quote: 少于 24 个可见字符
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 36. REP-T03-05

- Proposed split: `validation`
- Category: `authority_version`
- Question: “扫描页 OCR 触发条件”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-active.txt` / document `p2rep:document:be886186eac420450fe1ce7a19ba1c4193e8b8e4b7bde437bfaa2dd79ad2e7d0` / chunk `20311967c21442c1047274d62b3da0be323908b0988b595fcad1fef303fce1aa` / grade `3` / control `DM-OCR-TRIGGER-ACT` / quote: 页面直接提取结果少于 24 个可见字符时标记为 OCR 候选，但当前服务不会自动调用外部 OCR。
  - source `t03-parsing-draft.txt` / document `p2rep:document:b42f63113e2734b3cfd32725d73b58979a67ed1ab0ea4d8d18e0c24f37633713` / chunk `acb1816a126fd4c5038eb5a31e0601cf7479ac248497a6655ad9f2689d6d02ee` / grade `1` / control `DM-OCR-TRIGGER-DRF` / quote: 草案把 OCR 候选阈值提高到 40 个字符，同时计划增加图像覆盖率判断。
  - source `t03-parsing-superseded.txt` / document `p2rep:document:51700777607d1d71aacf85fb1c236480eb5833e56c5485199a49e7ff9f24e1cd` / chunk `ed8a2886fc05cdaa4dec00803b4cefe522b9f6c58d1bb8c9a3f658def3abef71` / grade `1` / control `DM-OCR-TRIGGER-OLD` / quote: 旧解析策略只在少于 10 个字符时标记扫描页，漏掉了部分图片型页面。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 37. REP-T03-06

- Proposed split: `validation`
- Category: `general_operations`
- Question: 执行“扫描页 OCR 触发条件”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-active.txt` / document `p2rep:document:be886186eac420450fe1ce7a19ba1c4193e8b8e4b7bde437bfaa2dd79ad2e7d0` / chunk `2a73642bcd787d479acec78a7fa333365d50fb3f3dfe8aa28c34dae512d3f93f` / grade `3` / control `DM-OCR-TRIGGER-ACT-PROC` / quote: 统计去除空白后的字符数；低于阈值则保留页码和候选标记，并向调用方返回可追踪的解析告警。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 38. REP-T03-09

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: 历史控制项 DM-OCR-TRIGGER-OLD 与当前行为有什么区别，故障处理中能否继续使用旧值？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-active.txt` / document `p2rep:document:be886186eac420450fe1ce7a19ba1c4193e8b8e4b7bde437bfaa2dd79ad2e7d0` / chunk `20311967c21442c1047274d62b3da0be323908b0988b595fcad1fef303fce1aa` / grade `3` / control `DM-OCR-TRIGGER-ACT` / quote: 页面直接提取结果少于 24 个可见字符时标记为 OCR 候选，但当前服务不会自动调用外部 OCR。
  - source `t03-parsing-superseded.txt` / document `p2rep:document:51700777607d1d71aacf85fb1c236480eb5833e56c5485199a49e7ff9f24e1cd` / chunk `ed8a2886fc05cdaa4dec00803b4cefe522b9f6c58d1bb8c9a3f658def3abef71` / grade `2` / control `DM-OCR-TRIGGER-OLD` / quote: 旧解析策略只在少于 10 个字符时标记扫描页，漏掉了部分图片型页面。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 39. REP-T03-12

- Proposed split: `validation`
- Category: `general_operations`
- Question: 在复盘旧系统时，“扫描页 OCR 触发条件”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t03-parsing-superseded.txt` / document `p2rep:document:51700777607d1d71aacf85fb1c236480eb5833e56c5485199a49e7ff9f24e1cd` / chunk `c19fc44caf1c23f824f12ee1fac28bfc41910e5ec9b5c6ac81b249e7516bd5fa` / grade `3` / control `DM-OCR-TRIGGER-OLD-PROC` / quote: 历史流程只执行字符计数并记录 debug 日志；该低阈值不再适用。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 40. REP-T03-13

- Proposed split: `validation`
- Category: `exact_lexical`
- Question: 未收录控制项 DM-OCR-TRIGGER-UNKNOWN 的生产值是多少？
- Answerable: `false`
- Ambiguity: `unanswerable_absent`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 41. REP-T03-14

- Proposed split: `validation`
- Category: `semantic`
- Question: 明年尚未发布的“扫描页 OCR 触发条件”最终政策会如何调整？
- Answerable: `false`
- Ambiguity: `unanswerable_future`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 42. REP-T03-15

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: 在三份文件都没有记录外部托管平台的情况下，该平台对“扫描页 OCR 触发条件”的强制值是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_external`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 43. REP-T03-16

- Proposed split: `validation`
- Category: `general_operations`
- Question: 负责“扫描页 OCR 触发条件”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 44. REP-T04-03

- Proposed split: `validation`
- Category: `difficult_negative`
- Question: DM-CHUNK-SIZE-DRF 与 DM-CHUNK-SIZE-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t04-chunking-active.txt` / document `p2rep:document:7b0d422adef1caf07a47acc26e5dff04a8b03bc91c1361228f2b0333e489272b` / chunk `7613e4a5cb4a4e0b8999f6dfd34bf6694efb3b19ce87459e55ced75066a1126a` / grade `3` / control `DM-CHUNK-SIZE-ACT` / quote: 生产递归分块的 chunk_size 固定为 500 个字符，评测材料必须使用同一参数。
  - source `t04-chunking-draft.txt` / document `p2rep:document:399fd36c79cac7d0577c9e56101841f0d2436050d1cc1d223ecb48532c95907f` / chunk `db6dce94032a2bb152e3415676f453b5821d77e1b7acc0da43025951f6a666d7` / grade `1` / control `DM-CHUNK-SIZE-DRF` / quote: 草案建议把窗口放大到 700 个字符以保留更多上下文，但尚无质量和延迟证据。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 45. REP-T04-06

- Proposed split: `validation`
- Category: `general_operations`
- Question: 执行“生产分块大小”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t04-chunking-active.txt` / document `p2rep:document:7b0d422adef1caf07a47acc26e5dff04a8b03bc91c1361228f2b0333e489272b` / chunk `9cba995e724d83c166a343490de1aa039838fdcfae0f704e44a0457cc8d9f965` / grade `3` / control `DM-CHUNK-SIZE-ACT-PROC` / quote: 按段落、换行、句末和字符顺序递归切分；写入前记录稳定 chunk_index 与内容哈希。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 46. REP-T04-12

- Proposed split: `validation`
- Category: `general_operations`
- Question: 在复盘旧系统时，“生产分块大小”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t04-chunking-superseded.txt` / document `p2rep:document:4dc2e247bc87284611d473cf247be4d721ca37843423939943efc9076d73608b` / chunk `e7d3bb754147d77f5ed7c8bed7f19b301524f62463641c13c870564212b73d7a` / grade `3` / control `DM-CHUNK-SIZE-OLD-PROC` / quote: 旧流程按 1000 字符递归切分；仅可用于复现历史索引指纹。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 47. REP-T04-16

- Proposed split: `validation`
- Category: `general_operations`
- Question: 负责“生产分块大小”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 48. REP-T05-06

- Proposed split: `validation`
- Category: `general_operations`
- Question: 执行“相邻分块重叠量”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t05-chunking-active.txt` / document `p2rep:document:a0c49985a779168b3ee4f65c5c179ddbc4f8fac8051bd4fb207c59e6019154d0` / chunk `a4048fce297be10b0647c29cb38e62cb841e1ac459a5f989d5b6accd52eea08a` / grade `3` / control `DM-CHUNK-OVERLAP-ACT-PROC` / quote: 创建分块器前校验 0 <= overlap < size；索引元数据记录实际参数供重建核对。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 49. REP-T05-12

- Proposed split: `validation`
- Category: `general_operations`
- Question: 在复盘旧系统时，“相邻分块重叠量”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t05-chunking-superseded.txt` / document `p2rep:document:eb2f67927e337ad9ecc0a0817ba2a201789e697799c8f6002563b55c553676aa` / chunk `5dd9968aa1f311faab6934ca1565c9be0bacd382e44e9f3e9f52330a267d20f0` / grade `3` / control `DM-CHUNK-OVERLAP-OLD-PROC` / quote: 历史重建会恢复 150 字符参数以核对旧索引，但不得切换为 active。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 50. REP-T06-06

- Proposed split: `validation`
- Category: `general_operations`
- Question: 执行“默认向量模型”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t06-embedding-active.txt` / document `p2rep:document:3e1dc80bc59ffd25b7d3d7e4e5342225657cd6f5e023caea5238d465eafd4a24` / chunk `ce1baffebca4ffc998e7a6921831d77c424c51e96fc17eabd76d722988d214e8` / grade `3` / control `DM-EMBED-MODEL-ACT-PROC` / quote: 启动时读取模型身份；写索引和检索前分别核对 index metadata，发现不一致则拒绝。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:


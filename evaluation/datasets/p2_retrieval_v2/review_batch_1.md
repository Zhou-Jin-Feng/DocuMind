# DS-04 Human Review Batch 1

Cases: 50. Every case remains `assisted_unverified` until a human decision is recorded.

For each case, review the question, answerability, ambiguity and every proposed qrel. Record approve, modify or delete in `review_decisions.jsonl`; a batch-level approval is valid only after every case below has been inspected.

## 1. REP-T13-01

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 控制项 DM-STALE-STATE-ACT 的当前冻结值和规则是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `22c634b42c3bf2b44f44db69f12c776b31ade39b44251557400c036e3a2c2b0a` / grade `3` / control `DM-STALE-STATE-ACT` / quote: 文档存在但 active 内容版本与请求前提冲突时返回 409，不得退化为跨版本检索。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:
## 2. REP-T13-02

- Proposed split: `holdout`
- Category: `semantic`
- Question: 文档状态已经变化而客户端仍持有旧键时，服务应如何回应，现行规范要求怎样处理？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `ccf88db9291bbc878d67f59abec848f28e2ea53dfb8e01a7ec672ca28c73d44e` / grade `3` / control `DM-STALE-STATE-ACT-PROC` / quote: 读取 Registry 版本后执行前置条件比较；冲突响应只暴露稳定错误码和 request_id。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 3. REP-T13-03

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: DM-STALE-STATE-DRF 与 DM-STALE-STATE-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `22c634b42c3bf2b44f44db69f12c776b31ade39b44251557400c036e3a2c2b0a` / grade `3` / control `DM-STALE-STATE-ACT` / quote: 文档存在但 active 内容版本与请求前提冲突时返回 409，不得退化为跨版本检索。
  - source `t13-lifecycle-draft.txt` / document `p2rep:document:98b16b0c258f87642b475cae9b5345719a3c499e39888afcd72a2ccc093d3b26` / chunk `1f7000bd58aefee8e66f9e0ac8fd412917044bf3a19d5221f39fb8055d1a3bc0` / grade `1` / control `DM-STALE-STATE-DRF` / quote: 草案讨论用 412 表达显式 If-Match 失败，但公共契约尚未变更。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 4. REP-T13-04

- Proposed split: `holdout`
- Category: `non_plain_text`
- Question: 在 json_log 摘录中，DM-STALE-STATE-ACT 对应的配置值是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `ccf88db9291bbc878d67f59abec848f28e2ea53dfb8e01a7ec672ca28c73d44e` / grade `3` / control `DM-STALE-STATE-ACT-DATA` / quote: HTTP 409
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 5. REP-T13-05

- Proposed split: `holdout`
- Category: `authority_version`
- Question: “陈旧文档检索语义”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `22c634b42c3bf2b44f44db69f12c776b31ade39b44251557400c036e3a2c2b0a` / grade `3` / control `DM-STALE-STATE-ACT` / quote: 文档存在但 active 内容版本与请求前提冲突时返回 409，不得退化为跨版本检索。
  - source `t13-lifecycle-draft.txt` / document `p2rep:document:98b16b0c258f87642b475cae9b5345719a3c499e39888afcd72a2ccc093d3b26` / chunk `1f7000bd58aefee8e66f9e0ac8fd412917044bf3a19d5221f39fb8055d1a3bc0` / grade `1` / control `DM-STALE-STATE-DRF` / quote: 草案讨论用 412 表达显式 If-Match 失败，但公共契约尚未变更。
  - source `t13-lifecycle-superseded.txt` / document `p2rep:document:cf4e2826ce35b8bdbf2972589a11dd6b9a517074a07beaa5c3fb0ac34c3c10e6` / chunk `4a39aa07e6a82e2a3b124c8085ad0948a5850d198b629efef782e2fd9386cb96` / grade `1` / control `DM-STALE-STATE-OLD` / quote: 旧版把状态冲突隐藏为 404，无法区分不存在与版本陈旧，已被替代。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 6. REP-T13-06

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 执行“陈旧文档检索语义”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `ccf88db9291bbc878d67f59abec848f28e2ea53dfb8e01a7ec672ca28c73d44e` / grade `3` / control `DM-STALE-STATE-ACT-PROC` / quote: 读取 Registry 版本后执行前置条件比较；冲突响应只暴露稳定错误码和 request_id。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 7. REP-T13-07

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 未生效控制项 DM-STALE-STATE-DRF 提议的值是什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-draft.txt` / document `p2rep:document:98b16b0c258f87642b475cae9b5345719a3c499e39888afcd72a2ccc093d3b26` / chunk `1f7000bd58aefee8e66f9e0ac8fd412917044bf3a19d5221f39fb8055d1a3bc0` / grade `3` / control `DM-STALE-STATE-DRF` / quote: 草案讨论用 412 表达显式 If-Match 失败，但公共契约尚未变更。
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `22c634b42c3bf2b44f44db69f12c776b31ade39b44251557400c036e3a2c2b0a` / grade `1` / control `DM-STALE-STATE-ACT` / quote: 文档存在但 active 内容版本与请求前提冲突时返回 409，不得退化为跨版本检索。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 8. REP-T13-08

- Proposed split: `holdout`
- Category: `semantic`
- Question: 如果只讨论“陈旧文档检索语义”的下一版建议，草案准备怎样执行？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-draft.txt` / document `p2rep:document:98b16b0c258f87642b475cae9b5345719a3c499e39888afcd72a2ccc093d3b26` / chunk `36f5a564ed5bcf54433d8e3e0c67abc49fae2773c6db8ba21ebf6871c2d28441` / grade `3` / control `DM-STALE-STATE-DRF-PROC` / quote: 先补消费者契约样例并验证兼容性；没有版本发布不得改变 409。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 9. REP-T13-09

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: 历史控制项 DM-STALE-STATE-OLD 与当前行为有什么区别，故障处理中能否继续使用旧值？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `22c634b42c3bf2b44f44db69f12c776b31ade39b44251557400c036e3a2c2b0a` / grade `3` / control `DM-STALE-STATE-ACT` / quote: 文档存在但 active 内容版本与请求前提冲突时返回 409，不得退化为跨版本检索。
  - source `t13-lifecycle-superseded.txt` / document `p2rep:document:cf4e2826ce35b8bdbf2972589a11dd6b9a517074a07beaa5c3fb0ac34c3c10e6` / chunk `4a39aa07e6a82e2a3b124c8085ad0948a5850d198b629efef782e2fd9386cb96` / grade `2` / control `DM-STALE-STATE-OLD` / quote: 旧版把状态冲突隐藏为 404，无法区分不存在与版本陈旧，已被替代。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 10. REP-T13-10

- Proposed split: `holdout`
- Category: `non_plain_text`
- Question: 从草案的 json_log 摘录读取，DM-STALE-STATE-DRF 配置了什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-draft.txt` / document `p2rep:document:98b16b0c258f87642b475cae9b5345719a3c499e39888afcd72a2ccc093d3b26` / chunk `36f5a564ed5bcf54433d8e3e0c67abc49fae2773c6db8ba21ebf6871c2d28441` / grade `3` / control `DM-STALE-STATE-DRF-DATA` / quote: HTTP 412
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 11. REP-T13-11

- Proposed split: `holdout`
- Category: `authority_version`
- Question: DM-STALE-STATE-OLD 记录的是哪个历史版本，当前为什么不能把它当作权威规则？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-superseded.txt` / document `p2rep:document:cf4e2826ce35b8bdbf2972589a11dd6b9a517074a07beaa5c3fb0ac34c3c10e6` / chunk `4a39aa07e6a82e2a3b124c8085ad0948a5850d198b629efef782e2fd9386cb96` / grade `3` / control `DM-STALE-STATE-OLD` / quote: 旧版把状态冲突隐藏为 404，无法区分不存在与版本陈旧，已被替代。
  - source `t13-lifecycle-active.txt` / document `p2rep:document:30766e28f0ecee066c3cde8ce587abbbce2f3508f567ecab56d0558fcdff5c37` / chunk `22c634b42c3bf2b44f44db69f12c776b31ade39b44251557400c036e3a2c2b0a` / grade `2` / control `DM-STALE-STATE-ACT` / quote: 文档存在但 active 内容版本与请求前提冲突时返回 409，不得退化为跨版本检索。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 12. REP-T13-12

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 在复盘旧系统时，“陈旧文档检索语义”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t13-lifecycle-superseded.txt` / document `p2rep:document:cf4e2826ce35b8bdbf2972589a11dd6b9a517074a07beaa5c3fb0ac34c3c10e6` / chunk `c4d3c75466be4ba1b1c983a5b6e36cc945d75be7299652ee4ad9abe9df7f0494` / grade `3` / control `DM-STALE-STATE-OLD-PROC` / quote: 历史适配器统一返回 not found；当前诊断不得沿用该映射。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 13. REP-T13-13

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 未收录控制项 DM-STALE-STATE-UNKNOWN 的生产值是多少？
- Answerable: `false`
- Ambiguity: `unanswerable_absent`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 14. REP-T13-14

- Proposed split: `holdout`
- Category: `semantic`
- Question: 明年尚未发布的“陈旧文档检索语义”最终政策会如何调整？
- Answerable: `false`
- Ambiguity: `unanswerable_future`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 15. REP-T13-15

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: 在三份文件都没有记录外部托管平台的情况下，该平台对“陈旧文档检索语义”的强制值是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_external`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 16. REP-T13-16

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 负责“陈旧文档检索语义”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 17. REP-T14-01

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 控制项 DM-DELETE-RETENTION-ACT 的当前冻结值和规则是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `dd118b2eba23ecdf1648489429be79f78bb3213217b6eb15ec03353593e0c8ce` / grade `3` / control `DM-DELETE-RETENTION-ACT` / quote: 删除成功后文档立即对检索不可见，向量清理在同一请求的有界补偿流程中完成。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 18. REP-T14-02

- Proposed split: `holdout`
- Category: `semantic`
- Question: 用户删除文档后，Registry 与向量记录应在多长时间内清除，现行规范要求怎样处理？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `97589fe58d95cda364e2d2c60f390bdf22a9ba2ea6ba7d6f7497a89a69d0a5bb` / grade `3` / control `DM-DELETE-RETENTION-ACT-PROC` / quote: 先标记删除并阻断新读取，再按确切 index_id 删除向量；失败则记录可重试清理任务。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 19. REP-T14-03

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: DM-DELETE-RETENTION-DRF 与 DM-DELETE-RETENTION-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `dd118b2eba23ecdf1648489429be79f78bb3213217b6eb15ec03353593e0c8ce` / grade `3` / control `DM-DELETE-RETENTION-ACT` / quote: 删除成功后文档立即对检索不可见，向量清理在同一请求的有界补偿流程中完成。
  - source `t14-lifecycle-draft.txt` / document `p2rep:document:193cc36e4c1489568ff6b1cdd65049052c37b4534c1ec438a0cb2e25aad76f4b` / chunk `ce7b24629a746d48a28c28948b76f012d1abfa4433303af2e53bb4b8c5ca71b2` / grade `1` / control `DM-DELETE-RETENTION-DRF` / quote: 草案建议保留 24 小时可恢复墓碑，但隐私删除语义尚未批准。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 20. REP-T14-04

- Proposed split: `holdout`
- Category: `non_plain_text`
- Question: 在 ocr_extract 摘录中，DM-DELETE-RETENTION-ACT 对应的配置值是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `97589fe58d95cda364e2d2c60f390bdf22a9ba2ea6ba7d6f7497a89a69d0a5bb` / grade `3` / control `DM-DELETE-RETENTION-ACT-DATA` / quote: immediate logical delete and bounded cleanup
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 21. REP-T14-05

- Proposed split: `holdout`
- Category: `authority_version`
- Question: “删除后的索引保留”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `dd118b2eba23ecdf1648489429be79f78bb3213217b6eb15ec03353593e0c8ce` / grade `3` / control `DM-DELETE-RETENTION-ACT` / quote: 删除成功后文档立即对检索不可见，向量清理在同一请求的有界补偿流程中完成。
  - source `t14-lifecycle-draft.txt` / document `p2rep:document:193cc36e4c1489568ff6b1cdd65049052c37b4534c1ec438a0cb2e25aad76f4b` / chunk `ce7b24629a746d48a28c28948b76f012d1abfa4433303af2e53bb4b8c5ca71b2` / grade `1` / control `DM-DELETE-RETENTION-DRF` / quote: 草案建议保留 24 小时可恢复墓碑，但隐私删除语义尚未批准。
  - source `t14-lifecycle-superseded.txt` / document `p2rep:document:25fe5cee972e8294a7172d068dacef8044ad3b9d664ce2f8fec6c9af8e9802ce` / chunk `6ccf00b973fbb542a5c91b1f49fd896c0c1538e37fd0f8bc4ea56980b7f83646` / grade `1` / control `DM-DELETE-RETENTION-OLD` / quote: 旧版仅异步尽力删除向量，短时间内可能仍被查询，现已废止。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 22. REP-T14-06

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 执行“删除后的索引保留”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `97589fe58d95cda364e2d2c60f390bdf22a9ba2ea6ba7d6f7497a89a69d0a5bb` / grade `3` / control `DM-DELETE-RETENTION-ACT-PROC` / quote: 先标记删除并阻断新读取，再按确切 index_id 删除向量；失败则记录可重试清理任务。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 23. REP-T14-07

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 未生效控制项 DM-DELETE-RETENTION-DRF 提议的值是什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-draft.txt` / document `p2rep:document:193cc36e4c1489568ff6b1cdd65049052c37b4534c1ec438a0cb2e25aad76f4b` / chunk `ce7b24629a746d48a28c28948b76f012d1abfa4433303af2e53bb4b8c5ca71b2` / grade `3` / control `DM-DELETE-RETENTION-DRF` / quote: 草案建议保留 24 小时可恢复墓碑，但隐私删除语义尚未批准。
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `dd118b2eba23ecdf1648489429be79f78bb3213217b6eb15ec03353593e0c8ce` / grade `1` / control `DM-DELETE-RETENTION-ACT` / quote: 删除成功后文档立即对检索不可见，向量清理在同一请求的有界补偿流程中完成。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 24. REP-T14-08

- Proposed split: `holdout`
- Category: `semantic`
- Question: 如果只讨论“删除后的索引保留”的下一版建议，草案准备怎样执行？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-draft.txt` / document `p2rep:document:193cc36e4c1489568ff6b1cdd65049052c37b4534c1ec438a0cb2e25aad76f4b` / chunk `1e406823f97f51684db7a71a54d836edb361ee46c6177c6e5b6bad6856b2b50a` / grade `3` / control `DM-DELETE-RETENTION-DRF-PROC` / quote: 先定义恢复授权和密钥擦除边界；未获批准不得延迟当前清理。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 25. REP-T14-09

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: 历史控制项 DM-DELETE-RETENTION-OLD 与当前行为有什么区别，故障处理中能否继续使用旧值？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `dd118b2eba23ecdf1648489429be79f78bb3213217b6eb15ec03353593e0c8ce` / grade `3` / control `DM-DELETE-RETENTION-ACT` / quote: 删除成功后文档立即对检索不可见，向量清理在同一请求的有界补偿流程中完成。
  - source `t14-lifecycle-superseded.txt` / document `p2rep:document:25fe5cee972e8294a7172d068dacef8044ad3b9d664ce2f8fec6c9af8e9802ce` / chunk `6ccf00b973fbb542a5c91b1f49fd896c0c1538e37fd0f8bc4ea56980b7f83646` / grade `2` / control `DM-DELETE-RETENTION-OLD` / quote: 旧版仅异步尽力删除向量，短时间内可能仍被查询，现已废止。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 26. REP-T14-10

- Proposed split: `holdout`
- Category: `non_plain_text`
- Question: 从草案的 ocr_extract 摘录读取，DM-DELETE-RETENTION-DRF 配置了什么？
- Answerable: `true`
- Ambiguity: `clear_but_non_authoritative`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-draft.txt` / document `p2rep:document:193cc36e4c1489568ff6b1cdd65049052c37b4534c1ec438a0cb2e25aad76f4b` / chunk `1e406823f97f51684db7a71a54d836edb361ee46c6177c6e5b6bad6856b2b50a` / grade `3` / control `DM-DELETE-RETENTION-DRF-DATA` / quote: 24 hour recoverable tombstone
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 27. REP-T14-11

- Proposed split: `holdout`
- Category: `authority_version`
- Question: DM-DELETE-RETENTION-OLD 记录的是哪个历史版本，当前为什么不能把它当作权威规则？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-superseded.txt` / document `p2rep:document:25fe5cee972e8294a7172d068dacef8044ad3b9d664ce2f8fec6c9af8e9802ce` / chunk `6ccf00b973fbb542a5c91b1f49fd896c0c1538e37fd0f8bc4ea56980b7f83646` / grade `3` / control `DM-DELETE-RETENTION-OLD` / quote: 旧版仅异步尽力删除向量，短时间内可能仍被查询，现已废止。
  - source `t14-lifecycle-active.txt` / document `p2rep:document:dc0e201f1a28d8c81cb3cefc0218840521d3db313c71244a38883314ba806f4a` / chunk `dd118b2eba23ecdf1648489429be79f78bb3213217b6eb15ec03353593e0c8ce` / grade `2` / control `DM-DELETE-RETENTION-ACT` / quote: 删除成功后文档立即对检索不可见，向量清理在同一请求的有界补偿流程中完成。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 28. REP-T14-12

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 在复盘旧系统时，“删除后的索引保留”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t14-lifecycle-superseded.txt` / document `p2rep:document:25fe5cee972e8294a7172d068dacef8044ad3b9d664ce2f8fec6c9af8e9802ce` / chunk `c2d55d5c6321d58f08a1c09707ca9749e026280d94bb76a3aa8ac9bf8c171b5f` / grade `3` / control `DM-DELETE-RETENTION-OLD-PROC` / quote: 历史任务按文件名扫描删除；禁止在当前环境使用模糊目标。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 29. REP-T14-13

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 未收录控制项 DM-DELETE-RETENTION-UNKNOWN 的生产值是多少？
- Answerable: `false`
- Ambiguity: `unanswerable_absent`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 30. REP-T14-14

- Proposed split: `holdout`
- Category: `semantic`
- Question: 明年尚未发布的“删除后的索引保留”最终政策会如何调整？
- Answerable: `false`
- Ambiguity: `unanswerable_future`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 31. REP-T14-15

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: 在三份文件都没有记录外部托管平台的情况下，该平台对“删除后的索引保留”的强制值是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_external`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 32. REP-T14-16

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 负责“删除后的索引保留”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 33. REP-T15-02

- Proposed split: `holdout`
- Category: `semantic`
- Question: 多智能体一次查询最多能请求返回多少个证据块，现行规范要求怎样处理？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-active.txt` / document `p2rep:document:c6439f9670c1ee29916741ce926dd5cd3d8a5c29296ead3736a45113c5da38ae` / chunk `e33c8139ceb1e708c3eb92cff3ff8dfeecc6a1c8cd5134c1e411a29cd0a75a95` / grade `3` / control `DM-TOPK-LIMIT-ACT-PROC` / quote: Pydantic 入参层先校验整数范围；合法请求再传给当前单文档 Dense 检索器。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 34. REP-T15-03

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: DM-TOPK-LIMIT-DRF 与 DM-TOPK-LIMIT-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-active.txt` / document `p2rep:document:c6439f9670c1ee29916741ce926dd5cd3d8a5c29296ead3736a45113c5da38ae` / chunk `72e4e2110a56dc2c21dfb471e36259d5a30dd02926854e2460f7eb4c68697530` / grade `3` / control `DM-TOPK-LIMIT-ACT` / quote: 公共纯检索接口允许的 top_k 范围为 1 到 20，超过范围按参数错误拒绝。
  - source `t15-retrieval-draft.txt` / document `p2rep:document:3daa8b763d6e9c8d4f1feec35811f099689c57435e905c582f2471c7a4c36999` / chunk `7acdf0226b30e5ca1b1319ee52d5101fa0293332714b14fb0dc2051cad178f43` / grade `1` / control `DM-TOPK-LIMIT-DRF` / quote: 草案为可信内部调用方讨论 50 条上限，但认证和配额机制不在当前版本。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 35. REP-T15-04

- Proposed split: `holdout`
- Category: `non_plain_text`
- Question: 在 mixed_zh_en 摘录中，DM-TOPK-LIMIT-ACT 对应的配置值是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-active.txt` / document `p2rep:document:c6439f9670c1ee29916741ce926dd5cd3d8a5c29296ead3736a45113c5da38ae` / chunk `e33c8139ceb1e708c3eb92cff3ff8dfeecc6a1c8cd5134c1e411a29cd0a75a95` / grade `3` / control `DM-TOPK-LIMIT-ACT-DATA` / quote: top_k <= 20
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 36. REP-T15-05

- Proposed split: `holdout`
- Category: `authority_version`
- Question: “纯检索 Top-K 上限”同时检索到 active、draft、superseded 三份文件时，哪份可以作为当前直接证据？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-active.txt` / document `p2rep:document:c6439f9670c1ee29916741ce926dd5cd3d8a5c29296ead3736a45113c5da38ae` / chunk `72e4e2110a56dc2c21dfb471e36259d5a30dd02926854e2460f7eb4c68697530` / grade `3` / control `DM-TOPK-LIMIT-ACT` / quote: 公共纯检索接口允许的 top_k 范围为 1 到 20，超过范围按参数错误拒绝。
  - source `t15-retrieval-draft.txt` / document `p2rep:document:3daa8b763d6e9c8d4f1feec35811f099689c57435e905c582f2471c7a4c36999` / chunk `7acdf0226b30e5ca1b1319ee52d5101fa0293332714b14fb0dc2051cad178f43` / grade `1` / control `DM-TOPK-LIMIT-DRF` / quote: 草案为可信内部调用方讨论 50 条上限，但认证和配额机制不在当前版本。
  - source `t15-retrieval-superseded.txt` / document `p2rep:document:02d005f4be7f6c4d5a4ccbdc763b6f6ee5e6f0c0a33645639f82932d0e243334` / chunk `bdac3462d161c9263387f211140161a5c7cf370fe860d13c3325c1df023d15d3` / grade `1` / control `DM-TOPK-LIMIT-OLD` / quote: 初版纯检索将 top_k 限制为 10，当前已经扩展到 20。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 37. REP-T15-06

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 执行“纯检索 Top-K 上限”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-active.txt` / document `p2rep:document:c6439f9670c1ee29916741ce926dd5cd3d8a5c29296ead3736a45113c5da38ae` / chunk `e33c8139ceb1e708c3eb92cff3ff8dfeecc6a1c8cd5134c1e411a29cd0a75a95` / grade `3` / control `DM-TOPK-LIMIT-ACT-PROC` / quote: Pydantic 入参层先校验整数范围；合法请求再传给当前单文档 Dense 检索器。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 38. REP-T15-09

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: 历史控制项 DM-TOPK-LIMIT-OLD 与当前行为有什么区别，故障处理中能否继续使用旧值？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-active.txt` / document `p2rep:document:c6439f9670c1ee29916741ce926dd5cd3d8a5c29296ead3736a45113c5da38ae` / chunk `72e4e2110a56dc2c21dfb471e36259d5a30dd02926854e2460f7eb4c68697530` / grade `3` / control `DM-TOPK-LIMIT-ACT` / quote: 公共纯检索接口允许的 top_k 范围为 1 到 20，超过范围按参数错误拒绝。
  - source `t15-retrieval-superseded.txt` / document `p2rep:document:02d005f4be7f6c4d5a4ccbdc763b6f6ee5e6f0c0a33645639f82932d0e243334` / chunk `bdac3462d161c9263387f211140161a5c7cf370fe860d13c3325c1df023d15d3` / grade `2` / control `DM-TOPK-LIMIT-OLD` / quote: 初版纯检索将 top_k 限制为 10，当前已经扩展到 20。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 39. REP-T15-12

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 在复盘旧系统时，“纯检索 Top-K 上限”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t15-retrieval-superseded.txt` / document `p2rep:document:02d005f4be7f6c4d5a4ccbdc763b6f6ee5e6f0c0a33645639f82932d0e243334` / chunk `cc493083e452f5fc5094dbaa2c4d1c9b438739abd132a41bd1d27c59854066bc` / grade `3` / control `DM-TOPK-LIMIT-OLD-PROC` / quote: 旧请求模型在校验层拒绝 11 以上数值；仅用于兼容性回归。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 40. REP-T15-13

- Proposed split: `holdout`
- Category: `exact_lexical`
- Question: 未收录控制项 DM-TOPK-LIMIT-UNKNOWN 的生产值是多少？
- Answerable: `false`
- Ambiguity: `unanswerable_absent`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 41. REP-T15-14

- Proposed split: `holdout`
- Category: `semantic`
- Question: 明年尚未发布的“纯检索 Top-K 上限”最终政策会如何调整？
- Answerable: `false`
- Ambiguity: `unanswerable_future`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 42. REP-T15-15

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: 在三份文件都没有记录外部托管平台的情况下，该平台对“纯检索 Top-K 上限”的强制值是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_external`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 43. REP-T15-16

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 负责“纯检索 Top-K 上限”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 44. REP-T16-03

- Proposed split: `holdout`
- Category: `difficult_negative`
- Question: DM-DISTANCE-METRIC-DRF 与 DM-DISTANCE-METRIC-ACT 的值冲突时，线上应采用哪一个，为什么？
- Answerable: `true`
- Ambiguity: `multiple_relevant_authority_ordered`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t16-retrieval-active.txt` / document `p2rep:document:c7e238271f041eeb851138bfbe0487934181483e99dcea04e1f3a3a71a9a2c4a` / chunk `1a6072fa10850a32a9f38ea018ebe20307b73353dbcc1f8cb0c5ae633dd5fee8` / grade `3` / control `DM-DISTANCE-METRIC-ACT` / quote: 当前 Dense 检索使用 Milvus L2 距离，数值越小排名越靠前。
  - source `t16-retrieval-draft.txt` / document `p2rep:document:66f7be20719281310fd40ea5c8a733aafd5eb1c5ee2492b7c3af653bcc3ecd64` / chunk `6795501ae16d4f276d9e2033f131c441b94432ad62b226f57b52aa20c9a31458` / grade `1` / control `DM-DISTANCE-METRIC-DRF` / quote: 草案计划对照 COSINE，但需要完整重建索引，不能直接复用 L2 基线。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 45. REP-T16-06

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 执行“向量距离度量”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t16-retrieval-active.txt` / document `p2rep:document:c7e238271f041eeb851138bfbe0487934181483e99dcea04e1f3a3a71a9a2c4a` / chunk `3f61ad4607b2edd91664e7a3354d05e274700470ec50dd2256c91b1fca8e335f` / grade `3` / control `DM-DISTANCE-METRIC-ACT-PROC` / quote: 集合和搜索参数同时声明 L2；报告中保留原始 distance，禁止当作越大越好的相似度。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 46. REP-T16-12

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 在复盘旧系统时，“向量距离度量”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t16-retrieval-superseded.txt` / document `p2rep:document:a64330e5bd5d417bceda5fc2b35120e264b31250548387779595a9d24e2b5085` / chunk `1e5a7608cdae88a5ee6f1559e804a2f08a53997334fc6cf43244de71c0b1923a` / grade `3` / control `DM-DISTANCE-METRIC-OLD-PROC` / quote: 旧适配器只用于确定性单测；生产证据必须来自 L2 路径。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 47. REP-T16-16

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 负责“向量距离度量”审批的真实员工姓名、手机号和邮箱是什么？
- Answerable: `false`
- Ambiguity: `unanswerable_private`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels: none (no-answer)
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 48. REP-T17-06

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 执行“Reranker 上线闸门”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t17-retrieval-active.txt` / document `p2rep:document:cddb7a91019a0fd602396dca5add19b1d716814449f24537ef975b103ca0efa6` / chunk `73212bce8d42976dd21032a229507243bc1c5c9c2d4cf934a2c3499f8e9b424a` / grade `3` / control `DM-RERANK-GATE-ACT-PROC` / quote: 只有新代表性 gold 上无质量回归、成功率为 1.0 且 P95 增量同时不超过 750 ms 和 2 倍 Dense，才可重新申请。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 49. REP-T17-12

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 在复盘旧系统时，“Reranker 上线闸门”以前采用什么步骤？
- Answerable: `true`
- Ambiguity: `clear_historical_only`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t17-retrieval-superseded.txt` / document `p2rep:document:56bd100eb4d5c2fb80122aacf7120af75eaa61671586a4608d5db20578207c61` / chunk `845c444e183997aca320f1bbde4c223f129dc2fbd745ff486c7ce9d0fcdf76f8` / grade `3` / control `DM-RERANK-GATE-OLD-PROC` / quote: 历史报告仅用于说明失败原因；不得用持平结果替代新 gold 证据。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

## 50. REP-T18-06

- Proposed split: `holdout`
- Category: `general_operations`
- Question: 执行“检索就绪条件”当前流程时，前置核对和安全停止步骤是什么？
- Answerable: `true`
- Ambiguity: `clear`
- Privacy: `synthetic_safe_pending_human`
- Proposed qrels:
  - source `t18-health-active.txt` / document `p2rep:document:928b88290877782a20bc1054f0906102866025cb54087f823ee106993d25f6b9` / chunk `b879ffd0edaf04ca4e40ff47200201bd5f213f02e0ef511833725dd88f396976` / grade `3` / control `DM-READINESS-ACT-PROC` / quote: 依次核对 Registry、Embedding 和 Milvus 的有界探测；任一失败都返回 503 和脱敏组件状态。
- Human decision: `[ ] approve  [ ] modify  [ ] delete`
- Reviewer note:

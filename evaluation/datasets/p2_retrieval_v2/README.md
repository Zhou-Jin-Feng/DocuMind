# P2 Retrieval V2 Representative Dataset

Status: `DS-05 FROZEN`

This directory contains project-generated synthetic DocuMind operational material. It contains no private or production documents. The 75 documents cover 25 topics with active, draft and superseded variants and are chunked with the production `500/100` recursive policy.

- Documents: 75
- Chunks: 235
- Exploration pool: 400 assisted/unverified questions
- Gold candidates: 100
- Dataset SHA-256: `7f2440695b6f575be045e066544009a765a308544982adb8618bf5004bf418a3`

Human review: 94 approve, 6 modify, 0 delete, 0 pending.

`gold_dataset.jsonl` contains 100 retained cases. Every retained case has explicit human confirmation; modified qrels retain their audit trail in `review_decisions.jsonl`.

Review packets are split into `review_batch_1.md` and `review_batch_2.md`; machine-readable decisions are in `review_decisions.jsonl`.

DS-05 froze the validation/holdout boundary in `split_freeze.json` after
checking that the two 50-case splits share no case, normalized question, fact
family, topic, document, Chunk, qrel pair or evidence identity. Run the audit
and freeze validation before any evaluation:

```powershell
.\venv\Scripts\python.exe -m evaluation.representative_split_audit validate
```

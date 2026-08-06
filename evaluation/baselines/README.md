# Evaluation Baselines

Baseline files store the quality metrics that a later change must not reduce
beyond the configured tolerance. The checked-in demo baseline is only a
deterministic pipeline smoke baseline; it is not a claim about production RAG
quality.

Create a real baseline only after running the same golden dataset through a
real or test-isolated retrieval adapter. Do not compare reports generated from
different datasets, Top-K values, document IDs, or embedding models.

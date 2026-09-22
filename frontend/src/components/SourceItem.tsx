import type { SourceReference } from "../types";

export function SourceItem({ source, highlighted = false }: { source: SourceReference; highlighted?: boolean }) {
  const metrics = [
    source.distance != null ? `距离 ${source.distance.toFixed(4)}` : null,
    source.rerank_score != null ? `重排 ${source.rerank_score.toFixed(4)}` : null,
    source.fusion_score != null ? `融合 ${source.fusion_score.toFixed(5)}` : null,
  ].filter(Boolean);

  return (
    <article
      className={"source-item" + (highlighted ? " source-item-highlighted" : "")}
      data-source-rank={source.rank}
      aria-current={highlighted ? "true" : undefined}
    >
      <header>
        <span className="source-rank">{source.rank}</span>
        <div>
          <strong>{source.source}</strong>
          <span>{source.page_number ? `第 ${source.page_number} 页` : "文档片段"}</span>
        </div>
      </header>
      <p>{source.excerpt}</p>
      {metrics.length > 0 && <footer>{metrics.join(" · ")}</footer>}
    </article>
  );
}

import type { Root } from "mdast";
import type { SourceReference } from "../../types";

const CITATION_PATTERN = /\[文档([^\]]+)\]/g;

type MarkdownNode = {
  type?: string;
  value?: string;
  url?: string;
  title?: string | null;
  data?: { hProperties?: Record<string, string> };
  children?: MarkdownNode[];
};

function citationNode(label: string, rank: number): MarkdownNode {
  return {
    type: "link",
    url: "#documind-citation-" + rank,
    title: null,
    children: [{ type: "text", value: label }],
    data: {
      hProperties: {
        "data-documind-citation": "true",
        "data-documind-citation-rank": String(rank),
      },
    },
  };
}

function splitTextNode(node: MarkdownNode, validRanks: Set<number>): MarkdownNode[] {
  if (node.type !== "text" || typeof node.value !== "string") return [node];
  const result: MarkdownNode[] = [];
  let lastIndex = 0;
  CITATION_PATTERN.lastIndex = 0;
  for (const match of node.value.matchAll(CITATION_PATTERN)) {
    const fullMatch = match[0];
    const rawRank = match[1];
    const rank = Number(rawRank);
    const canonicalRank = /^[1-9]\d*$/.test(rawRank) && Number.isSafeInteger(rank);
    const start = match.index ?? 0;
    if (start > lastIndex) result.push({ type: "text", value: node.value.slice(lastIndex, start) });
    result.push(canonicalRank && validRanks.has(rank) ? citationNode(fullMatch, rank) : { type: "text", value: fullMatch });
    lastIndex = start + fullMatch.length;
  }
  if (lastIndex < node.value.length) result.push({ type: "text", value: node.value.slice(lastIndex) });
  return result.length ? result : [node];
}

function transformChildren(node: MarkdownNode, validRanks: Set<number>): void {
  if (!node.children) return;
  const nextChildren: MarkdownNode[] = [];
  for (const child of node.children) {
    if (child.type === "link" || child.type === "linkReference" || child.type === "inlineCode" || child.type === "code") {
      nextChildren.push(child);
    } else if (child.type === "text") {
      nextChildren.push(...splitTextNode(child, validRanks));
    } else {
      transformChildren(child, validRanks);
      nextChildren.push(child);
    }
  }
  node.children = nextChildren;
}

export function createCitationRemarkPlugin(sources: SourceReference[]) {
  const rankCounts = new Map<number, number>();
  for (const source of sources) {
    rankCounts.set(source.rank, (rankCounts.get(source.rank) ?? 0) + 1);
  }
  const validRanks = new Set(
    sources.filter((source) => rankCounts.get(source.rank) === 1).map((source) => source.rank),
  );
  return function citationRemarkPlugin() {
    return function transform(tree: Root) {
      transformChildren(tree as unknown as MarkdownNode, validRanks);
    };
  };
}

export const HIGHLIGHT_OPTIONS = { detect: false };

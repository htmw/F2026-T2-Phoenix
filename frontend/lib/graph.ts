import type { EdgeView, NodeView } from "./types";

/** Group nodes into columns so independent agents sit side by side. */
export function rankNodes(nodes: NodeView[], edges: EdgeView[]): NodeView[][] {
  const remaining = new Set(nodes.map((node) => node.key));
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const incoming = new Map<string, string[]>();
  for (const node of nodes) {
    incoming.set(node.key, []);
  }
  for (const edge of edges) {
    incoming.get(edge.target)?.push(edge.source);
  }

  const ranks: NodeView[][] = [];
  while (remaining.size > 0) {
    let ready = [...remaining].filter((key) =>
      (incoming.get(key) ?? []).every((source) => !remaining.has(source)),
    );
    if (ready.length === 0) {
      const fallback = remaining.values().next().value;
      ready = fallback ? [fallback] : [];
    }
    const column: NodeView[] = [];
    for (const key of ready) {
      const node = byKey.get(key);
      if (node) {
        column.push(node);
      }
      remaining.delete(key);
    }
    if (column.length === 0) {
      break;
    }
    ranks.push(column);
  }
  return ranks;
}

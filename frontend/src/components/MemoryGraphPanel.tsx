import React from 'react';
import {
  AlertTriangle,
  Expand,
  GitBranch,
  Info,
  Layers3,
  Minimize2,
  Move,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

import type { MemoryGraphEdge, MemoryGraphNode, MemoryGraphResponse } from '@/types';

type EdgeFilter = 'ALL' | 'CONTRADICTS' | 'SUPPORTS' | 'REPLICATES';
type LayoutMode = 'network' | 'timeline';

interface MemoryGraphPanelProps {
  graph: MemoryGraphResponse | null;
  loading?: boolean;
  error?: string | null;
}

type PositionedNode = MemoryGraphNode & {
  x: number;
  y: number;
  connected_count: number;
};

const CANVAS_WIDTH = 1400;
const CANVAS_HEIGHT = 860;

export const MemoryGraphPanel: React.FC<MemoryGraphPanelProps> = ({
  graph,
  loading = false,
  error = null,
}) => {
  const [edgeFilter, setEdgeFilter] = React.useState<EdgeFilter>('ALL');
  const [layoutMode, setLayoutMode] = React.useState<LayoutMode>('network');
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = React.useState<string | null>(null);
  const [showHelp, setShowHelp] = React.useState(false);
  const [isFullscreen, setIsFullscreen] = React.useState(false);
  const [transform, setTransform] = React.useState({ x: 0, y: 0, scale: 1 });

  const panelRef = React.useRef<HTMLDivElement | null>(null);
  const dragStateRef = React.useRef<{
    dragging: boolean;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];

  React.useEffect(() => {
    if (!nodes.length) {
      setSelectedNodeId(null);
      return;
    }
    const bestNode = [...nodes].sort((left, right) => {
      const leftScore = left.contradiction_count * 4 + left.edge_count * 2 + left.composite_confidence;
      const rightScore = right.contradiction_count * 4 + right.edge_count * 2 + right.composite_confidence;
      return rightScore - leftScore;
    })[0];
    setSelectedNodeId((current) => (current && nodes.some((node) => node.id === current) ? current : bestNode.id));
  }, [nodes]);

  React.useEffect(() => {
    const handler = () => {
      setIsFullscreen(document.fullscreenElement === panelRef.current);
    };
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const visibleEdges = React.useMemo(() => {
    switch (edgeFilter) {
      case 'CONTRADICTS':
        return edges.filter((edge) => edge.edge_type === 'CONTRADICTS');
      case 'SUPPORTS':
        return edges.filter((edge) => edge.edge_type === 'SUPPORTS');
      case 'REPLICATES':
        return edges.filter((edge) => edge.edge_type === 'REPLICATES');
      default:
        return edges;
    }
  }, [edgeFilter, edges]);

  const filteredNodeIds = React.useMemo(() => {
    if (!visibleEdges.length) return new Set(nodes.map((node) => node.id));
    return new Set(visibleEdges.flatMap((edge) => [edge.source, edge.target]));
  }, [visibleEdges, nodes]);

  const connectedIds = React.useMemo(() => {
    const map = new Map<string, Set<string>>();
    visibleEdges.forEach((edge) => {
      if (!map.has(edge.source)) map.set(edge.source, new Set<string>());
      if (!map.has(edge.target)) map.set(edge.target, new Set<string>());
      map.get(edge.source)?.add(edge.target);
      map.get(edge.target)?.add(edge.source);
    });
    return map;
  }, [visibleEdges]);

  const layoutNodes = React.useMemo(
    () => computeLayout(nodes.filter((node) => filteredNodeIds.has(node.id)), visibleEdges, layoutMode),
    [nodes, filteredNodeIds, visibleEdges, layoutMode],
  );
  const nodeMap = React.useMemo(() => new Map(layoutNodes.map((node) => [node.id, node])), [layoutNodes]);

  const activeNodeId = hoveredNodeId || selectedNodeId;
  const neighborIds = React.useMemo(() => {
    if (!activeNodeId) return new Set<string>();
    return new Set([activeNodeId, ...(connectedIds.get(activeNodeId) || [])]);
  }, [activeNodeId, connectedIds]);

  const selectedNode = selectedNodeId ? nodeMap.get(selectedNodeId) || null : null;
  const selectedNodeEdges = React.useMemo(
    () =>
      selectedNodeId
        ? visibleEdges.filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId)
        : [],
    [selectedNodeId, visibleEdges],
  );

  const clusterCount = countTopics(nodes);

  const resetView = React.useCallback(() => {
    setTransform({ x: 0, y: 0, scale: 1 });
  }, []);

  const toggleFullscreen = React.useCallback(async () => {
    const element = panelRef.current;
    if (!element) return;
    if (document.fullscreenElement === element) {
      await document.exitFullscreen();
    } else {
      await element.requestFullscreen();
    }
  }, []);

  const handleWheel = React.useCallback((event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const delta = event.deltaY < 0 ? 1.08 : 0.92;
    setTransform((current) => ({
      ...current,
      scale: clamp(current.scale * delta, 0.62, 2.4),
    }));
  }, []);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('[data-node-interactive="true"]')) return;
    dragStateRef.current = {
      dragging: true,
      startX: event.clientX,
      startY: event.clientY,
      originX: transform.x,
      originY: transform.y,
    };
    (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current?.dragging) return;
    const deltaX = event.clientX - dragStateRef.current.startX;
    const deltaY = event.clientY - dragStateRef.current.startY;
    setTransform((current) => ({
      ...current,
      x: dragStateRef.current ? dragStateRef.current.originX + deltaX : current.x,
      y: dragStateRef.current ? dragStateRef.current.originY + deltaY : current.y,
    }));
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current?.dragging) return;
    dragStateRef.current.dragging = false;
    (event.currentTarget as HTMLDivElement).releasePointerCapture(event.pointerId);
  };

  if (loading) {
    return (
      <section className="rounded-3xl border border-neutral-200 bg-white p-6 shadow-sm">
        <div className="flex h-[65vh] items-center justify-center text-sm text-neutral-500">
          Loading claim relationship map...
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-3xl border border-red-200 bg-red-50 p-6 shadow-sm">
        <div className="flex items-start gap-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <div>
            <div className="font-semibold text-red-900">Graph unavailable</div>
            <div className="mt-1">{error}</div>
          </div>
        </div>
      </section>
    );
  }

  if (!graph || !nodes.length) {
    return (
      <section className="rounded-3xl border border-neutral-200 bg-white p-6 shadow-sm">
        <div className="flex h-[65vh] flex-col items-center justify-center text-center">
          <GitBranch className="mb-3 h-10 w-10 text-neutral-300" />
          <h4 className="text-base font-semibold text-neutral-900">No relationship graph yet</h4>
          <p className="mt-2 max-w-md text-sm text-neutral-500">
            Once claims are persisted into memory, this graph will show how they support,
            replicate, refine, or contradict each other.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      ref={panelRef}
      className={`rounded-[28px] border border-neutral-200/80 bg-neutral-50 shadow-[0_20px_60px_rgba(15,23,42,0.08)] ${
        isFullscreen ? 'h-screen overflow-auto rounded-none border-none' : ''
      }`}
    >
      <div className="border-b border-neutral-200/80 bg-white px-6 py-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-500">
              <Layers3 className="h-3.5 w-3.5" />
              Claim Relationship Map
            </div>
            <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center">
              <h3 className="text-[1.35rem] font-semibold tracking-[-0.03em] text-neutral-950">
                Explore how memory links claims across the literature
              </h3>
              <div className="flex flex-wrap gap-2">
                <StatBadge label="Nodes" value={graph.stats.visible_nodes} />
                <StatBadge label="Edges" value={graph.stats.visible_edges} />
                <StatBadge label="Clusters" value={clusterCount} />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {(['ALL', 'CONTRADICTS', 'SUPPORTS', 'REPLICATES'] as EdgeFilter[]).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setEdgeFilter(filter)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  edgeFilter === filter
                    ? 'bg-neutral-950 text-white shadow-[0_10px_24px_rgba(15,23,42,0.18)]'
                    : 'border border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300 hover:text-neutral-900'
                }`}
              >
                {filter === 'ALL' ? 'All' : formatEdgeType(filter)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setLayoutMode('network')}
                className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                  layoutMode === 'network'
                    ? 'bg-white text-neutral-950 shadow-sm ring-1 ring-neutral-200'
                    : 'text-neutral-500 hover:text-neutral-800'
                }`}
              >
                Network
              </button>
              <button
                type="button"
                onClick={() => setLayoutMode('timeline')}
                className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                  layoutMode === 'timeline'
                    ? 'bg-white text-neutral-950 shadow-sm ring-1 ring-neutral-200'
                    : 'text-neutral-500 hover:text-neutral-800'
                }`}
              >
                Timeline
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <IconButton
                title="Show graph help"
                onClick={() => setShowHelp((current) => !current)}
                icon={<Info className="h-4 w-4" />}
              />
              <IconButton
                title="Reset graph view"
                onClick={resetView}
                icon={<RotateCcw className="h-4 w-4" />}
              />
              <IconButton
                title={isFullscreen ? 'Exit fullscreen' : 'Expand to fullscreen'}
                onClick={toggleFullscreen}
                icon={isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
              />
            </div>
          </div>

          <div className="relative overflow-hidden rounded-[28px] border border-neutral-800/60 bg-[radial-gradient(circle_at_top,_rgba(96,165,250,0.18),_transparent_30%),radial-gradient(circle_at_bottom_left,_rgba(139,92,246,0.15),_transparent_24%),linear-gradient(180deg,_#111827_0%,_#0f172a_100%)] shadow-[0_30px_90px_rgba(15,23,42,0.35)]">
            <div className="pointer-events-none absolute inset-0 opacity-[0.16]" style={gridBackgroundStyle} />

            <div className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-2 text-xs font-medium text-white/80 backdrop-blur-md">
              <Move className="h-3.5 w-3.5" />
              Scroll to zoom, drag to pan
            </div>

            {showHelp && (
              <div className="absolute left-4 top-16 z-20 max-w-xs rounded-2xl border border-white/10 bg-slate-950/86 p-4 text-sm leading-6 text-white/80 shadow-2xl backdrop-blur-xl">
                Nodes are individual claims. Color shows direction, size shows importance, and curved lines show relationships.
                Click a node to focus on its local subgraph and inspect why it matters.
              </div>
            )}

            <div className="absolute right-4 top-4 z-20 rounded-2xl border border-white/10 bg-slate-950/70 p-3 text-xs text-white/75 shadow-xl backdrop-blur-xl">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-white/50">Legend</div>
              <div className="space-y-2">
                <FloatingLegendItem color="bg-emerald-400" label="Positive" />
                <FloatingLegendItem color="bg-rose-400" label="Negative" />
                <FloatingLegendItem color="bg-slate-300" label="Neutral" />
                <FloatingLegendItem color="bg-violet-400" label="Contradictions" />
              </div>
            </div>

            <div className="absolute bottom-4 left-4 z-20 flex flex-wrap gap-2">
              {selectedNode && (
                <div className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-xs font-medium text-white backdrop-blur-md">
                  Focus mode: {selectedNode.connected_count} connected claims
                </div>
              )}
              {layoutMode === 'timeline' && (
                <div className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-xs font-medium text-white backdrop-blur-md">
                  Timeline view: newer claims trend to the right
                </div>
              )}
            </div>

            <div
              className={`relative h-[75vh] min-h-[38rem] w-full touch-none select-none ${dragStateRef.current?.dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
              onWheel={handleWheel}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerLeave={() => setHoveredNodeId(null)}
            >
              <svg viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} className="h-full w-full">
                <defs>
                  <filter id="graphNodeShadow" x="-50%" y="-50%" width="200%" height="200%">
                    <feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="rgba(15,23,42,0.45)" />
                  </filter>
                </defs>

                <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
                  {layoutMode === 'timeline' && renderTimelineGuides(layoutNodes)}

                  {visibleEdges.map((edge) => {
                    const source = nodeMap.get(edge.source);
                    const target = nodeMap.get(edge.target);
                    if (!source || !target) return null;
                    const relatedToActive =
                      !!activeNodeId && (edge.source === activeNodeId || edge.target === activeNodeId);
                    return (
                      <path
                        key={edge.id}
                        d={buildCurvedPath(source.x, source.y, target.x, target.y, edge.id)}
                        fill="none"
                        stroke={edgeColor(edge.edge_type)}
                        strokeWidth={relatedToActive ? 3.8 : Math.max(1.4, edge.edge_weight * 4.4)}
                        strokeOpacity={
                          activeNodeId
                            ? relatedToActive
                              ? 0.96
                              : 0.08
                            : edge.edge_type === 'CONTRADICTS'
                              ? 0.58
                              : 0.22
                        }
                        strokeLinecap="round"
                        className="transition-all duration-300"
                      />
                    );
                  })}

                  {layoutNodes.map((node) => {
                    const selected = selectedNodeId === node.id;
                    const hovered = hoveredNodeId === node.id;
                    const inFocus = !activeNodeId || neighborIds.has(node.id) || node.id === activeNodeId;
                    const radius = nodeRadius(node);
                    return (
                      <g
                        key={node.id}
                        transform={`translate(${node.x}, ${node.y})`}
                        data-node-interactive="true"
                        className="cursor-pointer transition-all duration-300"
                        onMouseEnter={() => setHoveredNodeId(node.id)}
                        onMouseLeave={() => setHoveredNodeId((current) => (current === node.id ? null : current))}
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedNodeId(node.id);
                        }}
                      >
                        {(selected || hovered) && (
                          <circle
                            r={radius + 12}
                            fill="none"
                            stroke={node.direction === 'negative' ? 'rgba(244,63,94,0.38)' : 'rgba(59,130,246,0.34)'}
                            strokeWidth={2}
                            strokeDasharray="4 8"
                          />
                        )}
                        <circle
                          r={radius + 5}
                          fill="rgba(255,255,255,0.14)"
                          opacity={inFocus ? 0.9 : 0.14}
                          filter="url(#graphNodeShadow)"
                        />
                        <circle
                          r={radius}
                          fill={nodeColor(node.direction)}
                          opacity={inFocus ? 0.96 : 0.18}
                          stroke={selected ? '#ffffff' : node.contradiction_count > 0 ? '#c084fc' : 'rgba(255,255,255,0.55)'}
                          strokeWidth={selected ? 3 : node.contradiction_count > 0 ? 2.2 : 1.25}
                        />
                        {selected && (
                          <circle
                            r={radius + 9}
                            fill="none"
                            stroke="rgba(255,255,255,0.28)"
                            strokeWidth={2}
                          />
                        )}
                        <title>{node.statement}</title>
                      </g>
                    );
                  })}
                </g>
              </svg>
            </div>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-[24px] border border-neutral-200/90 bg-white p-5 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-neutral-950">Selected claim</div>
                <div className="mt-1 text-xs text-neutral-500">
                  Click a node to reveal its local evidence neighborhood.
                </div>
              </div>
              <div className="rounded-full bg-neutral-950 px-3 py-1.5 text-xs font-semibold text-white">
                {selectedNode ? `${Math.round(selectedNode.composite_confidence * 100)}%` : 'No selection'}
              </div>
            </div>

            {selectedNode ? (
              <div className="mt-5 space-y-4">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Claim</div>
                  <div className="mt-2 text-base font-semibold leading-7 text-neutral-950">
                    {selectedNode.statement}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <InfoTile label="Direction" value={formatDirection(selectedNode.direction)} />
                  <InfoTile label="Type" value={formatTitleCase(selectedNode.claim_type)} />
                  <InfoTile label="Confidence" value={`${Math.round(selectedNode.composite_confidence * 100)}%`} />
                  <InfoTile label="Connections" value={`${selectedNode.connected_count}`} />
                </div>

                <div className="rounded-[22px] border border-blue-100 bg-blue-50/80 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-blue-950">
                    <Sparkles className="h-4 w-4 text-blue-600" />
                    Why this matters
                  </div>
                  <p className="mt-2 text-sm leading-6 text-blue-900/85">
                    {buildWhyItMattersSummary(selectedNodeEdges)}
                  </p>
                </div>

                {selectedNode.paper_title && (
                  <div className="rounded-[20px] bg-neutral-50 px-4 py-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Paper source</div>
                    <div className="mt-2 text-sm leading-6 text-neutral-700">{selectedNode.paper_title}</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4 text-sm text-neutral-500">
                Select a node in the graph to inspect the claim and its connected relationships.
              </div>
            )}
          </div>

          <div className="rounded-[24px] border border-neutral-200/90 bg-white p-5 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
            <div className="text-sm font-semibold text-neutral-950">Connected nodes</div>
            <div className="mt-3 space-y-2.5">
              {selectedNodeEdges.slice(0, 8).map((edge) => {
                const otherId = edge.source === selectedNodeId ? edge.target : edge.source;
                const otherNode = nodeMap.get(otherId);
                return (
                  <button
                    key={edge.id}
                    type="button"
                    onClick={() => setSelectedNodeId(otherId)}
                    className="w-full rounded-[18px] border border-neutral-200 bg-neutral-50 px-4 py-3 text-left transition hover:border-neutral-300 hover:bg-white"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-neutral-500">
                        {formatEdgeType(edge.edge_type)}
                      </span>
                      <span className="text-xs font-medium text-neutral-500">
                        {Math.round(edge.edge_weight * 100)}% weight
                      </span>
                    </div>
                    <div className="mt-2 text-sm font-medium leading-6 text-neutral-800">
                      {otherNode?.intervention_canonical}
                      {' -> '}
                      {otherNode?.outcome_canonical}
                    </div>
                  </button>
                );
              })}
              {selectedNodeEdges.length === 0 && (
                <div className="text-sm text-neutral-500">No visible connected nodes for the current filter.</div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
};

function computeLayout(
  nodes: MemoryGraphNode[],
  edges: MemoryGraphEdge[],
  mode: LayoutMode,
): PositionedNode[] {
  if (!nodes.length) return [];

  const connectedCount = new Map<string, number>();
  nodes.forEach((node) => connectedCount.set(node.id, 0));
  edges.forEach((edge) => {
    connectedCount.set(edge.source, (connectedCount.get(edge.source) || 0) + 1);
    connectedCount.set(edge.target, (connectedCount.get(edge.target) || 0) + 1);
  });

  if (mode === 'timeline') return computeTimelineLayout(nodes, connectedCount);
  return computeForceLayout(nodes, edges, connectedCount);
}

function computeForceLayout(
  nodes: MemoryGraphNode[],
  edges: MemoryGraphEdge[],
  connectedCount: Map<string, number>,
): PositionedNode[] {
  const topicOrder = [...new Set(nodes.map((node) => node.topic_key))];
  const nodeStates = nodes.map((node, index) => {
    const topicIndex = topicOrder.indexOf(node.topic_key);
    const angle = (topicIndex / Math.max(topicOrder.length, 1)) * Math.PI * 2 + (index % 5) * 0.24;
    const ring = 150 + topicIndex * 34;
    return {
      ...node,
      x: CANVAS_WIDTH / 2 + Math.cos(angle) * ring + ((index % 4) - 1.5) * 22,
      y: CANVAS_HEIGHT / 2 + Math.sin(angle) * ring + ((index % 3) - 1) * 24,
      vx: 0,
      vy: 0,
    };
  });

  const stateMap = new Map(nodeStates.map((node) => [node.id, node]));
  const springs = edges
    .map((edge) => {
      const source = stateMap.get(edge.source);
      const target = stateMap.get(edge.target);
      if (!source || !target) return null;
      const idealLength = edge.edge_type === 'CONTRADICTS' ? 190 : edge.edge_type === 'REPLICATES' ? 110 : 140;
      return { source, target, idealLength, weight: 0.02 + edge.edge_weight * 0.06 };
    })
    .filter(Boolean) as Array<{
    source: { x: number; y: number; vx: number; vy: number };
    target: { x: number; y: number; vx: number; vy: number };
    idealLength: number;
    weight: number;
  }>;

  for (let step = 0; step < 180; step += 1) {
    for (let i = 0; i < nodeStates.length; i += 1) {
      const left = nodeStates[i];
      for (let j = i + 1; j < nodeStates.length; j += 1) {
        const right = nodeStates[j];
        const dx = left.x - right.x;
        const dy = left.y - right.y;
        const distSq = Math.max(dx * dx + dy * dy, 1);
        const force = 3400 / distSq;
        const dist = Math.sqrt(distSq);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        left.vx += fx;
        left.vy += fy;
        right.vx -= fx;
        right.vy -= fy;
      }
    }

    springs.forEach((spring) => {
      const dx = spring.target.x - spring.source.x;
      const dy = spring.target.y - spring.source.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const displacement = dist - spring.idealLength;
      const fx = (dx / dist) * displacement * spring.weight;
      const fy = (dy / dist) * displacement * spring.weight;
      spring.source.vx += fx;
      spring.source.vy += fy;
      spring.target.vx -= fx;
      spring.target.vy -= fy;
    });

    nodeStates.forEach((node) => {
      node.vx += (CANVAS_WIDTH / 2 - node.x) * 0.0015;
      node.vy += (CANVAS_HEIGHT / 2 - node.y) * 0.0015;
      node.vx *= 0.82;
      node.vy *= 0.82;
      node.x = clamp(node.x + node.vx, 58, CANVAS_WIDTH - 58);
      node.y = clamp(node.y + node.vy, 58, CANVAS_HEIGHT - 58);
    });
  }

  return nodeStates.map((node) => ({
    ...node,
    connected_count: connectedCount.get(node.id) || 0,
  }));
}

function computeTimelineLayout(
  nodes: MemoryGraphNode[],
  connectedCount: Map<string, number>,
): PositionedNode[] {
  const years = nodes
    .map((node) => node.publication_year)
    .filter((year): year is number => typeof year === 'number');
  const minYear = years.length ? Math.min(...years) : new Date().getFullYear() - 10;
  const maxYear = years.length ? Math.max(...years) : new Date().getFullYear();
  const topics = [...new Set(nodes.map((node) => node.topic_key))];

  return nodes.map((node, index) => {
    const topicIndex = topics.indexOf(node.topic_key);
    const year = node.publication_year ?? minYear;
    const yearProgress = maxYear === minYear ? 0.5 : (year - minYear) / Math.max(maxYear - minYear, 1);
    const x = 110 + yearProgress * (CANVAS_WIDTH - 220);
    const laneHeight = topics.length <= 1 ? CANVAS_HEIGHT / 2 : 120 + topicIndex * ((CANVAS_HEIGHT - 240) / Math.max(topics.length - 1, 1));
    const offset = ((index % 5) - 2) * 18;
    return {
      ...node,
      x,
      y: clamp(laneHeight + offset, 60, CANVAS_HEIGHT - 60),
      connected_count: connectedCount.get(node.id) || 0,
    };
  });
}

function renderTimelineGuides(nodes: PositionedNode[]) {
  const years = [...new Set(nodes.map((node) => node.publication_year).filter((year): year is number => typeof year === 'number'))]
    .sort((left, right) => left - right)
    .slice(0, 6);

  return years.map((year) => {
    const yearNodes = nodes.filter((node) => node.publication_year === year);
    if (!yearNodes.length) return null;
    const x = yearNodes.reduce((sum, node) => sum + node.x, 0) / yearNodes.length;
    return (
      <g key={`year-${year}`}>
        <line x1={x} y1={48} x2={x} y2={CANVAS_HEIGHT - 48} stroke="rgba(255,255,255,0.08)" strokeDasharray="5 9" />
        <text x={x} y={36} textAnchor="middle" fontSize="12" fill="rgba(255,255,255,0.68)" fontWeight="600">
          {year}
        </text>
      </g>
    );
  });
}

const StatBadge: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="rounded-full border border-neutral-200 bg-white px-3.5 py-2 shadow-sm">
    <span className="text-xs font-medium text-neutral-500">{label}</span>
    <span className="ml-2 text-sm font-semibold text-neutral-950">{value}</span>
  </div>
);

const IconButton: React.FC<{ title: string; onClick: () => void; icon: React.ReactNode }> = ({
  title,
  onClick,
  icon,
}) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-neutral-200 bg-white text-neutral-600 shadow-sm transition hover:border-neutral-300 hover:text-neutral-900"
  >
    {icon}
  </button>
);

const FloatingLegendItem: React.FC<{ color: string; label: string }> = ({ color, label }) => (
  <div className="flex items-center gap-2">
    <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
    <span>{label}</span>
  </div>
);

const InfoTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-[18px] bg-neutral-50 px-4 py-3">
    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">{label}</div>
    <div className="mt-1 text-sm font-medium text-neutral-800">{value}</div>
  </div>
);

const gridBackgroundStyle: React.CSSProperties = {
  backgroundImage:
    'linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)',
  backgroundSize: '36px 36px',
};

function buildCurvedPath(x1: number, y1: number, x2: number, y2: number, seed: string) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const distance = Math.sqrt(dx * dx + dy * dy) || 1;
  const normalX = -dy / distance;
  const normalY = dx / distance;
  const seedValue = hashSeed(seed) % 2 === 0 ? 1 : -1;
  const curvature = Math.min(34, distance * 0.18) * seedValue;
  const cx = mx + normalX * curvature;
  const cy = my + normalY * curvature;
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

function hashSeed(seed: string) {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function nodeRadius(node: MemoryGraphNode) {
  return 7 + node.composite_confidence * 10 + Math.min(node.edge_count, 8) * 0.8;
}

function nodeColor(direction: MemoryGraphNode['direction']) {
  switch (direction) {
    case 'positive':
      return '#34d399';
    case 'negative':
      return '#fb7185';
    case 'null':
      return '#94a3b8';
    default:
      return '#cbd5e1';
  }
}

function edgeColor(edgeType: string) {
  switch (edgeType) {
    case 'CONTRADICTS':
      return '#8b5cf6';
    case 'SUPPORTS':
      return '#2dd4bf';
    case 'REPLICATES':
      return '#60a5fa';
    case 'REFINES':
      return '#f59e0b';
    case 'IS_SUBGROUP_OF':
      return '#cbd5e1';
    default:
      return '#cbd5e1';
  }
}

function buildWhyItMattersSummary(edges: MemoryGraphEdge[]) {
  const contradictions = edges.filter((edge) => edge.edge_type === 'CONTRADICTS').length;
  const supports = edges.filter((edge) => edge.edge_type === 'SUPPORTS').length;
  const replicates = edges.filter((edge) => edge.edge_type === 'REPLICATES').length;

  if (contradictions >= 2 && supports >= 2) {
    return `This claim sits at the center of a contested area: it has strong support, but ${contradictions} visible contradictions mean the literature is not fully settled.`;
  }
  if (contradictions >= 1) {
    return 'This claim matters because it is part of an active conflict in the literature, so it should shape how the current evidence is framed.';
  }
  if (supports + replicates >= 3) {
    return 'This is one of the clearer anchors in memory. Several nearby claims reinforce it, so it carries more structural weight than an isolated finding.';
  }
  return 'This claim is currently more isolated than central. It still contributes evidence, but it has not yet accumulated a large supporting neighborhood.';
}

function formatEdgeType(edgeType: string) {
  switch (edgeType) {
    case 'ALL':
      return 'All';
    case 'CONTRADICTS':
      return 'Contradictions';
    case 'SUPPORTS':
      return 'Supports';
    case 'REPLICATES':
      return 'Replicates';
    case 'IS_SUBGROUP_OF':
      return 'Subgroup';
    default:
      return formatTitleCase(edgeType);
  }
}

function formatDirection(direction: string) {
  switch (direction) {
    case 'positive':
      return 'Positive';
    case 'negative':
      return 'Negative';
    case 'null':
      return 'Neutral';
    default:
      return 'Unclear';
  }
}

function formatTitleCase(value: string) {
  return value
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function countTopics(nodes: MemoryGraphNode[]) {
  return new Set(nodes.map((node) => node.topic_key)).size;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

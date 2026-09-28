import { useEffect, useMemo } from 'react';
import {
  BaseEdge, Handle, Position, ReactFlow, ReactFlowProvider, getSmoothStepPath, useReactFlow,
  type Edge, type EdgeProps, type EdgeTypes, type Node, type NodeProps, type NodeTypes,
} from '@xyflow/react';
import { Activity, Bot, CalendarCheck, Database, History, Lightbulb, ScrollText, ShieldCheck, Wrench } from 'lucide-react';
import { EDGES, NODES, edgeId, type DiagramState, type NodeActivity, type NodeDef } from '../lib/derive';

// Fixed layout: the planning loop on top, the learning loop underneath, the policy -> gate
// edge climbing between them. Positions never change, so the eye can rest on the same spot.
const POS: Record<string, { x: number; y: number }> = {
  memory: { x: 20, y: 60 }, agent: { x: 240, y: 60 }, gate: { x: 460, y: 60 }, tools: { x: 680, y: 60 },
  outcomes: { x: 20, y: 240 }, risk: { x: 200, y: 240 }, proposal: { x: 380, y: 240 }, backtest: { x: 560, y: 240 }, policy: { x: 740, y: 240 },
};
const COLORS: Record<string, string> = {
  memory: 'var(--node-memory)', agent: 'var(--node-agent)', gate: 'var(--node-gate)', tools: 'var(--node-tools)',
  outcomes: 'var(--node-outcomes)', risk: 'var(--node-risk)', proposal: 'var(--node-proposal)', backtest: 'var(--node-backtest)', policy: 'var(--node-policy)',
};
const ICONS: Record<string, typeof Database> = {
  memory: Database, agent: Bot, gate: ShieldCheck, tools: Wrench, outcomes: CalendarCheck, risk: Activity, proposal: Lightbulb, backtest: History, policy: ScrollText,
};
// how each edge attaches: right->left along a row, top handles for the loop back, bottom/top across rows
const HANDLES: Record<string, { s: string; t: string; label?: string; faint?: boolean }> = {
  'memory->agent': { s: 'r', t: 'l' }, 'agent->gate': { s: 'r', t: 'l' }, 'gate->tools': { s: 'r', t: 'l' },
  'tools->agent': { s: 'ts', t: 'tt', label: 'results' },
  'outcomes->risk': { s: 'r', t: 'l' }, 'risk->proposal': { s: 'r', t: 'l' }, 'proposal->backtest': { s: 'r', t: 'l' }, 'backtest->policy': { s: 'r', t: 'l' },
  'policy->gate': { s: 'ts', t: 'bt', label: 'policy in force' },
  'tools->outcomes': { s: 'b', t: 'tt', label: 'time passes', faint: true },
};

type FlowNodeData = { def: NodeDef; activity: NodeActivity; selected: boolean; active: boolean };
type FlowNode = Node<FlowNodeData, 'flake'>;
type FlowEdgeData = { lit: boolean; traversed: boolean; faint: boolean; color: string; label?: string };
type FlowEdge = Edge<FlowEdgeData, 'flake'>;

function FlowNodeView({ data }: NodeProps<FlowNode>) {
  const Icon = ICONS[data.def.id];
  const a = data.activity;
  const cls = ['flow-node', data.active ? 'active' : '', a.status === 'warn' ? 'status-warn' : '', a.status === 'error' ? 'status-error' : '', data.selected ? 'selected' : ''].join(' ');
  return (
    <div className={cls} style={{ '--accent': COLORS[data.def.id] } as React.CSSProperties}
      data-testid={`node-${data.def.id}`} data-active={data.active} data-selected={data.selected} data-count={a.count} role="button" tabIndex={0}>
      <Handle type="target" position={Position.Left} id="l" />
      <Handle type="source" position={Position.Right} id="r" />
      <Handle type="target" position={Position.Top} id="tt" />
      <Handle type="source" position={Position.Top} id="ts" />
      <Handle type="source" position={Position.Bottom} id="b" />
      <Handle type="target" position={Position.Bottom} id="bt" />
      <div className="head"><span className="icon" style={{ background: COLORS[data.def.id] }}><Icon size={13} /></span>{data.def.label}</div>
      <div className="sub">{data.def.sub}</div>
      <div className="last" title={a.last?.summary ?? ''}>{a.last ? a.last.summary : 'idle'}</div>
      {a.count > 0 && <span className="count" aria-label={`${a.count} events`}>{a.count}</span>}
    </div>
  );
}

// React Flow's animating-edges technique: the path plus a dot that follows it with <animateMotion>.
function FlowEdgeView({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps<FlowEdge>) {
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 14 });
  const d = data!;
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: d.lit ? d.color : d.traversed ? '#64748b' : d.faint ? '#d1d5db' : '#cbd5e1', strokeWidth: d.lit ? 2.5 : d.traversed ? 2 : 1.5, strokeDasharray: d.faint ? '4 4' : undefined }} />
      {d.label && (
        <text x={labelX} y={labelY - 6} textAnchor="middle" className="react-flow__edge-text" style={{ fontSize: 10, fill: d.lit ? d.color : '#9ca3af', fontWeight: d.lit ? 700 : 400 }}>{d.label}</text>
      )}
      {d.lit && (
        <circle r="5" fill={d.color}>
          <animateMotion dur="1.4s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </>
  );
}

const nodeTypes: NodeTypes = { flake: FlowNodeView };
const edgeTypes: EdgeTypes = { flake: FlowEdgeView };

function FitOnResize() {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const el = document.querySelector('.diagram');
    if (!el) return;
    const ro = new ResizeObserver(() => fitView({ padding: 0.08, duration: 150 }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [fitView]);
  return null;
}

interface Props { diagram: DiagramState; selectedNode: string | null; onSelectNode: (id: string) => void }

export function AgentDiagram({ diagram, selectedNode, onSelectNode }: Props) {
  const nodes: FlowNode[] = useMemo(() => NODES.map((def) => ({
    id: def.id, type: 'flake', position: POS[def.id], draggable: false, selectable: false,
    data: { def, activity: diagram.nodes[def.id], selected: selectedNode === def.id, active: diagram.activeNode === def.id },
  })), [diagram, selectedNode]);
  const edges: FlowEdge[] = useMemo(() => EDGES.map(([a, b]) => {
    const id = edgeId(a, b);
    const h = HANDLES[id];
    const lit = diagram.litEdges.has(id);
    return {
      id, type: 'flake', source: a, target: b, sourceHandle: h.s, targetHandle: h.t, selectable: false, focusable: false,
      className: `${id === 'policy->gate' ? 'policy-gate' : ''} ${lit ? 'lit' : ''}`,
      data: { lit, traversed: diagram.traversed.has(id), faint: !!h.faint && !lit, color: COLORS[b] ?? '#64748b', label: h.label },
      zIndex: lit ? 10 : 0,
    };
  }), [diagram]);
  return (
    <div className="diagram" data-testid="diagram">
      <div className="legend"><span className="planning">Planning loop</span><span className="learning">Learning loop</span></div>
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.08 }}
          onNodeClick={(_, node) => onSelectNode(node.id)}
          nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} panOnDrag={false} zoomOnScroll={false} zoomOnPinch={false}
          zoomOnDoubleClick={false} preventScrolling={false} minZoom={0.2} maxZoom={1.5} proOptions={{ hideAttribution: true }}>
          <FitOnResize />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}

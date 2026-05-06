import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge as FlowEdge,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { api } from './api';
import { useSmartPoll } from './hooks/useSmartPoll';
import TaskNode from './components/TaskNode';
import Sidebar from './components/Sidebar';
import Legend from './components/Legend';
import type { AgentInfo, PipelineData, TaskStatus } from './types';

const nodeTypes = { task: TaskNode };

const TERMINAL_STATES = new Set(['completed', 'failed', 'cancelled']);

function buildFlowElements(pipeline: PipelineData, taskStatuses: Record<string, TaskStatus>) {
  const nodes: Node[] = [];
  const edges: FlowEdge[] = [];
  const levels = pipeline.levels;
  const NODE_W = 200;
  const NODE_GAP = 40;
  const LEVEL_GAP = 120;
  const maxWidth = Math.max(...levels.map(l => l.length)) * (NODE_W + NODE_GAP);

  levels.forEach((level, levelIdx) => {
    const levelWidth = level.length * (NODE_W + NODE_GAP) - NODE_GAP;
    const startX = (maxWidth - levelWidth) / 2;
    level.forEach((taskName, idx) => {
      const pNode = pipeline.nodes.find((n) => n.id === taskName);
      const status = taskStatuses[taskName] || ({} as Partial<TaskStatus>);
      nodes.push({
        id: taskName, type: 'task',
        position: { x: startX + idx * (NODE_W + NODE_GAP), y: levelIdx * LEVEL_GAP },
        data: {
          label: taskName, goal: pNode?.goal || '',
          model: status.model || pNode?.model || null,
          status: status.status || 'pending', iteration: status.iteration || 0,
          permissions: pNode?.permissions || {}, duration_ms: status.duration_ms || null,
          max_iterations: pNode?.max_iterations || 20, system_prompt: pNode?.system_prompt || null,
        },
      });
    });
  });

  pipeline.edges.forEach((e, i) => {
    edges.push({
      id: `e-${i}`, source: e.from, target: e.to,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#475569', width: 12, height: 12 },
      style: { stroke: '#475569', strokeWidth: 1.5 },
      animated: (taskStatuses[e.from]?.status === 'running'),
      ...(e.condition ? { label: e.condition, labelStyle: { fill: '#94a3b8', fontSize: 9 }, labelBgStyle: { fill: '#0f172a', fillOpacity: 0.9 } } : {}),
    });
  });
  return { nodes, edges };
}

export default function App() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [taskStatuses, setTaskStatuses] = useState<Record<string, TaskStatus>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [allRuns, setAllRuns] = useState<any[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState([] as any);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as any);

  // Ref to track current runId for updating allRuns inline
  const runIdRef = useRef(runId);
  runIdRef.current = runId;

  // Filter runs by currently selected pipeline
  const pipelineName = pipeline?.name || null;
  const runs = useMemo(
    () => pipelineName ? allRuns.filter((r) => r.pipeline_name === pipelineName) : allRuns,
    [allRuns, pipelineName],
  );

  // -- Helper: update a single run's status in allRuns without re-fetching the list --
  const updateRunInList = useCallback((id: string, status: string) => {
    setAllRuns((prev) => prev.map((r) => r.run_id === id ? { ...r, status } : r));
  }, []);

  // ==================== Data loading ====================

  // Load pipelines once on mount
  useEffect(() => {
    api.listPipelines().then((res) => setAgents(res.pipelines)).catch(console.error);
  }, []);

  // Load pipeline DAG when selected
  useEffect(() => {
    if (!selectedAgent) { setPipeline(null); return; }
    api.getPipeline(selectedAgent).then(setPipeline).catch(console.error);
    setTaskStatuses({});
    setRunId(null);
    setRunStatus(null);
    setSelectedNodeId(null);
  }, [selectedAgent]);

  // Build flow elements when pipeline or task statuses change
  useEffect(() => {
    if (!pipeline) { setNodes([]); setEdges([]); return; }
    const { nodes: n, edges: e } = buildFlowElements(pipeline, taskStatuses);
    setNodes(n);
    setEdges(e);
  }, [pipeline, taskStatuses, setNodes, setEdges]);

  // Load runs list once on mount — the ONLY request that fires when idle
  useEffect(() => {
    api.listRunsDirect().then((r) => setAllRuns(r.runs || [])).catch(() => {});
  }, []);

  // ==================== Polling (ONLY during active runs) ====================

  const isRunActive = !!runId && !!runStatus && !TERMINAL_STATES.has(runStatus);

  // Poll run status at 1s — updates task statuses AND syncs left panel inline
  useSmartPoll({
    fetcher: async () => {
      if (!runId) return null;
      const run = await api.getRun(runId);
      if (run) {
        setRunStatus(run.status);
        const statuses: Record<string, TaskStatus> = {};
        for (const [name, task] of Object.entries(run.tasks || {})) {
          statuses[name] = task as TaskStatus;
        }
        setTaskStatuses(statuses);
        // Sync left panel status inline — no separate list fetch needed
        updateRunInList(run.run_id, run.status);
      }
      return run;
    },
    interval: 1000,
    enabled: isRunActive,
    stopWhen: (run) => run && TERMINAL_STATES.has(run.status),
  });

  // ==================== One-shot fetches (user actions only) ====================

  // Fetch run status when user selects a run from the left panel
  useEffect(() => {
    if (!runId) return;
    api.getRunDirect(runId).then((run) => {
      setRunStatus(run.status);
      const statuses: Record<string, TaskStatus> = {};
      for (const [name, task] of Object.entries(run.tasks || {})) {
        statuses[name] = task as TaskStatus;
      }
      setTaskStatuses(statuses);
    }).catch(console.error);
  }, [runId]);

  // ==================== User actions ====================

  const handleRun = useCallback(async () => {
    if (!selectedAgent) return;
    try {
      const res = await api.runPipeline(selectedAgent, {});
      setRunId(res.run_id);
      setRunStatus('running');
      setTaskStatuses({});
      // Add new run to left panel immediately
      setAllRuns((prev) => [...prev, {
        run_id: res.run_id,
        pipeline_name: pipelineName || selectedAgent,
        status: 'running',
        started_at: Date.now() / 1000,
        started_time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        task_names: pipeline?.nodes.map((n) => n.id) || [],
      }]);
    } catch (err) { console.error(err); }
  }, [selectedAgent, pipelineName, pipeline]);

  const handleSelectRun = useCallback((id: string) => {
    setRunId(id);
    setTaskStatuses({});
    setSelectedNodeId(null);
  }, []);

  const handlePause = useCallback(async () => {
    if (!runId) return;
    setRunStatus('paused');
    updateRunInList(runId, 'paused');
    try { await api.pauseRun(runId); }
    catch (err) { console.error(err); setRunStatus('running'); updateRunInList(runId, 'running'); }
  }, [runId, updateRunInList]);

  const handleResume = useCallback(async () => {
    if (!runId) return;
    setRunStatus('running');
    updateRunInList(runId, 'running');
    try { await api.resumeRun(runId); }
    catch (err) { console.error(err); setRunStatus('paused'); updateRunInList(runId, 'paused'); }
  }, [runId, updateRunInList]);

  // ==================== Render ====================

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);
  const isRunning = runStatus === 'running';
  const isPaused = runStatus === 'paused';

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: '#0f172a' }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
        background: '#0f172a', borderBottom: '1px solid #1e293b', color: '#e2e8f0',
        fontFamily: "'Inter', system-ui", flexShrink: 0,
      }}>
        <strong style={{ fontSize: 15, color: '#60a5fa', marginRight: 6 }}>AgentPipe</strong>

        <select value={selectedAgent || ''} onChange={(e) => setSelectedAgent(e.target.value)}
          style={{ background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: 6, padding: '7px 10px', fontSize: 12 }}>
          <option value="">Pipeline...</option>
          {agents.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
        </select>

        <button onClick={handleRun} disabled={!selectedAgent || isRunning}
          style={{ padding: '7px 18px', background: '#22c55e', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12, opacity: (!selectedAgent || isRunning) ? 0.4 : 1 }}>
          ▶ Run
        </button>
        {isRunning && <button onClick={handlePause}
          style={{ padding: '7px 14px', background: '#f59e0b', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12 }}>⏸</button>}
        {isPaused && <button onClick={handleResume}
          style={{ padding: '7px 14px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12 }}>▶</button>}

        <div style={{ flex: 1 }} />

        {runId && runStatus && (
          <span style={{
            fontSize: 10, padding: '4px 10px', borderRadius: 10, fontWeight: 600, textTransform: 'uppercase',
            background: isRunning ? '#60a5fa15' : runStatus === 'completed' ? '#4ade8015' : runStatus === 'failed' ? '#f8717115' : isPaused ? '#fbbf2415' : '#94a3b815',
            color: isRunning ? '#60a5fa' : runStatus === 'completed' ? '#4ade80' : runStatus === 'failed' ? '#f87171' : isPaused ? '#fbbf24' : '#94a3b8',
          }}>{runStatus} · {runId.substring(0, 6)}</span>
        )}
      </div>

      {/* Main area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left: Runs panel */}
        <div style={{
          width: 220, borderRight: '1px solid #1e293b', overflowY: 'auto', flexShrink: 0,
          background: '#0f172a', fontFamily: "'Inter', system-ui",
        }}>
          <div style={{ padding: '10px 12px', fontSize: 10, color: '#475569', textTransform: 'uppercase', fontWeight: 600, borderBottom: '1px solid #1e293b' }}>
            Runs {pipelineName ? `· ${pipelineName}` : ''} ({runs.length})
          </div>
          {runs.length === 0 && (
            <div style={{ padding: 12, fontSize: 11, color: '#475569' }}>
              {pipelineName ? 'No runs for this pipeline' : 'No runs yet'}
            </div>
          )}
          {runs.slice().reverse().map((r) => {
            const isActive = r.run_id === runId;
            const sc: Record<string, string> = { running: '#60a5fa', completed: '#4ade80', failed: '#f87171', paused: '#fbbf24' };
            const color = sc[r.status] || '#94a3b8';
            return (
              <div
                key={r.run_id}
                onClick={() => handleSelectRun(r.run_id)}
                style={{
                  padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #1e293b',
                  background: isActive ? '#1e293b' : 'transparent',
                  borderLeft: isActive ? `3px solid ${color}` : '3px solid transparent',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: '#e2e8f0' }}>{r.run_id.substring(0, 8)}</span>
                  <span style={{ fontSize: 9, color, fontWeight: 600, textTransform: 'uppercase' }}>{r.status}</span>
                </div>
                <div style={{ fontSize: 9, color: '#64748b', marginTop: 2 }}>
                  {r.started_time || '—'}
                  {r.task_names && <span> · {r.task_names.length} tasks</span>}
                </div>
              </div>
            );
          })}
        </div>

        {/* Center: DAG canvas */}
        <div style={{ flex: 1, position: 'relative' }}>
          <ReactFlow
            nodes={nodes} edges={edges}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            fitView fitViewOptions={{ padding: 0.3 }}
            minZoom={0.5} maxZoom={2}
            defaultEdgeOptions={{ type: 'smoothstep' }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1e293b" gap={24} />
          </ReactFlow>
          <Legend />
        </div>

        {/* Right: Sidebar */}
        {selectedNode && (
          <Sidebar key={selectedNodeId} selectedNode={selectedNode} runId={runId} onClose={() => setSelectedNodeId(null)} />
        )}
      </div>
    </div>
  );
}

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge as FlowEdge,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { api, connectWS } from './api';
import TaskNode from './components/TaskNode';
import Sidebar from './components/Sidebar';
import Toolbar from './components/Toolbar';
import type { AgentInfo, PipelineData, WSEvent } from './types';

const nodeTypes = { task: TaskNode };

function buildFlowElements(pipeline: PipelineData, taskStatuses: Record<string, any>) {
  const nodes: Node[] = [];
  const edges: FlowEdge[] = [];

  const levels = pipeline.levels;
  const LEVEL_GAP = 160;
  const NODE_GAP = 280;

  levels.forEach((level, levelIdx) => {
    const totalWidth = level.length * NODE_GAP;
    const startX = -totalWidth / 2 + NODE_GAP / 2;

    level.forEach((taskName, idx) => {
      const pNode = pipeline.nodes.find((n) => n.id === taskName);
      const status = taskStatuses[taskName] || {};

      nodes.push({
        id: taskName,
        type: 'task',
        position: { x: startX + idx * NODE_GAP, y: levelIdx * LEVEL_GAP },
        data: {
          label: taskName,
          goal: pNode?.goal || '',
          model: status.model || pNode?.model || null,
          status: status.status || 'pending',
          iteration: status.iteration || 0,
          permissions: pNode?.permissions || {},
          duration_ms: status.duration_ms || null,
          max_iterations: pNode?.max_iterations || 20,
          system_prompt: pNode?.system_prompt || null,
        },
      });
    });
  });

  pipeline.edges.forEach((e, i) => {
    const edge: FlowEdge = {
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#585b70' },
      style: { stroke: '#585b70', strokeWidth: 2 },
      animated: (taskStatuses[e.source]?.status === 'running'),
    };
    if (e.condition) {
      edge.label = e.condition;
      edge.labelStyle = { fill: '#a6adc8', fontSize: 10 };
      edge.labelBgStyle = { fill: '#1e1e2e', fillOpacity: 0.9 };
    }
    edges.push(edge);
  });

  return { nodes, edges };
}

export default function App() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [taskStatuses, setTaskStatuses] = useState<Record<string, any>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([] as any);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as any);

  useEffect(() => {
    api.listAgents().then((res) => setAgents(res.agents)).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedAgent) { setPipeline(null); return; }
    api.getPipeline(selectedAgent).then((data) => {
      setPipeline(data);
      setTaskStatuses({});
      setRunId(null);
      setRunStatus(null);
    }).catch(console.error);
  }, [selectedAgent]);

  useEffect(() => {
    if (!pipeline) { setNodes([]); setEdges([]); return; }
    const { nodes: n, edges: e } = buildFlowElements(pipeline, taskStatuses);
    setNodes(n);
    setEdges(e);
  }, [pipeline, taskStatuses, setNodes, setEdges]);

  useEffect(() => {
    const ws = connectWS((event: WSEvent) => {
      if (event.type === 'task_status' && event.run_id === runId) {
        setTaskStatuses((prev) => ({
          ...prev,
          [event.task!]: { ...prev[event.task!], status: event.status, ...event.details },
        }));
      } else if (event.type === 'run_complete' && event.run_id === runId) {
        setRunStatus(event.status || 'completed');
      } else if (event.type === 'run_paused' && event.run_id === runId) {
        setRunStatus('paused');
      } else if (event.type === 'run_resumed' && event.run_id === runId) {
        setRunStatus('running');
      }
    });
    return () => ws.close();
  }, [runId]);

  const handleRunStarted = useCallback((id: string) => {
    setRunId(id);
    setRunStatus('running');
    setTaskStatuses({});
  }, []);

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: '#1e1e2e' }}>
      <Toolbar
        agents={agents}
        selectedAgent={selectedAgent}
        runId={runId}
        runStatus={runStatus}
        onSelectAgent={setSelectedAgent}
        onRunStarted={handleRunStarted}
      />
      <div style={{ flex: 1, position: 'relative' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedNodeId(node.id)}
          onPaneClick={() => setSelectedNodeId(null)}
          fitView
          minZoom={0.3}
          maxZoom={2}
          defaultEdgeOptions={{ type: 'smoothstep' }}
        >
          <Background color="#313244" gap={20} />
          <Controls style={{ background: '#1e1e2e', borderColor: '#313244' }} />
          <MiniMap
            nodeColor={(n: any) => {
              const s = n.data?.status;
              if (s === 'completed') return '#22c55e';
              if (s === 'running') return '#3b82f6';
              if (s === 'failed') return '#ef4444';
              return '#6b7280';
            }}
            style={{ background: '#11111b' }}
          />
        </ReactFlow>
        <Sidebar selectedNode={selectedNode} runId={runId} onClose={() => setSelectedNodeId(null)} />
      </div>
    </div>
  );
}

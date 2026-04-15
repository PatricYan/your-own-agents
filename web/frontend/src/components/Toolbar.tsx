import React, { useState } from 'react';
import { api } from '../api';
import type { AgentInfo } from '../types';

interface ToolbarProps {
  agents: AgentInfo[];
  selectedAgent: string | null;
  runId: string | null;
  runStatus: string | null;
  onSelectAgent: (name: string) => void;
  onRunStarted: (runId: string) => void;
}

export default function Toolbar({
  agents, selectedAgent, runId, runStatus, onSelectAgent, onRunStarted,
}: ToolbarProps) {
  const [input, setInput] = useState('{}');
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    if (!selectedAgent) return;
    setRunning(true);
    try {
      let inputData: Record<string, any> = {};
      try { inputData = JSON.parse(input); } catch {}
      const res = await api.runPipeline(selectedAgent, inputData);
      onRunStarted(res.run_id);
    } catch (err) {
      console.error('Run failed:', err);
    }
    setRunning(false);
  };

  const handlePause = async () => {
    if (runId) await api.pauseRun(runId);
  };

  const handleResume = async () => {
    if (runId) await api.resumeRun(runId);
  };

  const isRunning = runStatus === 'running';
  const isPaused = runStatus === 'paused';

  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px',
        background: '#11111b', borderBottom: '1px solid #313244', color: '#cdd6f4',
        fontFamily: 'system-ui',
      }}
    >
      <strong style={{ fontSize: 16, marginRight: 8 }}>AgentPipe</strong>

      <select
        value={selectedAgent || ''}
        onChange={(e) => onSelectAgent(e.target.value)}
        style={{ background: '#1e1e2e', color: '#cdd6f4', border: '1px solid #313244', borderRadius: 6, padding: '6px 12px', fontSize: 13 }}
      >
        <option value="">Select pipeline...</option>
        {agents.map((a) => (
          <option key={a.name} value={a.name}>{a.name}</option>
        ))}
      </select>

      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder='Input JSON: {"key": "value"}'
        style={{ flex: 1, background: '#1e1e2e', color: '#cdd6f4', border: '1px solid #313244', borderRadius: 6, padding: '6px 12px', fontSize: 12 }}
      />

      <button
        onClick={handleRun}
        disabled={!selectedAgent || running || isRunning}
        style={{ padding: '6px 20px', background: '#22c55e', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, opacity: (!selectedAgent || running || isRunning) ? 0.5 : 1 }}
      >
        ▶ Run
      </button>

      {isRunning && (
        <button
          onClick={handlePause}
          style={{ padding: '6px 16px', background: '#f59e0b', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}
        >
          ⏸ Pause
        </button>
      )}

      {isPaused && (
        <button
          onClick={handleResume}
          style={{ padding: '6px 16px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}
        >
          ▶ Resume
        </button>
      )}

      {runId && (
        <span style={{ fontSize: 11, color: '#7f849c' }}>
          Run: {runId} ({runStatus})
        </span>
      )}
    </div>
  );
}

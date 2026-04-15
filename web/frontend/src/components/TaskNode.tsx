import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';

const STATUS_COLORS: Record<string, string> = {
  pending: '#6b7280',
  running: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
  skipped: '#a855f7',
  paused: '#f59e0b',
};

interface TaskNodeData {
  label: string;
  goal: string;
  model: string | null;
  status: string;
  iteration: number;
  permissions: Record<string, string>;
  duration_ms: number | null;
  [key: string]: any;
}

function TaskNode({ data, selected }: NodeProps & { data: TaskNodeData }) {
  const color = STATUS_COLORS[data.status] || '#6b7280';
  const permList = Object.entries(data.permissions || {})
    .filter(([, v]) => v === 'allow')
    .map(([k]) => k);

  return (
    <div
      style={{
        background: '#1e1e2e',
        border: `2px solid ${color}`,
        borderRadius: 12,
        padding: '12px 16px',
        minWidth: 200,
        color: '#cdd6f4',
        fontFamily: 'system-ui, sans-serif',
        boxShadow: selected ? `0 0 0 2px ${color}` : '0 2px 8px rgba(0,0,0,0.3)',
        transition: 'border-color 0.3s, box-shadow 0.3s',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <strong style={{ fontSize: 14 }}>{data.label}</strong>
        <span
          style={{
            fontSize: 10,
            padding: '2px 8px',
            borderRadius: 10,
            background: color,
            color: '#fff',
            fontWeight: 600,
            textTransform: 'uppercase',
          }}
        >
          {data.status}
        </span>
      </div>

      <div style={{ fontSize: 11, color: '#a6adc8', marginBottom: 4 }}>
        {data.goal.length > 60 ? data.goal.substring(0, 60) + '...' : data.goal}
      </div>

      <div style={{ fontSize: 10, color: '#7f849c', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <span>🧠 {data.model || 'N/A'}</span>
        {data.status === 'running' && <span>🔄 iter {data.iteration}</span>}
        {data.duration_ms != null && <span>⏱ {(data.duration_ms / 1000).toFixed(1)}s</span>}
      </div>

      {permList.length > 0 && (
        <div style={{ fontSize: 9, color: '#585b70', marginTop: 4 }}>
          perms: {permList.join(', ')}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  );
}

export default memo(TaskNode);

import React, { memo, useState } from 'react';
import { Handle, Position } from '@xyflow/react';

const STATUS_STYLE: Record<string, { color: string; bg: string; icon: string }> = {
  pending:   { color: '#94a3b8', bg: '#94a3b810', icon: '○' },
  running:   { color: '#60a5fa', bg: '#60a5fa15', icon: '◉' },
  completed: { color: '#4ade80', bg: '#4ade8015', icon: '✓' },
  failed:    { color: '#f87171', bg: '#f8717115', icon: '✗' },
  skipped:   { color: '#c084fc', bg: '#c084fc15', icon: '⊘' },
  paused:    { color: '#fbbf24', bg: '#fbbf2415', icon: '⏸' },
};

function TaskNode({ data }: any) {
  const [hovered, setHovered] = useState(false);

  if (!data) return null;

  const s = STATUS_STYLE[data.status] || STATUS_STYLE.pending;
  const goal = data.goal || '';
  const goalShort = goal.length > 120 ? goal.substring(0, 120) + '...' : goal;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: s.bg,
        border: `1.5px solid ${s.color}50`,
        borderRadius: 10,
        padding: '10px 12px',
        color: '#e2e8f0',
        fontFamily: "'Inter', system-ui, sans-serif",
        cursor: 'pointer',
        width: 190,
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: s.color, width: 7, height: 7, border: '2px solid #0f172a' }} />

      {/* Left: status icon — vertically centered with the right block */}
      <div style={{
        fontSize: 20,
        color: s.color,
        lineHeight: 1,
        flexShrink: 0,
        width: 22,
        textAlign: 'center',
      }}>
        {s.icon}
      </div>

      {/* Right: name + model — vertically stacked, horizontally left-aligned */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12,
          fontWeight: 600,
          color: '#f1f5f9',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          lineHeight: 1.3,
        }}>
          {data.label}
        </div>
        <div style={{
          fontSize: 10,
          color: '#94a3b8',
          marginTop: 2,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          lineHeight: 1.3,
        }}>
          {data.model || '—'}
          {data.duration_ms != null && (
            <span style={{ color: '#64748b' }}> · {(data.duration_ms / 1000).toFixed(1)}s</span>
          )}
          {data.status === 'running' && data.iteration > 0 && (
            <span style={{ color: '#64748b' }}> · iter {data.iteration}</span>
          )}
        </div>
      </div>

      {/* Hover tooltip */}
      {hovered && goal && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 8px)',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#1e293b',
          color: '#e2e8f0',
          padding: '10px 14px',
          borderRadius: 8,
          fontSize: 11,
          lineHeight: 1.5,
          width: 280,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          boxShadow: '0 8px 24px rgba(0,0,0,0.7)',
          border: '1px solid #334155',
          pointerEvents: 'none',
          textAlign: 'left',
        }}>
          <div style={{ fontWeight: 600, marginBottom: 6, color: '#60a5fa', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>Goal</div>
          {goalShort}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: s.color, width: 7, height: 7, border: '2px solid #0f172a' }} />
    </div>
  );
}

export default memo(TaskNode);

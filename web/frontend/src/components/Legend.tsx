import React from 'react';

const items = [
  { icon: '○', label: 'Pending', color: '#94a3b8' },
  { icon: '◉', label: 'Running', color: '#60a5fa' },
  { icon: '✓', label: 'Completed', color: '#4ade80' },
  { icon: '✗', label: 'Failed', color: '#f87171' },
  { icon: '⊘', label: 'Skipped', color: '#c084fc' },
  { icon: '⏸', label: 'Paused', color: '#fbbf24' },
];

export default function Legend() {
  return (
    <div style={{
      position: 'absolute', bottom: 12, left: 12,
      background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8,
      padding: '6px 14px', zIndex: 5,
      display: 'flex', gap: 14, fontFamily: "'Inter', system-ui",
    }}>
      {items.map((item) => (
        <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ color: item.color, fontSize: 13 }}>{item.icon}</span>
          <span style={{ color: '#64748b', fontSize: 9, letterSpacing: 0.3 }}>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

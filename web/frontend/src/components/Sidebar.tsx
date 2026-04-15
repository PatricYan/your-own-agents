import React, { useState } from 'react';
import { api } from '../api';

interface SidebarProps {
  selectedNode: any | null;
  runId: string | null;
  onClose: () => void;
}

const PERM_KEYS = ['read', 'edit', 'write', 'bash', 'glob', 'grep', 'web_fetch'];

export default function Sidebar({ selectedNode, runId, onClose }: SidebarProps) {
  const [editGoal, setEditGoal] = useState('');
  const [editPrompt, setEditPrompt] = useState('');
  const [editPerms, setEditPerms] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  if (!selectedNode) return null;

  const data = selectedNode.data;
  const isRunning = runId != null;

  const handleOpen = () => {
    setEditGoal(data.goal || '');
    setEditPrompt(data.system_prompt || '');
    setEditPerms(data.permissions || {});
  };

  const handleSave = async () => {
    if (!runId) return;
    setSaving(true);
    try {
      const updates: Record<string, any> = {};
      if (editGoal && editGoal !== data.goal) updates.goal = editGoal;
      if (editPrompt !== (data.system_prompt || '')) updates.system_prompt = editPrompt;

      const permChanges: Record<string, string> = {};
      let hasPerm = false;
      for (const k of PERM_KEYS) {
        if (editPerms[k] && editPerms[k] !== (data.permissions?.[k] || 'deny')) {
          permChanges[k] = editPerms[k];
          hasPerm = true;
        }
      }
      if (hasPerm) updates.permissions = permChanges;

      if (Object.keys(updates).length > 0) {
        await api.updateTask(runId, data.label, updates);
      }
    } catch (err) {
      console.error('Failed to update task:', err);
    }
    setSaving(false);
  };

  return (
    <div
      style={{
        position: 'fixed', right: 0, top: 0, bottom: 0, width: 360,
        background: '#181825', borderLeft: '1px solid #313244', padding: 20,
        overflowY: 'auto', color: '#cdd6f4', fontFamily: 'system-ui',
        zIndex: 10,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>{data.label}</h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#a6adc8', cursor: 'pointer', fontSize: 18 }}>✕</button>
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 11, color: '#7f849c' }}>Status</label>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{data.status}</div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 11, color: '#7f849c' }}>Model</label>
        <div>{data.model || 'N/A'}</div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 11, color: '#7f849c' }}>Goal</label>
        {isRunning ? (
          <textarea
            value={editGoal || data.goal}
            onChange={(e) => setEditGoal(e.target.value)}
            onFocus={handleOpen}
            style={{ width: '100%', minHeight: 60, background: '#1e1e2e', color: '#cdd6f4', border: '1px solid #313244', borderRadius: 6, padding: 8, fontSize: 12 }}
          />
        ) : (
          <div style={{ fontSize: 12 }}>{data.goal}</div>
        )}
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 11, color: '#7f849c' }}>Permissions</label>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginTop: 4 }}>
          {PERM_KEYS.map((k) => {
            const val = isRunning ? (editPerms[k] || data.permissions?.[k] || 'deny') : (data.permissions?.[k] || 'deny');
            return (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 11, width: 70 }}>{k}</span>
                {isRunning ? (
                  <select
                    value={val}
                    onChange={(e) => { handleOpen(); setEditPerms({ ...editPerms, [k]: e.target.value }); }}
                    style={{ background: '#1e1e2e', color: '#cdd6f4', border: '1px solid #313244', borderRadius: 4, fontSize: 11, padding: 2 }}
                  >
                    <option value="allow">allow</option>
                    <option value="ask">ask</option>
                    <option value="deny">deny</option>
                  </select>
                ) : (
                  <span style={{ fontSize: 11, color: val === 'allow' ? '#22c55e' : val === 'ask' ? '#f59e0b' : '#ef4444' }}>{val}</span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {data.system_prompt && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: '#7f849c' }}>System Prompt</label>
          {isRunning ? (
            <textarea
              value={editPrompt || data.system_prompt || ''}
              onChange={(e) => setEditPrompt(e.target.value)}
              onFocus={handleOpen}
              style={{ width: '100%', minHeight: 80, background: '#1e1e2e', color: '#cdd6f4', border: '1px solid #313244', borderRadius: 6, padding: 8, fontSize: 12 }}
            />
          ) : (
            <div style={{ fontSize: 11, color: '#a6adc8' }}>{data.system_prompt}</div>
          )}
        </div>
      )}

      {data.iteration > 0 && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: '#7f849c' }}>Iteration</label>
          <div>{data.iteration} / {data.max_iterations}</div>
        </div>
      )}

      {data.duration_ms != null && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: '#7f849c' }}>Duration</label>
          <div>{(data.duration_ms / 1000).toFixed(2)}s</div>
        </div>
      )}

      {isRunning && (
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            width: '100%', padding: '10px 0', marginTop: 12,
            background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8,
            cursor: 'pointer', fontWeight: 600, fontSize: 14,
          }}
        >
          {saving ? 'Saving...' : 'Apply Changes'}
        </button>
      )}
    </div>
  );
}

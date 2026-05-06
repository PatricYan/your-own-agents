import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { LogEntry } from '../types';

interface SidebarProps {
  selectedNode: any | null;
  runId: string | null;
  onClose: () => void;
}

const PERM_KEYS = ['read', 'edit', 'bash', 'glob', 'grep', 'webfetch'];
const PERM_COLORS: Record<string, string> = { allow: '#4ade80', ask: '#fbbf24', deny: '#f87171' };

/**
 * Merge consecutive "content" log entries into single text blocks.
 * The backend stores each streaming token as a separate log entry,
 * which looks terrible rendered individually. This coalesces them
 * into readable paragraphs.
 */
function mergeContentLogs(raw: LogEntry[]): LogEntry[] {
  const merged: LogEntry[] = [];
  let contentBuf = '';

  for (const entry of raw) {
    if (entry.type === 'content') {
      contentBuf += entry.text || '';
    } else {
      // Flush accumulated content before non-content entry
      if (contentBuf) {
        merged.push({ type: 'content', text: contentBuf });
        contentBuf = '';
      }
      merged.push(entry);
    }
  }
  // Flush trailing content
  if (contentBuf) {
    merged.push({ type: 'content', text: contentBuf });
  }
  return merged;
}

export default function Sidebar({ selectedNode, runId, onClose }: SidebarProps) {
  const [editGoal, setEditGoal] = useState('');
  const [editPrompt, setEditPrompt] = useState('');
  const [editPerms, setEditPerms] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  // Auto-select logs tab when a run is active, details when no run
  const [activeTab, setActiveTab] = useState<'info' | 'logs'>(runId ? 'logs' : 'info');
  const [rawLogs, setRawLogs] = useState<LogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const cursorRef = useRef(0);

  const data = selectedNode?.data;
  const taskName = data?.label || selectedNode?.id || 'unknown';
  const hasRun = runId != null;

  // Merge consecutive content tokens into readable text blocks
  const logs = mergeContentLogs(rawLogs);

  // Cursor-based log polling: fetch once, then poll only while task is still active.
  // Stops automatically when task reaches a terminal state (completed/failed/skipped).
  useEffect(() => {
    if (activeTab !== 'logs' || !runId) {
      return;
    }

    setRawLogs([]);
    cursorRef.current = 0;
    setLogsLoading(true);
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const TERMINAL = new Set(['completed', 'failed', 'skipped', 'cancelled']);

    const fetchLogs = async () => {
      try {
        const res = await api.getTaskLogs(runId, taskName, cursorRef.current);
        if (cancelled) return;

        if (res.logs.length > 0) {
          setRawLogs((prev) => [...prev, ...res.logs]);
          cursorRef.current = res.cursor;
        }
        setLogsLoading(false);

        // Stop polling once the task is done — no more logs will appear
        if (TERMINAL.has(res.status) && intervalId !== null) {
          clearInterval(intervalId);
          intervalId = null;
        }
      } catch {
        if (!cancelled) setLogsLoading(false);
      }
    };

    fetchLogs();
    intervalId = setInterval(fetchLogs, 2000);

    return () => {
      cancelled = true;
      if (intervalId !== null) clearInterval(intervalId);
    };
  }, [activeTab, runId, taskName]);

  const handleSave = useCallback(async () => {
    if (!runId || !data) return;
    setSaving(true);
    try {
      const updates: Record<string, any> = {};
      if (editGoal && editGoal !== (data.goal || '')) updates.goal = editGoal;
      if (editPrompt && editPrompt !== (data.system_prompt || '')) updates.system_prompt = editPrompt;
      const pc: Record<string, string> = {};
      for (const k of PERM_KEYS) { if (editPerms[k]) pc[k] = editPerms[k]; }
      if (Object.keys(pc).length > 0) updates.permissions = pc;
      if (Object.keys(updates).length > 0) await api.updateTask(runId, taskName, updates);
    } catch (err) { console.error(err); }
    setSaving(false);
  }, [runId, data, editGoal, editPrompt, editPerms, taskName]);

  const getPermLevel = (key: string): string => {
    const perms = data?.permissions || {};
    const val = perms[key];
    if (typeof val === 'string') return val;
    if (typeof val === 'object') return 'custom';
    return perms['*'] || 'deny';
  };

  if (!data) return null;

  return (
    <div style={{
      width: 380, borderLeft: '1px solid #1e293b', background: '#0f172a',
      color: '#e2e8f0', fontFamily: "'Inter', system-ui",
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{ padding: '12px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{taskName}</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
            <StatusBadge status={data.status} />
            {data.model && <span style={{ fontSize: 10, color: '#64748b' }}>{data.model}</span>}
            {data.duration_ms != null && <span style={{ fontSize: 10, color: '#64748b' }}>{(data.duration_ms / 1000).toFixed(1)}s</span>}
          </div>
        </div>
        <button onClick={onClose} style={{ background: '#1e293b', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 14, borderRadius: 6, width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>×</button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
        {(['info', 'logs'] as const).map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            flex: 1, padding: '9px 0', background: 'none', border: 'none', cursor: 'pointer',
            color: activeTab === tab ? '#60a5fa' : '#64748b', fontSize: 11, fontWeight: 600,
            textTransform: 'uppercase', letterSpacing: 0.5,
            borderBottom: activeTab === tab ? '2px solid #60a5fa' : '2px solid transparent',
          }}>
            {tab === 'info' ? 'Details' : `Logs${rawLogs.length > 0 ? ` (${rawLogs.length})` : ''}`}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
        {activeTab === 'info' ? (
          <div style={{ padding: 14 }}>
            <Row label="Goal">
              {hasRun ? <textarea defaultValue={data.goal || ''} onChange={(e) => setEditGoal(e.target.value)} style={textareaStyle} />
                : <div style={textStyle}>{data.goal || 'none'}</div>}
            </Row>
            <Row label="Permissions">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
                {PERM_KEYS.map((k) => {
                  const level = getPermLevel(k);
                  return (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ fontSize: 10, width: 55, color: '#64748b' }}>{k}</span>
                      {hasRun ? (
                        <select defaultValue={level} onChange={(e) => setEditPerms({ ...editPerms, [k]: e.target.value })} style={selectStyle}>
                          <option value="allow">allow</option><option value="ask">ask</option><option value="deny">deny</option>
                        </select>
                      ) : (
                        <span style={{ fontSize: 10, color: PERM_COLORS[level] || '#64748b', fontWeight: 600 }}>{level}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Row>
            {hasRun && <button onClick={handleSave} disabled={saving} style={buttonStyle}>{saving ? 'Saving...' : 'Apply Changes'}</button>}
          </div>
        ) : (
          <div style={{ padding: 12, fontSize: 12, fontFamily: "'Fira Code', monospace", color: '#cbd5e1', lineHeight: 1.7 }}>
            {logsLoading && rawLogs.length === 0 && <div style={{ color: '#475569' }}>Loading...</div>}
            {!logsLoading && rawLogs.length === 0 && <div style={{ color: '#475569' }}>No logs yet.</div>}
            {logs.map((log, i) => {
              if (log.type === 'content') {
                return (
                  <div key={i} style={{ marginBottom: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {log.text}
                  </div>
                );
              }
              if (log.type === 'tool_call') {
                return (
                  <div key={i} style={{ marginBottom: 6, padding: '4px 8px', background: '#1e293b', borderRadius: 4, borderLeft: '3px solid #60a5fa' }}>
                    <span style={{ color: '#60a5fa', fontWeight: 600 }}>{log.name}</span>
                    <span style={{ color: '#64748b' }}>({(log.args || '').substring(0, 100)})</span>
                  </div>
                );
              }
              if (log.type === 'iteration') {
                return (
                  <div key={i} style={{ marginBottom: 4, marginTop: 8, fontSize: 10, color: '#fbbf24', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    — iteration {log.iteration} · {log.phase} —
                  </div>
                );
              }
              return null;
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 3, fontWeight: 600 }}>{label}</div>
      {children}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const c: Record<string, string> = { pending: '#94a3b8', running: '#60a5fa', completed: '#4ade80', failed: '#f87171', skipped: '#c084fc', paused: '#fbbf24' };
  return <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 8, background: `${c[status] || '#94a3b8'}15`, color: c[status] || '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>{status || 'pending'}</span>;
}

const textareaStyle: React.CSSProperties = { width: '100%', minHeight: 50, background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: 6, padding: 8, fontSize: 11, fontFamily: "'Inter', system-ui", resize: 'vertical', lineHeight: 1.5, boxSizing: 'border-box' };
const selectStyle: React.CSSProperties = { background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: 4, fontSize: 10, padding: '2px 4px' };
const textStyle: React.CSSProperties = { fontSize: 11, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#94a3b8' };
const buttonStyle: React.CSSProperties = { width: '100%', padding: '9px 0', marginTop: 10, background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 12 };

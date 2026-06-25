import { useEffect, useState } from 'react';
import { getAdminAgents, setAgentFlags } from '../../api';
import type { AdminAgent } from '../../api';
import { fmtUsd } from '../../utils/format';
import './Dashboard.css';

// Operator-only dashboard. Gated by the admin key (sent as X-Admin-Key); the key
// lives in sessionStorage so a refresh keeps you in but a closed tab logs out.
const KEY_STORAGE = 'quip:adminKey';

type LoadState = 'gate' | 'loading' | 'ready' | 'error';
type Patch = { hidden?: boolean; disabled?: boolean };

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function AdminDashboard() {
  const [adminKey, setAdminKey] = useState<string>(() => {
    try { return sessionStorage.getItem(KEY_STORAGE) ?? ''; } catch { return ''; }
  });
  const [keyInput, setKeyInput] = useState('');
  const [agents, setAgents] = useState<AdminAgent[]>([]);
  const [loadState, setLoadState] = useState<LoadState>(adminKey ? 'loading' : 'gate');
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // A bump-to-refetch counter, so toggles and the Refresh button reload the list
  // (ranks shift when an agent's visibility changes).
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    if (!adminKey) return;
    let cancelled = false;
    setLoadState('loading');
    setError(null);
    getAdminAgents(adminKey)
      .then(rows => { if (!cancelled) { setAgents(rows); setLoadState('ready'); } })
      .catch(err => {
        if (cancelled) return;
        if ((err as { status?: number })?.status === 403) {
          try { sessionStorage.removeItem(KEY_STORAGE); } catch { /* ignore */ }
          setAdminKey('');
          setLoadState('gate');
          setError('That admin key was rejected.');
        } else {
          setLoadState('error');
          setError(err instanceof Error ? err.message : 'Could not load agents.');
        }
      });
    return () => { cancelled = true; };
  }, [adminKey, refreshNonce]);

  function unlock() {
    const key = keyInput.trim();
    if (!key) return;
    try { sessionStorage.setItem(KEY_STORAGE, key); } catch { /* ignore */ }
    setKeyInput('');
    setAdminKey(key);
  }

  function lock() {
    try { sessionStorage.removeItem(KEY_STORAGE); } catch { /* ignore */ }
    setAgents([]);
    setAdminKey('');
    setLoadState('gate');
  }

  async function toggle(agentId: string, patch: Patch) {
    if (busyId) return;
    setBusyId(agentId);
    setError(null);
    try {
      await setAgentFlags(adminKey, agentId, patch);
      setRefreshNonce(n => n + 1); // refetch — ranks change when visibility flips
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed.');
    } finally {
      setBusyId(null);
    }
  }

  if (loadState === 'gate') {
    return (
      <div className="admin-gate">
        <form className="admin-gate-card" onSubmit={e => { e.preventDefault(); unlock(); }}>
          <h1>Admin dashboard</h1>
          <p>Enter the admin key to view and manage agents.</p>
          <input
            type="password"
            autoFocus
            placeholder="Admin key"
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
          />
          <button type="submit">Unlock</button>
          {error && <div className="admin-gate-err">{error}</div>}
        </form>
      </div>
    );
  }

  const onBoard = agents.filter(a => !a.hidden);
  const hidden = agents.filter(a => a.hidden);

  return (
    <div className="admin-root">
      <header className="admin-head">
        <div>
          <h1>Admin dashboard</h1>
          <span className="admin-sub">
            {agents.length} agents · {onBoard.length} on the board · {hidden.length} hidden
          </span>
        </div>
        <div className="admin-head-actions">
          <button onClick={() => setRefreshNonce(n => n + 1)} disabled={loadState === 'loading'}>
            {loadState === 'loading' ? 'Refreshing…' : 'Refresh'}
          </button>
          <button onClick={lock}>Lock</button>
        </div>
      </header>

      {error && <div className="admin-banner-err">{error}</div>}
      {loadState === 'error' ? (
        <div className="admin-empty">Couldn't reach the backend.</div>
      ) : (
        <>
          <AdminTable title="On the board" rows={onBoard} busyId={busyId} onToggle={toggle} />
          <AdminTable title="Hidden" rows={hidden} busyId={busyId} onToggle={toggle} />
        </>
      )}
    </div>
  );
}

function AdminTable({
  title, rows, busyId, onToggle,
}: {
  title: string;
  rows: AdminAgent[];
  busyId: string | null;
  onToggle: (id: string, patch: Patch) => void;
}) {
  return (
    <section className="admin-section">
      <h2>{title} · {rows.length}</h2>
      {rows.length === 0 ? (
        <div className="admin-empty">None.</div>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th className="num">Rank</th>
              <th>Agent</th>
              <th>Email</th>
              <th className="num">Total</th>
              <th className="num">P&amp;L</th>
              <th className="num">Retunes</th>
              <th className="num">Basket</th>
              <th>Created</th>
              <th>Status</th>
              <th className="admin-actions-h">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(a => {
              const busy = busyId === a.agentId;
              const up = a.plUSD >= 0;
              return (
                <tr key={a.agentId} className={a.disabled ? 'is-disabled' : ''}>
                  <td className="num">{a.rank ?? '—'}</td>
                  <td>
                    <div className="admin-name">{a.name}</div>
                    <div className="admin-handle">{a.handle ?? a.agentId}</div>
                  </td>
                  <td className="admin-email">{a.email ?? '—'}</td>
                  <td className="num">{fmtUsd(a.total)}</td>
                  <td className={`num ${up ? 'up' : 'down'}`}>
                    {up ? '+' : '−'}{fmtUsd(Math.abs(a.plUSD))} · {up ? '+' : '−'}{Math.abs(a.plPct).toFixed(2)}%
                  </td>
                  <td className="num">{a.jobsSolved}</td>
                  <td className="num">{a.basketSize}</td>
                  <td className="admin-date">{fmtDate(a.createdAt)}</td>
                  <td>
                    {a.disabled
                      ? <span className="admin-badge disabled">disabled</span>
                      : a.hidden
                        ? <span className="admin-badge hidden">hidden</span>
                        : <span className="admin-badge live">live</span>}
                  </td>
                  <td className="admin-actions">
                    {!a.hidden ? (
                      <button disabled={busy} onClick={() => onToggle(a.agentId, { hidden: true })}>Hide</button>
                    ) : (
                      <>
                        <button disabled={busy} onClick={() => onToggle(a.agentId, { hidden: false })}>Unhide</button>
                        {a.disabled ? (
                          <button disabled={busy} onClick={() => onToggle(a.agentId, { disabled: false })}>Enable</button>
                        ) : (
                          <button disabled={busy} className="danger" onClick={() => onToggle(a.agentId, { disabled: true })}>Disable</button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const read = async (url, options) => {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
};
const post = (url, body) => read(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
});
const label = value => (value || '').replaceAll('_', ' ');
const clock = iso => iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';

function App() {
  const [view, setView] = useState('queue');
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState({ conversations: 0, completed: 0, escalated: 0, open: 0, urgent: 0 });
  const [examples, setExamples] = useState([]);
  const [selected, setSelected] = useState(null);
  const [example, setExample] = useState('cv_0011');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = async () => {
    const [r, s] = await Promise.all([read('/api/conversations'), read('/api/stats')]);
    setRecords(r); setStats(s);
  };
  useEffect(() => {
    refresh().catch(e => setError(e.message));
    read('/api/examples').then(setExamples).catch(e => setError(e.message));
  }, []);

  const runExample = async () => {
    setBusy(true); setError('');
    try {
      const record = await post('/api/examples/run', { id: example });
      await refresh();
      setSelected(record.id); setView('detail');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const resolve = async id => {
    setBusy(true); setError('');
    try { await post(`/api/handoffs/${id}/resolve`, {}); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const openDetail = id => { setSelected(id); setView('detail'); };
  const record = records.find(item => item.id === selected) || records[0];
  const open = records.filter(item => item.result.terminal_state === 'escalated' && !item.resolved);

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand-mark">✚</div>
      <div className="nav-stack">
        <button title="Handoff queue" className={`nav-dot ${view === 'queue' ? 'active' : ''}`} onClick={() => setView('queue')}>◉</button>
        <button title="Conversation detail" className={`nav-dot ${view === 'detail' ? 'active' : ''}`} onClick={() => setView('detail')}>◉</button>
      </div>
      <div className="sidebar-foot">SQ</div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><div className="eyebrow">SUNRISE CLINIC · DEHRADUN</div><div className="workspace-title">Front Desk Agent</div></div>
        <div className="top-actions"><span className="live-dot" /> Local workspace <span className="top-divider" /> <span className="avatar">SQ</span></div>
      </header>
      {error && <div role="alert" className="error-banner">{error}<button onClick={() => setError('')}>×</button></div>}
      {view === 'queue' ? <>
        <div className="page-heading"><div><div className="eyebrow">OPERATIONS / HANDOFFS</div><h1>Handoff Queue</h1><p>Conversations the agent handed to your team.</p></div><span className="open-count">{stats.open} OPEN</span></div>
        <div className="stat-grid">
          <Stat title="CONVERSATIONS" value={stats.conversations} note="all runs" />
          <Stat title="COMPLETED BY AGENT" value={stats.completed} note={stats.conversations ? `${Math.round(stats.completed / stats.conversations * 100)}%` : '0%'} />
          <Stat title="ESCALATED" value={stats.escalated} note={`${stats.open} still open`} blue />
          <Stat title="URGENT" value={stats.urgent} note="clinical, unresolved" red />
        </div>
        <section className="card queue-card"><div className="card-head"><div><h2>Open handoffs</h2><span>Review each caller's request and resolve it here.</span></div><span className="small-count">{open.length} items</span></div>
          <div className="table-scroll"><table><thead><tr><th>CONVERSATION</th><th>CALLER SAID</th><th>REASON</th><th>TIME</th><th></th></tr></thead><tbody>
            {open.map(item => <tr key={item.id}><td><button className="text-link mono" onClick={() => openDetail(item.id)}>{item.result.conversation_id}</button><div className="subtle">{item.id}</div></td><td className="quote">“{item.turns.at(-1)}”</td><td><span className={`badge ${item.result.escalation_reason}`}>{label(item.result.escalation_reason)}</span></td><td className="mono subtle">{clock(item.created_at)}</td><td><button className="outline-button" disabled={busy} onClick={() => resolve(item.id)}>Resolve</button></td></tr>)}
            {!open.length && <tr><td colSpan="5" className="empty-cell">No open handoffs. Run an example to see the queue in action.</td></tr>}
          </tbody></table></div>
        </section>
        <section className="card demo-card"><div><div className="eyebrow">TRY THE AGENT</div><h2>Run a supplied conversation</h2><p>Each run starts from the original clinic schedule.</p></div><div className="demo-controls"><select aria-label="Example conversation" value={example} onChange={e => setExample(e.target.value)}>{examples.map(item => <option key={item.id} value={item.id}>{item.id} — {item.description}</option>)}</select><button className="primary-button" onClick={runExample} disabled={busy || !examples.length}>{busy ? 'Running…' : 'Run example'}</button></div></section>
      </> : <>
        <div className="page-heading"><div><button className="back-button" onClick={() => setView('queue')}>← Handoff Queue</button><div className="eyebrow">CONVERSATION / DETAIL</div><h1>{record ? `Conversation ${record.result.conversation_id}` : 'Conversation Detail'}</h1><p>Transcript, tool calls, and the machine-readable outcome.</p></div>{record && <span className={`badge large ${record.result.escalation_reason || record.result.terminal_state}`}>{record.result.terminal_state === 'escalated' ? `ESCALATED — ${label(record.result.escalation_reason)}` : label(record.result.terminal_state)}</span>}</div>
        {record ? <div className="detail-grid"><section className="card transcript"><div className="card-head"><div><h2>Transcript and tool calls</h2><span>Calls appear in the order the agent made them.</span></div><span className="mono subtle">{clock(record.created_at)}</span></div>
          <div className="events">{record.events.map((event, index) => <div className={`event event-${event.type}`} key={index}><span className="event-label">{event.type.toUpperCase()}</span><div className="event-body">{event.type === 'tool' ? <><strong>{event.name}</strong><code>{JSON.stringify(event.arguments)}</code><div className="tool-result">{event.result.error ? `Error: ${event.result.error.message}` : 'Tool returned successfully'}</div></> : event.text}</div></div>)}</div>
          {record.result.escalation_reason === 'clinical_urgent' && <div className="safety-note">Booking flow stopped. No appointment was created.</div>}
        </section><section className="card outcome"><div className="card-head"><h2>Outcome</h2></div><dl>
          <Row name="terminal_state" value={record.result.terminal_state} />
          <Row name="escalation_reason" value={record.result.escalation_reason} />
          <Row name="patient_id" value={record.result.patient_id} />
          <Row name="appointment_id" value={record.result.appointment_id} />
          <Row name="tool_calls" value={record.result.tool_calls.length} />
          <Row name="turns" value={record.result.metrics.turns} />
          <Row name="tokens" value={record.result.metrics.tokens} />
          <Row name="latency" value={`${record.result.metrics.latency_ms} ms`} />
        </dl><div className="outcome-footer"><div className="eyebrow">HANDOFF</div><div>{record.result.terminal_state === 'escalated' ? (record.resolved ? 'Resolved by staff' : 'Open for staff review') : 'No handoff needed'}</div>{record.result.terminal_state === 'escalated' && !record.resolved && <button className="outline-button" disabled={busy} onClick={() => resolve(record.id)}>Resolve handoff</button>}</div></section></div> : <div className="card empty-detail">No conversation has been run yet. <button className="text-link" onClick={() => setView('queue')}>Open the queue</button> to run an example.</div>}
      </>}
    </main>
  </div>;
}

function Stat({ title, value, note, blue, red }) { return <div className="stat card"><div className="eyebrow">{title}</div><div className="stat-number">{value}</div><div className={blue ? 'blue' : red ? 'red' : 'muted'}>{note}</div></div>; }
function Row({ name, value }) { return <div className="outcome-row"><dt>{name}</dt><dd>{value === null ? 'null' : value}</dd></div>; }

createRoot(document.getElementById('root')).render(<App />);

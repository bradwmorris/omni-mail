import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Decision = 'yes' | 'no' | 'pending' | 'unavailable';
type Filter = 'all' | 'yes' | 'no';

const filters: { value: Filter; label: string; empty: string }[] = [
  { value: 'all', label: 'All', empty: 'No inbox threads.' },
  { value: 'yes', label: 'Action', empty: 'No threads flagged for action.' },
  { value: 'no', label: 'No Action', empty: 'No threads classified as No Action.' },
];

const decisionLabels: Record<Decision, string> = {
  yes: 'Action',
  no: 'No Action',
  pending: 'Pending',
  unavailable: 'Unavailable',
};
type Row = {
  id: string;
  subject: string;
  sender: string;
  preview: string;
  timestamp: number;
  decision: Decision;
  account?: string;
};
type Inbox = {
  mode: 'sample' | 'sample-model' | 'gmail';
  account: string | null;
  account_count?: number;
  model?: string;
  models?: { id: string; label: string; available: boolean }[];
  revision?: string;
  synced: string | null;
  stage: 'idle' | 'syncing' | 'classifying';
  error: string | null;
  limit: number;
  threads: Row[];
};
type Thread = {
  id: string;
  subject: string;
  messages: { id: string; from: string; timestamp: number; body: string | null }[];
};

const shortDate = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });
const messageDate = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error ?? 'Couldn’t reach Omni Mail. Try refreshing.');
  }
  return response.json();
}

function Time({ timestamp, full = false }: { timestamp: number; full?: boolean }) {
  const date = new Date(timestamp * 1000);
  return <time dateTime={date.toISOString()}>{(full ? messageDate : shortDate).format(date)}</time>;
}

function ThreadReader({ row, revision, close }: { row: Row; revision: string | null; close: () => void }) {
  const [thread, setThread] = useState<Thread>();
  const [error, setError] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    request<Thread>('/api/threads/' + encodeURIComponent(row.id), { signal: controller.signal })
      .then(setThread)
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [row.id, revision]);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  return <>
    <header className="reader-header">
      <button type="button" className="back" onClick={close}>‹ Back to inbox</button>
      <h2 ref={heading} tabIndex={-1}>{row.subject}</h2>
      <div className="reader-meta">
        {row.account && <span className="account-name" title={row.account}>{row.account}</span>}
        <DecisionLabel decision={row.decision} />
        {thread && <span>{thread.messages.length} {thread.messages.length === 1 ? 'message' : 'messages'}</span>}
      </div>
    </header>
    {error && <p role="alert" className="notice">Couldn’t open this thread. Try refreshing.</p>}
    {!thread && !error && <p role="status" className="notice">Loading thread…</p>}
    <div className="messages">
      {thread?.messages.map(message => <article className="message" key={message.id}>
        <header>
          <strong>{message.from || 'Unknown sender'}</strong>
          <Time timestamp={message.timestamp} full />
        </header>
        <div className="message-body">{message.body ?? 'No readable text for this message. View the original in Gmail.'}</div>
      </article>)}
    </div>
  </>;
}

function DecisionLabel({ decision }: { decision: Decision }) {
  return <span className="decision" data-decision={decision}>{decisionLabels[decision]}</span>;
}

function App() {
  const [inbox, setInbox] = useState<Inbox>();
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<string>();
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const lastRow = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    request<Inbox>('/api/inbox', { signal: controller.signal }).then(setInbox)
      .catch(cause => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!inbox || inbox.stage === 'idle') return;
    const controller = new AbortController();
    let timer = window.setTimeout(poll, 700);
    async function poll() {
      try {
        const next = await request<Inbox>('/api/inbox', { signal: controller.signal });
        setError('');
        setInbox(next);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError((cause as Error).message);
        timer = window.setTimeout(poll, 1500);
      }
    }
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [inbox]);

  async function update(path: string) {
    setRefreshing(true);
    setError('');
    try {
      setInbox(await request<Inbox>(path, { method: 'POST' }));
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setRefreshing(false);
    }
  }

  const all = inbox?.threads ?? [];
  const rows = filter === 'all' ? all : all.filter(row => row.decision === filter);
  const current = rows.find(row => row.id === selected);
  const busy = refreshing || Boolean(inbox && inbox.stage !== 'idle');
  const status = inbox?.stage === 'syncing' ? 'Refreshing inbox…'
    : inbox?.stage === 'classifying' ? 'Classifying on this Mac…'
    : inbox?.synced ? 'Updated ' + messageDate.format(new Date(inbox.synced))
    : 'Waiting for inbox';
  const empty = filters.find(option => option.value === filter)?.empty;
  const source = inbox?.account ?? (inbox?.mode === 'gmail' ? 'Gmail' : 'Sample mail');

  function close() {
    setSelected(undefined);
    requestAnimationFrame(() => lastRow.current?.focus());
  }

  return <main className={current ? 'app reading' : 'app'}>
    <header className="toolbar">
      <h1 className="brand"><span aria-hidden="true">O</span>Omni Mail</h1>
      <div className="filters" role="group" aria-label="Filter inbox">
        {filters.map(option => <button
          key={option.value}
          type="button"
          aria-pressed={filter === option.value}
          onClick={() => { setFilter(option.value); setSelected(undefined); }}
        >{option.label}</button>)}
      </div>
      {inbox?.models && <select className="model-select" aria-label="Decision model"
        disabled={busy} value={inbox.model}
        onChange={event => void update('/api/model/' + encodeURIComponent(event.target.value))}>
        {inbox.models.map(model => <option key={model.id} value={model.id} disabled={!model.available}>
          {model.label}{model.available ? '' : ' (download required)'}
        </option>)}
      </select>}
      <button type="button" className="refresh" disabled={busy} onClick={() => void update('/api/refresh')}>Refresh</button>
    </header>
    {(error || inbox?.error) && <div className="alert" role="alert">{error || inbox?.error}</div>}
    <div className="workspace">
      <section className="list" aria-label="Inbox threads">
        <div className="list-meta">
          <span><strong>{rows.length}</strong> {rows.length === 1 ? 'thread' : 'threads'}</span>
          {inbox?.mode === 'gmail' && <span>Latest {inbox.limit} in Inbox{inbox.account_count && inbox.account_count > 1 ? ' per account' : ''}</span>}
        </div>
        {rows.length === 0 && <p className="notice">{!inbox || busy ? 'Loading mail…' : empty}</p>}
        <div className="rows">{rows.map(row => <button
          type="button"
          key={row.id}
          className={row.account ? "mail-row multi-account" : "mail-row"}
          aria-current={current?.id === row.id || undefined}
          onClick={event => { lastRow.current = event.currentTarget; setSelected(row.id); }}
        >
          <DecisionLabel decision={row.decision} />
          <span className="sender">{row.sender}</span>
          <strong>{row.subject}</strong>
          <span className="preview">{row.preview}</span>
          {row.account && <span className="account-name" title={row.account}>{row.account}</span>}
          <Time timestamp={row.timestamp} />
        </button>)}</div>
      </section>
      {current && <section className="reader" aria-label="Thread reader">
        <ThreadReader key={current.id} row={current} revision={inbox?.revision ?? inbox?.synced ?? null} close={close} />
      </section>}
    </div>
    <footer className="status-bar">
      <span className="source" title={source}>{source}</span>
      <span className="sync" role="status">{status}</span>
    </footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);

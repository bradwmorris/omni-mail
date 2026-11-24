import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Decision = 'yes' | 'no' | 'unprocessed' | 'unavailable';
type Filter = 'all' | 'yes' | 'no' | 'unprocessed';

const filters: { value: Filter; label: string; icon: string; empty: string }[] = [
  { value: 'all', label: 'Inbox', icon: '▤', empty: 'No inbox threads. Click Sync mail to load your inbox.' },
  { value: 'yes', label: 'Action', icon: '✓', empty: 'No threads flagged for action.' },
  { value: 'no', label: 'No Action', icon: '–', empty: 'No threads processed as No Action.' },
  { value: 'unprocessed', label: 'Unprocessed', icon: '○', empty: 'All inbox threads have been processed.' },
];

const decisionLabels: Record<Decision, string> = {
  yes: 'Action',
  no: 'No Action',
  unprocessed: 'Unprocessed',
  unavailable: 'Unavailable',
};

function matches(decision: Decision, filter: Filter) {
  return filter === 'all' || decision === filter || (filter === 'unprocessed' && decision === 'unavailable');
}

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
  jev?: { id: string; label: string; connected: boolean }[];
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
    throw new Error(data?.error ?? 'Couldn’t reach Omni Mail. Try syncing again.');
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
    {error && <p role="alert" className="notice">Couldn’t open this thread. Try syncing again.</p>}
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
  const [checked, setChecked] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [updating, setUpdating] = useState(false);
  const [jevOpen, setJevOpen] = useState(false);
  const jevDialog = useRef<HTMLDialogElement>(null);
  const [provider, setProvider] = useState('openrouter');
  const [jevKey, setJevKey] = useState('');
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

  async function update(path: string, body?: object) {
    setUpdating(true);
    setError('');
    const payload = body === undefined
      ? undefined : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    try {
      setInbox(await request<Inbox>(path, { method: 'POST', ...payload }));
      setChecked([]);
      return true;
    } catch (cause) {
      setError((cause as Error).message);
      return false;
    } finally {
      setUpdating(false);
    }
  }

  const all = inbox?.threads ?? [];
  const rows = all.filter(row => matches(row.decision, filter));
  const current = all.find(row => row.id === selected);
  const busy = updating || Boolean(inbox && inbox.stage !== 'idle');
  const activeJev = inbox?.jev?.find(option => inbox.model === 'jev-' + option.id);
  const selectedProvider = inbox?.jev?.find(option => option.id === provider);
  const status = inbox?.stage === 'syncing' ? 'Syncing mail…'
    : inbox?.stage === 'classifying' ? (activeJev ? `Processing via ${activeJev.label}…` : 'Processing on this Mac…')
    : inbox?.synced ? 'Synced ' + messageDate.format(new Date(inbox.synced))
    : 'Ready to sync';
  const empty = filters.find(option => option.value === filter)?.empty;
  const source = inbox?.account ?? (inbox?.mode === 'gmail' ? 'Gmail' : inbox?.mode === 'sample' ? 'Sample mail · preset decisions' : 'Sample mail');
  const remaining = all.filter(row => matches(row.decision, 'unprocessed')).length;
  const processCount = checked.length || remaining;

  function showJevSettings() {
    setError('');
    setJevKey('');
    setJevOpen(true);
    jevDialog.current?.showModal();
  }

  function selectJev() {
    const savedProvider = selectedProvider?.connected ? selectedProvider : inbox?.jev?.find(option => option.connected);
    if (!savedProvider) {
      showJevSettings();
      return;
    }
    void update('/api/model/jev-' + savedProvider.id);
  }

  async function saveJevKey() {
    const key = jevKey.trim();
    setJevKey('');
    if (await update('/api/jev', { provider, key })) jevDialog.current?.close();
  }

  function close() {
    setSelected(undefined);
    requestAnimationFrame(() => lastRow.current?.focus());
  }

  return <div className={current ? 'app reading' : 'app'}>
    <aside className="sidebar">
      <h1 className="brand"><span aria-hidden="true">O</span>Omni Mail</h1>
      <nav className="filters" aria-label="Inbox views">
        {filters.map(option => <button
          key={option.value}
          type="button"
          aria-current={filter === option.value ? 'page' : undefined}
          onClick={() => { setFilter(option.value); setSelected(undefined); setChecked([]); }}
        >
          <span className="view-icon" aria-hidden="true">{option.icon}</span>
          <span>{option.label}</span>
          <span className="view-count">{all.filter(row => matches(row.decision, option.value)).length}</span>
        </button>)}
      </nav>
      {inbox?.jev && <button type="button" className="settings-cog" aria-label="Settings"
        title="Settings" aria-haspopup="dialog" onClick={showJevSettings}>⚙</button>}
    </aside>
    <main className="content">
    <header className="toolbar">
      <button type="button" className="sync-button" disabled={busy} onClick={() => void update('/api/sync')}>
        <span aria-hidden="true">↻</span> Sync mail
      </button>
      {inbox?.models && <select className="model-select" aria-label="Decision model"
        disabled={busy} value={inbox.model}
        onChange={event => {
          if (event.target.value.startsWith('jev-')) setProvider(event.target.value.slice(4));
          void update('/api/model/' + encodeURIComponent(event.target.value));
        }}>
        {inbox.models.map(model => <option key={model.id} value={model.id} disabled={!model.available}>
          {model.label}{model.available ? '' : ' (download required)'}
        </option>)}
      </select>}
      {inbox?.jev && <button type="button" className="jev-button" disabled={busy}
        aria-current={activeJev ? 'true' : undefined} onClick={selectJev}>
        <img src="/assets/typesafe-mark.png" alt="" width="16" height="16" /> JEV
      </button>}
      <button type="button" className="process-button" disabled={busy || !processCount}
        onClick={() => void update('/api/process', { thread_ids: checked.length ? checked : null })}>
        <span aria-hidden="true">ϟ</span> Process {checked.length ? 'selected' : 'remaining'}{processCount > 0 ? ` (${processCount})` : ''}
      </button>
    </header>
    {inbox?.jev && <dialog className="settings-dialog" ref={jevDialog} aria-labelledby="jev-settings-title"
      onClose={() => { setJevKey(''); setError(''); setJevOpen(false); }}>
      <form className="jev-settings" onSubmit={event => {
        event.preventDefault();
        void saveJevKey();
      }}>
        <h2 id="jev-settings-title">Settings</h2>
        <label>
          Provider
          <select value={provider} disabled={busy}
            onChange={event => { setProvider(event.target.value); setJevKey(''); setError(''); }}>
            {inbox.jev.map(option => <option key={option.id} value={option.id}>
              {option.label}{option.connected ? ' · key saved' : ''}
            </option>)}
          </select>
        </label>
        <label>
          API key
          <input type="password" value={jevKey} onChange={event => setJevKey(event.target.value)}
            autoComplete="off" spellCheck={false} maxLength={512} disabled={busy}
            placeholder={selectedProvider?.connected ? 'Enter to replace saved key' : 'Paste an API key'}
            required />
        </label>
        <p>Processing with JEV sends the selected message text to {selectedProvider?.label}. Provider charges may apply.</p>
        {jevOpen && error && <p className="settings-error" role="alert">{error}</p>}
        <div className="settings-actions">
          <button type="button" className="jev-button" onClick={() => jevDialog.current?.close()}>Close</button>
          <button type="submit" className="process-button" disabled={busy || !jevKey.trim()}>Save key</button>
        </div>
      </form>
    </dialog>}
    {(!jevOpen && (error || inbox?.error)) && <div className="alert" role="alert">{error || inbox?.error}</div>}
    <div className="workspace">
      <section className="list" aria-label="Inbox threads">
        <div className="list-meta">
          <span><strong>{rows.length}</strong> {rows.length === 1 ? 'thread' : 'threads'}</span>
          {inbox?.mode === 'gmail' && <span>Latest {inbox.limit} in Inbox{inbox.account_count && inbox.account_count > 1 ? ' per account' : ''}</span>}
        </div>
        {rows.length === 0 && <p className="notice">{!inbox || inbox.stage === 'syncing' ? 'Loading mail…' : empty}</p>}
        <div className="rows">{rows.map(row => <div className="mail-entry" key={row.id} data-checked={checked.includes(row.id)}>
          <input
            type="checkbox"
            className="row-check"
            aria-label={`Select ${row.subject}`}
            checked={checked.includes(row.id)}
            disabled={busy}
            onChange={event => {
              const selected = event.target.checked;
              setChecked(items => selected ? [...items, row.id] : items.filter(id => id !== row.id));
            }}
          />
          <button
          type="button"
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
          </button></div>)}</div>
      </section>
      {current && <section className="reader" aria-label="Thread reader">
        <ThreadReader key={current.id} row={current} revision={inbox?.revision ?? inbox?.synced ?? null} close={close} />
      </section>}
    </div>
    <footer className="status-bar">
      <span className="source" title={source}>{source}
        {activeJev && <span title="Processing sends email text to this provider."> · JEV via {activeJev.label}</span>}
      </span>
      <span className="sync" role="status">{status}</span>
    </footer>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);

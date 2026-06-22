// A neutral loading / not-found / error panel for a surface that can't render
// its content yet. Colors inherit from the `tone` so it works inside both the
// dark phone frame and the light kiosk stage. Replaces the old silent `return
// null` blanks.

type Action = { label: string; onClick?: () => void; href?: string };

type Props = {
  tone: 'dark' | 'light';
  title: string;
  message?: string;
  action?: Action;
  busy?: boolean;
};

export default function StatusScreen({ tone, title, message, action, busy }: Props) {
  return (
    <div className={`surface-status ${tone}`} role={busy ? 'status' : 'alert'} aria-busy={busy || undefined}>
      <div className="surface-status-eyebrow">Quip Network</div>
      <div className="surface-status-title">{title}</div>
      {message && <p className="surface-status-msg">{message}</p>}
      {action && (action.href
        ? <a className="surface-status-action" href={action.href}>{action.label}</a>
        : <button type="button" className="surface-status-action" onClick={action.onClick}>{action.label}</button>
      )}
    </div>
  );
}

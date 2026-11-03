import { TriangleAlert, Info, Lock, LoaderCircle, X } from 'lucide-react';
import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { useClickOutside } from '../../lib/hooks';

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ');
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

export function Button({ variant = 'secondary', size = 'md', icon, children, className, loading, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md'; icon?: ReactNode; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:opacity-50',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-9 px-3.5 text-sm',
        variant === 'primary' && 'bg-navy text-white hover:bg-[#16335c] dark:bg-accent dark:hover:bg-[#3a7fd6]',
        variant === 'secondary' && 'border border-line-strong bg-panel text-ink hover:bg-panel-2',
        variant === 'ghost' && 'text-ink-2 hover:bg-panel-2 hover:text-ink',
        variant === 'danger' && 'border border-line-strong bg-panel text-bad hover:bg-bad-soft',
        className,
      )}
    >
      {loading ? <LoaderCircle size={15} className="animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function IconButton({ label, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button {...rest} aria-label={label} title={label}
      className={cx('inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-2 hover:bg-panel-2 hover:text-ink', className)}>
      {children}
    </button>
  );
}

export function Panel({ title, subtitle, actions, children, className, bodyClass, loading, id }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
  bodyClass?: string; loading?: boolean; id?: string;
}) {
  return (
    <section id={id} className={cx('min-w-0 rounded-xl border border-line bg-panel', loading && 'loading-bar', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold leading-snug text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={cx('px-5 pb-5 pt-3', bodyClass)}>{children}</div>
    </section>
  );
}

const BADGE: Record<string, string> = {
  critical: 'bg-bad-soft text-bad',
  warning: 'bg-warn-soft text-warn',
  positive: 'bg-good-soft text-good',
  good: 'bg-good-soft text-good',
  info: 'bg-accent-soft text-accent-ink',
  neutral: 'bg-panel-2 text-ink-2 border border-line',
};

export function Badge({ tone = 'neutral', children, icon, className }: { tone?: keyof typeof BADGE | string; children: ReactNode; icon?: ReactNode; className?: string }) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium whitespace-nowrap', BADGE[tone] ?? BADGE.neutral, className)}>
      {icon}{children}
    </span>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = 'sm', label }: {
  value: T; options: { value: T; label: string; disabled?: boolean }[]; onChange: (v: T) => void; size?: 'sm' | 'md'; label?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-panel-2 p-0.5">
      {options.map((o) => (
        <button key={o.value} role="radio" aria-checked={value === o.value} disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cx('rounded-[5px] font-medium transition-colors disabled:opacity-40',
            size === 'sm' ? 'h-6 px-2 text-xs' : 'h-8 px-3 text-sm',
            value === o.value ? 'bg-panel text-ink shadow-[0_0_0_1px_var(--line-strong)]' : 'text-ink-2 hover:text-ink')}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, label, className }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; label: string; className?: string;
}) {
  return (
    <label className={cx('inline-flex items-center gap-2 text-xs text-ink-2', className)}>
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}
        className="h-7 rounded-md border border-line-strong bg-panel px-2 text-xs text-ink">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('animate-pulse rounded-md bg-panel-2', className)} />;
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      {icon && <div className="mb-3 text-ink-3">{icon}</div>}
      <p className="text-sm font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** A metric the dataset cannot support. States what is missing instead of showing invented numbers. */
export function NotSupported({ title, reason, requires, onMap }: { title: string; reason: string; requires?: string[]; onMap?: () => void }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col justify-center rounded-lg border border-dashed border-line-strong bg-panel-2 px-5 py-6">
      <div className="flex items-center gap-2 text-sm font-semibold text-ink"><Lock size={15} className="text-ink-3" />{title}</div>
      <p className="mt-1.5 max-w-prose text-sm text-ink-2">{reason}</p>
      {requires && requires.length > 0 && (
        <p className="mt-2 text-xs text-ink-3">Needs: {requires.map((r) => r.replace(/_/g, ' ')).join(', ')}</p>
      )}
      {onMap && <div className="mt-3"><Button size="sm" onClick={onMap}>Review column mapping</Button></div>}
    </div>
  );
}

export function Callout({ tone = 'info', children, title }: { tone?: 'info' | 'warning' | 'critical'; children: ReactNode; title?: string }) {
  const Icon = tone === 'info' ? Info : TriangleAlert;
  return (
    <div className={cx('flex gap-3 rounded-lg border px-4 py-3 text-sm',
      tone === 'info' && 'border-line bg-accent-soft/60 text-ink',
      tone === 'warning' && 'border-warn/30 bg-warn-soft text-ink',
      tone === 'critical' && 'border-bad/30 bg-bad-soft text-ink')}>
      <Icon size={17} className={cx('mt-0.5 shrink-0', tone === 'info' ? 'text-accent' : tone === 'warning' ? 'text-warn' : 'text-bad')} />
      <div>{title && <p className="font-semibold">{title}</p>}<div className="text-ink-2">{children}</div></div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children, width = 520 }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, onClose, open);
  useEffect(() => { if (open) ref.current?.focus(); }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-[rgba(7,14,28,0.35)]">
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Details'}
        style={{ width: `min(${width}px, 100vw)` }}
        className="absolute right-0 top-0 flex h-full flex-col border-l border-line bg-panel shadow-pop outline-none">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="text-md font-semibold">{title}</h2>
          <IconButton label="Close" onClick={onClose}><X size={18} /></IconButton>
        </div>
        <div className="scroll-thin flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'good' | 'bad' }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-ink-2">{label}</p>
      <p className={cx('mt-1 text-xl font-semibold tracking-tight', tone === 'good' && 'text-good', tone === 'bad' && 'text-bad')}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-bad/30 bg-bad-soft px-4 py-3 text-sm">
      <span className="text-ink">{error.message}</span>
      {onRetry && <Button size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

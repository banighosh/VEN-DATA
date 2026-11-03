import { CircleCheck, Database, Info, X, CircleX } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import { FilterBar, Sidebar, Topbar } from './components/layout/Shell';
import { Button, cx, EmptyState, Skeleton } from './components/ui/primitives';
import { navigate, useRoute, type Page } from './lib/hooks';
import { useApp } from './state/AppState';
import Dashboard from './pages/Dashboard';

const pages: Record<Page, React.LazyExoticComponent<() => React.JSX.Element> | (() => React.JSX.Element)> = {
  dashboard: Dashboard,
  executive: lazy(() => import('./pages/Executive')),
  performance: lazy(() => import('./pages/Performance')),
  financial: lazy(() => import('./pages/Financial')),
  customers: lazy(() => import('./pages/Customers')),
  products: lazy(() => import('./pages/Products')),
  regional: lazy(() => import('./pages/Regional')),
  operations: lazy(() => import('./pages/Operations')),
  insights: lazy(() => import('./pages/Insights')),
  explorer: lazy(() => import('./pages/Explorer')),
  data: lazy(() => import('./pages/DataManagement')),
  settings: lazy(() => import('./pages/Settings')),
};

const NO_FILTER_BAR: Page[] = ['data', 'settings'];

function Toasts() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const Icon = t.kind === 'success' ? CircleCheck : t.kind === 'error' ? CircleX : Info;
        return (
          <div key={t.id} className="pointer-events-auto flex items-start gap-2.5 rounded-lg border border-line bg-panel px-3.5 py-3 text-sm shadow-pop">
            <Icon size={17} className={cx('mt-0.5 shrink-0', t.kind === 'success' ? 'text-good' : t.kind === 'error' ? 'text-bad' : 'text-accent')} />
            <span className="flex-1">{t.message}</span>
            <button onClick={() => dismissToast(t.id)} aria-label="Dismiss" className="text-ink-3 hover:text-ink"><X size={15} /></button>
          </div>
        );
      })}
    </div>
  );
}

function Welcome() {
  return (
    <div className="mx-auto max-w-xl pt-16">
      <EmptyState icon={<Database size={36} />} title="Start by uploading your sales data"
        action={<Button variant="primary" onClick={() => navigate('data')}>Upload a file</Button>}>
        Upload an Excel workbook or CSV. You will preview it, review a data quality report and map its columns to business fields
        before anything is calculated.
      </EmptyState>
    </div>
  );
}

export default function App() {
  const page = useRoute();
  const { dataset, datasetsLoaded } = useApp();
  const [menu, setMenu] = useState(false);
  const Current = pages[page];
  const needsData = !NO_FILTER_BAR.includes(page);
  return (
    <div className="flex h-full">
      <a href="#main-scroll" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[70] focus:rounded focus:bg-panel focus:px-3 focus:py-2">Skip to content</a>
      <Sidebar page={page} open={menu} onClose={() => setMenu(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenu={() => setMenu(true)} />
        {needsData && dataset && <FilterBar />}
        <main id="main-scroll" className="scroll-thin min-w-0 flex-1 overflow-y-auto px-4 pb-12 pt-6 lg:px-6">
          {!datasetsLoaded ? (
            <div className="space-y-4"><Skeleton className="h-8 w-64" /><Skeleton className="h-40 w-full" /><Skeleton className="h-72 w-full" /></div>
          ) : needsData && !dataset ? <Welcome /> : (
            <Suspense fallback={<div className="space-y-4"><Skeleton className="h-8 w-64" /><Skeleton className="h-72 w-full" /></div>}>
              <Current />
            </Suspense>
          )}
        </main>
      </div>
      <Toasts />
    </div>
  );
}

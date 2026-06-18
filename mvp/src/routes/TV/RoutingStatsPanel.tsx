import type { RoutingProviderStat, RoutingStats } from '../../api';

type Props = {
  stats: RoutingStats;
  showProviders?: boolean;
};

const PROVIDER_LABELS: Record<string, string> = {
  dwave: 'D-Wave Advantage',
  sa: 'Simulated Annealing',
  gurobi: 'Gurobi',
};

export default function RoutingStatsPanel({ stats, showProviders = false }: Props) {
  const qpuPct = Math.round(stats.qpuPct);
  const cpuPct = Math.round(stats.cpuPct);
  const qpuWidth = stats.total > 0 ? stats.qpuPct : 0;
  const cpuWidth = stats.total > 0 ? stats.cpuPct : 0;

  return (
    <>
      <div className="v4-section">
        <div className="v3-panel-head">
          <span className="v3-panel-eyebrow">Solve winners</span>
          <span className="v3-panel-hero">Quantum <span className="accent">vs</span> classical.</span>
        </div>
        <div className="v3-panel-body">
          <div className="v3-qc">
            <div className="num-row">
              <span className="num-q">{qpuPct}<span className="pct">%</span></span>
              <span className="num-c">{cpuPct}<span className="pct">%</span></span>
            </div>
            <div className="names">
              <span className="n-q">Quantum (QPU)</span>
              <span className="n-c">Classical (CPU)</span>
            </div>
            <div className="ms-bar">
              <span className="q" style={{ width: `${qpuWidth}%` }}></span>
              <span className="c" style={{ width: `${cpuWidth}%` }}></span>
            </div>
          </div>
        </div>
      </div>

      {showProviders && (
        <div className="v4-section">
          <div className="v3-panel-head">
            <span className="v3-panel-eyebrow">Top providers</span>
            <span className="v3-panel-hero">Top Providers</span>
          </div>
          <div className="v3-panel-body">
            <div className="v4-plist">
              <div className="v4-stack">
                {stats.providers.map((provider, index) => (
                  <span
                    key={`${provider.provider}-${provider.providerType}`}
                    className={segmentClass(provider, index)}
                    style={{ width: `${provider.pct}%` }}
                  ></span>
                ))}
              </div>
              {stats.providers.length > 0 ? (
                stats.providers.map((provider) => (
                  <div
                    className={`v4-pr ${provider.providerType === 'QPU' ? 'q' : 'c'}`}
                    key={`${provider.provider}-${provider.providerType}`}
                  >
                    <span className="type">{provider.providerType}</span>
                    <span className="nm">{providerLabel(provider.provider)}</span>
                    <span className="pct">{Math.round(provider.pct)}%</span>
                  </div>
                ))
              ) : (
                <div className="v4-pr c">
                  <span className="type">CPU</span>
                  <span className="nm">Waiting for first solve</span>
                  <span className="pct">0%</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function segmentClass(provider: RoutingProviderStat, index: number): string {
  if (provider.providerType === 'QPU') return 'seg q';
  return `seg c${Math.min(index + 1, 8)}`;
}

function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

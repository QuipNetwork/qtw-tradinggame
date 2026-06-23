import { REBALANCE_TIERS, rebalanceTierIndex, rebalanceTierValue } from '../utils/strategy';

// The Rebalance cadence control: a thin heat-bar slider that matches the other
// strategy sliders — gray at low cadence warming to app-cyan at high cadence,
// with a detached "Off" dot in the left whitespace. Each tier node sits in a
// round white cutout on the bar. Shared by the kiosk sign-up and the phone
// retune panel — both pass a 0–100 value (sliders[0]) and get back the snapped
// 0–100 value on change.
//
// Per-tier x position in % of the bar; `Off` is detached in the left whitespace,
// the ladder 12h→30m runs START→100.
const START = 18;
const TIER_VIS: Array<{ x: number; color: string; lone?: boolean }> = [
  { x: 4,    color: '#a1a1aa', lone: true }, // Off  (detached lone dot)
  { x: 18,   color: '#a1a1aa' },             // 12h
  { x: 34.4, color: '#a1a1aa' },             // 8h
  { x: 50.8, color: '#9bbcc4' },             // 4h  (gray→cyan transition)
  { x: 67.2, color: '#5cc3d6' },             // 2h
  { x: 83.6, color: '#22d3ee' },             // 1h
  { x: 100,  color: '#4BE0FF' },             // 30m (full app-cyan)
];
const HOT_FROM = 5;                          // 1h and 30m read as "high cadence" → glow

export default function RebalanceSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  const idx = rebalanceTierIndex(value);
  const last = REBALANCE_TIERS.length - 1;
  const tier = TIER_VIS[idx];
  const hot = idx >= HOT_FROM;
  // fill reveals from START up to the selected node; Off (x < START) reveals none.
  const reveal = Math.max(0, (tier.x - START) / (100 - START)) * 100;

  const label = REBALANCE_TIERS[idx].label;
  const valText = idx === 0 ? 'Off' : `Every ${label}`;

  return (
    <div className="rbx">
      <span className="rbx-label">Rebalance</span>
      <div className="rbx-body">
        <div className="rbx-well">
          <div className="rbx-bar">
            <div className="rbx-track" style={{ left: `${START}%` }}></div>
            <div
              className="rbx-fill"
              style={{ left: `${START}%`, clipPath: `inset(0 ${100 - reveal}% 0 0 round 999px)` }}
            ></div>
            <div
              className="rbx-glow"
              style={{ left: `${tier.x}%`, color: tier.color, opacity: hot ? 0.85 : 0 }}
            ></div>
            {TIER_VIS.map((t, i) => (
              <div
                key={i}
                className={`rbx-node${t.lone ? ' lone' : ''}${i === idx ? ' sel' : ''}`}
                style={{ left: `${t.x}%`, background: i <= idx ? t.color : '#cfcfd6', color: t.color }}
              ></div>
            ))}
            <input
              type="range"
              className="rbx-range"
              min={0}
              max={last}
              step={1}
              value={idx}
              aria-label="Rebalance frequency"
              aria-valuetext={valText}
              onChange={(e) => onChange(rebalanceTierValue(parseInt(e.target.value, 10)))}
            />
          </div>
        </div>

        <div className="rbx-labels">
          {TIER_VIS.map((t, i) => (
            <span
              key={i}
              className={`rbx-lab${i === idx ? ' sel' : ''}`}
              style={{ left: `${t.x}%`, color: i === idx ? t.color : undefined }}
              onClick={() => onChange(rebalanceTierValue(i))}
            >
              {REBALANCE_TIERS[i].label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

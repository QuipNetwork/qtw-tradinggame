// Three jargon-free steps. No QUBO / slider-name / encoding talk — this is the
// public explainer, not the internal directory.
const STEPS = [
  {
    n: '01',
    glyph: '◑',
    tint: 'var(--coral-soft)',
    title: 'Pick your assets',
    body: 'A watchlist from the 28-asset universe — stocks, crypto, and quantum names.',
  },
  {
    n: '02',
    glyph: '◴',
    tint: '#FFF8DC',
    title: 'Set three dials',
    body: 'Risk, max position size, and how many names to hold.',
  },
  {
    n: '03',
    glyph: '⚛',
    tint: 'var(--cyan-soft)',
    title: 'Race the solvers',
    body: 'Quantum and classical solvers compete each rebalance. Follow the result on your phone.',
  },
];

export default function HowItWorks() {
  return (
    <section id="how" className="qpub-section qpub-how" data-reveal>
      <span className="qpub-eyebrow">How it works</span>
      <div className="qpub-steps">
        {STEPS.map(s => (
          <article className="qpub-step" key={s.n}>
            <span className="qpub-step-ic" style={{ background: s.tint }} aria-hidden>{s.glyph}</span>
            <span className="qpub-step-n">Step {s.n}</span>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

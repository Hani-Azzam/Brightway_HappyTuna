import { useEffect } from 'react';

interface Item {
  title: string;
  body: string;
  formula?: string;
}

interface Section {
  heading: string;
  items: Item[];
}

function buildSections(company: string): Section[] {
  return [
    {
      heading: 'How analysis works',
      items: [
        {
          title: 'On-demand, not automatic',
          body: 'Posts are scored only when “Run analysis” is pressed. Each post receives a sentiment score from −1 to +1, a label (positive / neutral / negative), the product aspects it addresses, and whether it mentions the company. Results are cached on each post, and every panel reads from that cache.',
        },
        {
          title: 'Two engines (the AI toggle)',
          body: 'With the toggle off, a deterministic keyword lexicon scores posts — fast and reproducible. With it on (and an API key configured), Claude scores them, handling context and sarcasm. The engine pill shows which is active; both produce results of the same form, so every metric is identical in definition.',
        },
      ],
    },
    {
      heading: 'Headline KPIs',
      items: [
        {
          title: 'Opinion Index',
          body: `The headline measure of overall sentiment toward ${company}, on a −100 to +100 scale (−100 uniformly negative, +100 uniformly positive). The toggle switches between the raw index and the influence-weighted index.`,
          formula: 'OpinionIndex = 100 × mean(sentiment of company posts)',
        },
        {
          title: 'Influence-weighted Opinion Index',
          body: 'The same measure with each post weighted by its author’s account-type weight and by how widely it was amplified (likes and reposts). It reflects the sentiment that is actually reaching an audience.',
          formula: 'w = typeBoost(author) × (1 + ln(1 + likes + reposts));  index = 100 × Σ(w · sentiment) / Σ w',
        },
        {
          title: 'Crisis Meter',
          body: 'An early-warning gauge combining the share of recent posts that are negative with the rate at which posting volume is rising. Bands: 0–30 Calm, 30–60 Watch, 60–80 Elevated, 80–100 Crisis.',
          formula: 'Crisis = clamp(negativeShare × (1 + volumeVelocity), 0, 1) × 100   (velocity capped at 1)',
        },
        {
          title: 'Share of Voice',
          body: `The proportion of analysed posts that mention ${company}, as opposed to off-topic activity.`,
          formula: 'SoV = company posts / all analysed posts',
        },
        {
          title: 'Sentiment mix',
          body: 'The distribution of company posts across positive, neutral and negative — the spread that underlies the average.',
        },
      ],
    },
    {
      heading: 'Trends over time',
      items: [
        {
          title: 'Opinion over time',
          body: 'The Opinion Index recalculated for each time bucket, over posts that mention the company, showing how sentiment moves through a period.',
        },
        {
          title: 'Aspect sentiment',
          body: 'Mean sentiment across the six product aspects — sustainability, health, price, taste, ethics and safety — with the number of posts addressing each. It identifies which issue is driving sentiment rather than only that sentiment moved.',
        },
      ],
    },
    {
      heading: 'Narrative shapers',
      items: [
        {
          title: 'Who is shaping opinion (cohorts)',
          body: 'Company sentiment grouped by author type — journalists, influencers and the public, each shown separately. The gap compares the shapers (journalists and influencers) with the public; a wide gap indicates the accounts with reach diverge from the broader public. The official company account is reported separately and excluded from both groups, as it represents company communications rather than independent opinion.',
          formula: 'gap = OpinionIndex(journalists + influencers) − OpinionIndex(public)',
        },
        {
          title: 'Narrative origins',
          body: 'For each hashtag, the account that posted it first (the originator) and whether the origin was a shaper, the official company account, or the grassroots public. The coloured bar shows how the posts distribute across author types — the topic’s propagation footprint.',
        },
      ],
    },
    {
      heading: 'Topics, influence and events',
      items: [
        {
          title: 'Trending topics',
          body: 'The most-used hashtags in the current window, each with a rising multiplier and the mean sentiment of its posts.',
          formula: 'rising = count(current window) / (count(previous window) + 1)',
        },
        {
          title: 'Top influencers',
          body: 'Accounts ranked by reach, each with their stance — the account’s own mean sentiment toward the company. A high-reach account turning negative is a leading indicator.',
          formula: 'influence = ln(1 + followers) + 0.5 · ln(1 + reposts received) + typeBoost(account)',
        },
        {
          title: 'Detected events (spikes)',
          body: 'Company events are not announced to the platform, so they are inferred: any time bucket whose posting volume is well above the norm is flagged as a detected event, with its z-score and the sentiment recorded during it.',
          formula: 'z = (volume − mean) / stdDev;  flagged when z ≥ k (≈ 2)',
        },
        {
          title: 'Top posts',
          body: 'The most-engaged posts, ranked by likes + reposts + replies.',
        },
      ],
    },
  ];
}

export function HelpModal({ company, onClose }: { company: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const sections = buildSections(company);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="help-modal" role="dialog" aria-modal="true" aria-label="Dashboard help" onClick={(e) => e.stopPropagation()}>
        <header className="help-head">
          <div>
            <h2>Help — how this dashboard works</h2>
            <p>Every metric in plain language. Full formulas live in <code>docs/analytics-methodology.md</code>.</p>
          </div>
          <button className="help-close" onClick={onClose} aria-label="Close help">
            ✕
          </button>
        </header>

        <div className="help-body">
          <div className="help-grid">
            {sections.map((section) => (
              <section key={section.heading} className="help-section">
                <h3>{section.heading}</h3>
                {section.items.map((item) => (
                  <div className="help-item" key={item.title}>
                    <div className="help-item-title">{item.title}</div>
                    <p>{item.body}</p>
                    {item.formula && <code className="help-formula">{item.formula}</code>}
                  </div>
                ))}
              </section>
            ))}
          </div>
          <footer className="help-credit">Made by the Hanzo, Kareen and Seren Team</footer>
        </div>
      </div>
    </div>
  );
}

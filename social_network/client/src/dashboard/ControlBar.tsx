import type { AnalysisConfig } from '../types';

export function ControlBar({
  config,
  analyzing,
  onToggleAi,
  onRunAnalysis,
}: {
  config: AnalysisConfig;
  analyzing: boolean;
  onToggleAi: () => void;
  onRunAnalysis: () => void;
}) {
  const pending = config.totalPosts - config.analyzedPosts;
  return (
    <div className="control">
      <div className="coverage">
        Analyzed <b>{config.analyzedPosts}</b> / <b>{config.totalPosts}</b> posts
      </div>
      <span className={`engine-pill ${config.activeEngine}`}>{config.activeEngine}</span>
      {pending > 0 && <span className="hint">· {pending} not yet analyzed</span>}

      <div className="spacer" />

      <button
        className={`switch ${config.aiAnalysisEnabled ? 'on' : ''}`}
        onClick={onToggleAi}
        aria-pressed={config.aiAnalysisEnabled}
        title="Use Claude for sentiment analysis"
      >
        <span className="track">
          <span className="knob" />
        </span>
        AI sentiment
      </button>
      {config.aiAnalysisEnabled && !config.hasApiKey && <span className="hint">no API key — using lexicon</span>}

      <button className="btn-primary" onClick={onRunAnalysis} disabled={analyzing}>
        {analyzing ? 'Analyzing…' : 'Run analysis'}
      </button>
    </div>
  );
}

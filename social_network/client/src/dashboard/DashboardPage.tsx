import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useMeta } from '../meta/MetaContext';
import type {
  AnalysisConfig,
  AspectStat,
  CohortReport,
  Influencer,
  Narrative,
  Overview,
  Spike,
  TimelineBucket,
  TopPost,
  TrendStat,
} from '../types';
import { ControlBar } from './ControlBar';
import { Kpis } from './Kpis';
import { TimelineChart } from './TimelineChart';
import { AspectChart } from './AspectChart';
import { CohortPanel } from './CohortPanel';
import { NarrativePanel } from './NarrativePanel';
import { HelpModal } from './HelpModal';
import { TrendsTable, InfluencerTable, SpikeList, TopPostsList } from './Tables';

export function DashboardPage() {
  const { platformName, companyName } = useMeta();
  const [config, setConfig] = useState<AnalysisConfig | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [timeline, setTimeline] = useState<TimelineBucket[]>([]);
  const [aspects, setAspects] = useState<AspectStat[]>([]);
  const [trends, setTrends] = useState<TrendStat[]>([]);
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [spikes, setSpikes] = useState<Spike[]>([]);
  const [topPosts, setTopPosts] = useState<TopPost[]>([]);
  const [cohorts, setCohorts] = useState<CohortReport | null>(null);
  const [narratives, setNarratives] = useState<Narrative[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const refreshMetrics = useCallback(async () => {
    const [ov, tl, asp, tr, inf, sp, tp, co, na, cfg] = await Promise.all([
      api.getOverview(),
      api.getTimeline(),
      api.getAspects(),
      api.getAnalyticsTrends(),
      api.getInfluencers(),
      api.getSpikes(),
      api.getTopAnalyticsPosts(),
      api.getCohorts(),
      api.getNarratives(),
      api.getAnalyticsConfig(),
    ]);
    setOverview(ov);
    setTimeline(tl);
    setAspects(asp);
    setTrends(tr);
    setInfluencers(inf);
    setSpikes(sp);
    setTopPosts(tp);
    setCohorts(co);
    setNarratives(na);
    setConfig(cfg);
  }, []);

  useEffect(() => {
    refreshMetrics().catch(() => undefined);
  }, [refreshMetrics]);

  const toggleAi = useCallback(async () => {
    if (!config) return;
    const next = await api.setAnalyticsConfig(!config.aiAnalysisEnabled);
    setConfig(next);
  }, [config]);

  const runAnalysis = useCallback(async () => {
    setAnalyzing(true);
    try {
      await api.runAnalysis(true);
      await refreshMetrics();
    } finally {
      setAnalyzing(false);
    }
  }, [refreshMetrics]);

  return (
    <div className="dash">
      <header className="dash-head">
        <div className="bar">
          <div className="title">
            🐟 {platformName} · Research
            <small>Public opinion about {companyName}</small>
          </div>
          <div className="spacer" />
          <button className="help-btn" onClick={() => setHelpOpen(true)}>
            <span className="help-q">?</span> Help
          </button>
          <Link className="back-link" to="/">
            ← Back to feed
          </Link>
        </div>
      </header>

      <div className="dash-body">
        {config && config.analyzedPosts === 0 && (
          <div className="dash-banner">
            <span>No posts analyzed yet — run the analysis to populate these metrics.</span>
            <button className="btn-primary" onClick={runAnalysis} disabled={analyzing}>
              {analyzing ? 'Analyzing…' : 'Run analysis'}
            </button>
          </div>
        )}

        {config && <ControlBar config={config} analyzing={analyzing} onToggleAi={toggleAi} onRunAnalysis={runAnalysis} />}

        {overview ? <Kpis overview={overview} /> : <div className="dempty">Loading…</div>}

        <div className="charts-2">
          <TimelineChart data={timeline} />
          <AspectChart data={aspects} />
        </div>

        <div className="section-label">Narrative shapers</div>
        <div className="tables-2">
          <CohortPanel data={cohorts} />
          <NarrativePanel data={narratives} />
        </div>

        <div className="tables-2">
          <TrendsTable data={trends} />
          <InfluencerTable data={influencers} />
        </div>

        <div className="tables-2">
          <SpikeList data={spikes} />
          <TopPostsList data={topPosts} />
        </div>
      </div>

      {helpOpen && <HelpModal company={companyName} onClose={() => setHelpOpen(false)} />}
    </div>
  );
}

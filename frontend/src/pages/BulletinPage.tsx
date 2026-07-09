import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Newspaper, Clock, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Download, ExternalLink, Sparkles, Search, X } from 'lucide-react';
import { ensureOk, getBackendBaseUrl, normalizeUnknownError } from '../api/client';
import { createTelegramLinkToken, fetchTelegramStatus, unlinkTelegram, type TelegramStatus } from '../api/telegram';
import { clearStoredUser, getAuthHeaders } from '../lib/auth';
import { categoryLabel } from '../lib/categoryLabels';
import { getImageForTopic } from '../lib/topicImages';
import type { Cluster, Digest, Paper } from '../lib/types';
import { EmptyState, LoadingState, StateMessage } from '../components/ui';
import { MarkdownContent } from '../components/MarkdownContent';

interface BulletinGroup {
  cluster: Cluster;
  papers: Paper[];
  digest?: Digest | null;
}

interface PaperDetail extends Paper {
  doi?: string | null;
  source?: string | null;
  external_id?: string | null;
  authors?: string | null;
  venue?: string | null;
  primary_category?: string | null;
  citation_count?: number;
  has_pdf?: boolean;
}

interface CategoryOption {
  category: string;
  paper_count: number;
}

interface BulletinPreference {
  selection_type: 'clusters' | 'categories';
  cluster_ids: number[];
  categories: string[];
  notifications_enabled: boolean;
  notification_frequency: string;
  last_generated_at?: string | null;
}

interface UserBulletinResponse {
  configured: boolean;
  preference: BulletinPreference | null;
  bulletin: unknown[];
}

type SelectionType = 'clusters' | 'categories';
type WeeksBestSelectionType = 'cluster' | 'category';

const MIN_CATEGORY_PAPER_COUNT = 500;
const PAPERS_PER_PAGE = 10;

interface WeeksBestSource {
  source_id: string;
  article_id: number;
  title: string;
  authors?: string[];
  published_date?: string | null;
  source_name?: string | null;
  doi?: string | null;
  pdf_url?: string | null;
  external_url?: string | null;
  category?: string | null;
  cluster_id?: number | null;
}

interface WeeksBestBulletin {
  status: 'validated' | 'failed' | 'empty' | 'not_generated';
  title?: string;
  selection_label?: string;
  week_start?: string;
  week_end?: string;
  full_markdown?: string;
  sources?: WeeksBestSource[];
  metadata?: {
    candidate_count?: number;
    selected_count?: number;
    source_count?: number;
    model_name?: string | null;
    use_llm?: boolean;
    generation_source?: string | null;
    llm_error?: string | null;
    generated_at?: string;
    limited_activity?: boolean;
  };
  validation?: {
    valid: boolean;
    errors: string[];
    warnings: string[];
  };
  message?: string;
}

type ApiRecord = Record<string, unknown>;

function asRecord(value: unknown): ApiRecord {
  return typeof value === 'object' && value !== null ? value as ApiRecord : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function normalizeBulletinGroups(data: unknown[]): BulletinGroup[] {
  return data.map((rawCluster) => {
    const c = asRecord(rawCluster);
    if (c.cluster && c.papers) {
      const cluster = asRecord(c.cluster);
      return {
        cluster: {
          id: String(cluster.id ?? ''),
          name: asString(cluster.name),
          keyword: asString(cluster.keyword, asString(cluster.name)),
          paper_count: asNumber(cluster.paper_count),
          color: asString(cluster.color, '#10b981'),
          description: asString(cluster.description),
          created_at: asString(cluster.created_at, new Date().toISOString()),
          metadata: asRecord(cluster.metadata),
        },
        papers: asArray(c.papers).map((rawPaper) => {
          const a = asRecord(rawPaper);
          return {
            id: String(a.id ?? ''),
            title: asString(a.title),
            reference: asString(a.reference),
            abstract: asString(a.abstract),
            url: asNullableString(a.url) || asNullableString(a.link) || undefined,
            pdf_url: asNullableString(a.pdf_url),
            doi: asNullableString(a.doi),
            source: asNullableString(a.source),
            citation_count: asNumber(a.citation_count),
            has_pdf: Boolean(a.has_pdf ?? a.pdf_url),
            representation_score: asNumber(a.representation_score, asNumber(a.score)),
            cluster_id: String(cluster.id ?? ''),
            published_at: asNullableString(a.published_at) || asNullableString(a.publish_date),
            is_representative: Boolean(a.is_representative ?? true),
            is_weekly_pick: Boolean(a.is_weekly_pick ?? false),
            week_label: asString(a.week_label, 'This Week'),
            created_at: asString(a.created_at, asString(a.published_at, new Date().toISOString())),
          };
        }),
        digest: c.digest ? c.digest as Digest : null,
      };
    }

    return {
      cluster: {
        id: String(c.cluster_id ?? ''),
        name: asString(c.cluster_name),
        keyword: asString(c.cluster_name),
        paper_count: asNumber(c.article_count),
        color: '#10b981',
        description: asString(c.cluster_name),
        created_at: new Date().toISOString(),
      },
      papers: asArray(c.articles).map((rawPaper) => {
        const a = asRecord(rawPaper);
        return {
          id: String(a.id ?? ''),
          title: asString(a.title),
          reference: asString(a.reference),
          abstract: asString(a.abstract),
          url: asNullableString(a.url) || asNullableString(a.link) || undefined,
          pdf_url: asNullableString(a.pdf_url),
          representation_score: asNumber(a.score),
          cluster_id: String(c.cluster_id ?? ''),
          published_at: asNullableString(a.publish_date) || asNullableString(a.published_at),
          is_representative: true,
          is_weekly_pick: false,
          week_label: 'This Week',
          created_at: asString(a.publish_date, asString(a.published_at, new Date().toISOString())),
        };
      }),
      digest: null,
    };
  });
}

export default function BulletinPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [groups, setGroups] = useState<BulletinGroup[]>([]);
  const [clusterOptions, setClusterOptions] = useState<Cluster[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<CategoryOption[]>([]);
  const [configured, setConfigured] = useState(false);
  const [preference, setPreference] = useState<BulletinPreference | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWeekly, setShowWeekly] = useState(false);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
  const [currentPageByCluster, setCurrentPageByCluster] = useState<Record<string, number>>({});
  const [selectionType, setSelectionType] = useState<SelectionType>('clusters');
  const [selectedClusterIds, setSelectedClusterIds] = useState<Set<string>>(new Set());
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());
  const [topicSearch, setTopicSearch] = useState('');
  const [topicsOpen, setTopicsOpen] = useState(false);
  const [selectedOnly, setSelectedOnly] = useState(false);
  const initialWeeksBestType = searchParams.get('selection_type') === 'category' ? 'category' : 'cluster';
  const [weeksBestType, setWeeksBestType] = useState<WeeksBestSelectionType>(initialWeeksBestType);
  const [weeksBestSelectionId, setWeeksBestSelectionId] = useState(searchParams.get('selection_id') || '');
  const [weeksBest, setWeeksBest] = useState<WeeksBestBulletin | null>(null);
  const [weeksBestLoading, setWeeksBestLoading] = useState(false);
  const [weeksBestPdfLoading, setWeeksBestPdfLoading] = useState(false);
  const [weeksBestError, setWeeksBestError] = useState<string | null>(null);
  const [weeksBestWeekStart, setWeeksBestWeekStart] = useState(() => searchParams.get('week_start') || previousWeekRange().start);
  const [weeksBestWeekEnd, setWeeksBestWeekEnd] = useState(() => searchParams.get('week_end') || previousWeekRange().end);

  const backendBaseUrl = getBackendBaseUrl();

  useEffect(() => {
    async function fetchData() {
      try {
        const [optionsResponse, bulletinResponse] = await Promise.all([
          fetch(`${backendBaseUrl}/bulletin/options`),
          fetch(`${backendBaseUrl}/bulletin/me`, { headers: getAuthHeaders() }),
        ]);

        await ensureOk(optionsResponse);
        if (bulletinResponse.status === 401) {
          clearStoredUser();
          navigate('/auth');
          return;
        }
        await ensureOk(bulletinResponse);

        const options = asRecord(await optionsResponse.json());
        const userBulletin = await bulletinResponse.json() as UserBulletinResponse;
        setClusterOptions(asArray(options.clusters).map((rawCluster) => {
          const cluster = asRecord(rawCluster);
          return {
            id: String(cluster.id ?? ''),
            name: asString(cluster.name),
            keyword: asString(cluster.keyword, asString(cluster.name)),
            description: asString(cluster.description),
            color: asString(cluster.color, '#10b981'),
            paper_count: asNumber(cluster.paper_count),
            created_at: asString(cluster.created_at, new Date().toISOString()),
            metadata: asRecord(cluster.metadata),
          };
        }));
        const categories = asArray(options.categories).map((rawCategory) => {
          const category = asRecord(rawCategory);
          return {
            category: asString(category.category),
            paper_count: asNumber(category.paper_count),
          };
        }).filter((category) => category.paper_count >= MIN_CATEGORY_PAPER_COUNT);
        setCategoryOptions(categories);
        setConfigured(userBulletin.configured);
        setPreference(userBulletin.preference);
        setGroups(normalizeBulletinGroups(userBulletin.bulletin || []));
        setCurrentPageByCluster({});
        const querySelectionId = searchParams.get('selection_id');
        const querySelectionType = searchParams.get('selection_type');
        if (querySelectionId && (querySelectionType === 'cluster' || querySelectionType === 'category')) {
          setWeeksBestType(querySelectionType);
          setWeeksBestSelectionId(querySelectionId);
          setWeeksBestWeekStart(searchParams.get('week_start') || previousWeekRange().start);
          setWeeksBestWeekEnd(searchParams.get('week_end') || previousWeekRange().end);
        } else if (userBulletin.preference) {
          setSelectionType(userBulletin.preference.selection_type);
          setSelectedClusterIds(new Set((userBulletin.preference.cluster_ids || []).map(String)));
          const availableCategories = new Set(categories.map((item) => item.category));
          const selectedAvailableCategories = (userBulletin.preference.categories || [])
            .filter((category) => availableCategories.has(category));
          setSelectedCategories(new Set(selectedAvailableCategories));
          if (userBulletin.preference.selection_type === 'clusters' && userBulletin.preference.cluster_ids.length) {
            setWeeksBestType('cluster');
            setWeeksBestSelectionId(String(userBulletin.preference.cluster_ids[0]));
          } else if (selectedAvailableCategories.length) {
            setWeeksBestType('category');
            setWeeksBestSelectionId(selectedAvailableCategories[0]);
          }
        }
        setError(null);
      } catch (e) {
        console.error("Failed to fetch bulletin", e);
        setError(normalizeUnknownError(e, "Backend is unavailable.").message);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [backendBaseUrl, navigate, searchParams]);

  useEffect(() => {
    const selectionTypeParam = searchParams.get('selection_type');
    const selectionIdParam = searchParams.get('selection_id');
    const weekStartParam = searchParams.get('week_start');
    const weekEndParam = searchParams.get('week_end');
    if (!selectionIdParam || (selectionTypeParam !== 'cluster' && selectionTypeParam !== 'category')) {
      return;
    }

    const params = new URLSearchParams({
      selection_type: selectionTypeParam,
      selection_id: selectionIdParam,
      use_llm: 'true',
    });
    if (weekStartParam) params.set('week_start', weekStartParam);
    if (weekEndParam) params.set('week_end', weekEndParam);

    async function fetchCachedWeeksBest() {
      setWeeksBestLoading(true);
      setWeeksBestError(null);
      try {
        const response = await fetch(`${backendBaseUrl}/bulletin/weeks-best?${params.toString()}`);
        await ensureOk(response);
        setWeeksBest(await response.json() as WeeksBestBulletin);
      } catch (err) {
        setWeeksBestError(normalizeUnknownError(err, "Week's Best bulletin could not be loaded.").message);
      } finally {
        setWeeksBestLoading(false);
      }
    }

    fetchCachedWeeksBest();
  }, [backendBaseUrl, searchParams]);

  const toggleCluster = (clusterId: string) => {
    setExpandedClusters((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        next.add(clusterId);
        // Reset page to 1 when expanding
        setCurrentPageByCluster(p => ({ ...p, [clusterId]: 1 }));
      }
      return next;
    });
  };

  const topicOptions = useMemo(() => {
    const query = topicSearch.trim().toLowerCase();
    return clusterOptions.filter((cluster) => {
      if (selectedOnly && !selectedClusterIds.has(cluster.id)) {
        return false;
      }
      if (!query) {
        return true;
      }
      return `${cluster.name} ${cluster.keyword} ${cluster.description}`.toLowerCase().includes(query);
    });
  }, [clusterOptions, selectedClusterIds, selectedOnly, topicSearch]);

  const categorySearchOptions = useMemo(() => {
    const query = topicSearch.trim().toLowerCase();
    return categoryOptions.filter((item) => {
      if (selectedOnly && !selectedCategories.has(item.category)) {
        return false;
      }
      return !query || `${item.category} ${categoryLabel(item.category)}`.toLowerCase().includes(query);
    });
  }, [categoryOptions, selectedCategories, selectedOnly, topicSearch]);

  const visibleGroups = groups;
  const weeksBestOptions = weeksBestType === 'cluster'
    ? clusterOptions.map((cluster) => ({ id: cluster.id, label: cluster.name }))
    : categoryOptions.map((item) => ({ id: item.category, label: categoryLabel(item.category) }));

  const toggleTopic = (clusterId: string) => {
    setSelectedClusterIds((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        next.add(clusterId);
      }
      return next;
    });
  };

  const toggleCategory = (category: string) => {
    setSelectedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const saveBulletinPreference = async () => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(`${backendBaseUrl}/bulletin/me`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          selection_type: selectionType,
          cluster_ids: selectionType === 'clusters' ? Array.from(selectedClusterIds).map(Number) : [],
          categories: selectionType === 'categories' ? Array.from(selectedCategories) : [],
          include_digests: true,
          notifications_enabled: true,
        }),
      });

      if (response.status === 401) {
        clearStoredUser();
        navigate('/auth');
        return;
      }
      await ensureOk(response);

      const data = await response.json() as UserBulletinResponse;
      setConfigured(data.configured);
      setPreference(data.preference);
      setGroups(normalizeBulletinGroups(data.bulletin || []));
      setCurrentPageByCluster({});
      setTopicsOpen(false);
    } catch (error) {
      console.error("Failed to save bulletin preference", error);
      setError(normalizeUnknownError(error, "Bulletin preference could not be saved.").message);
    } finally {
      setSaving(false);
    }
  };

  const generateWeeksBest = async (forceRefresh = false) => {
    if (!weeksBestSelectionId) {
      setWeeksBestError('Choose a cluster or category first.');
      return;
    }
    if (!weeksBestWeekStart || !weeksBestWeekEnd || weeksBestWeekEnd < weeksBestWeekStart) {
      setWeeksBestError('Choose a valid date range.');
      return;
    }
    setWeeksBestLoading(true);
    setWeeksBestError(null);
    try {
      const response = await fetch(`${backendBaseUrl}/bulletin/weeks-best/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          selection_type: weeksBestType,
          selection_id: weeksBestSelectionId,
          week_start: weeksBestWeekStart,
          week_end: weeksBestWeekEnd,
          force_refresh: forceRefresh,
          use_llm: true,
        }),
      });
      await ensureOk(response);
      setWeeksBest(await response.json() as WeeksBestBulletin);
      window.dispatchEvent(new Event('notifications-updated'));
    } catch (error) {
      console.error("Failed to generate Week's Best bulletin", error);
      setWeeksBestError(normalizeUnknownError(error, "Week's Best bulletin could not be generated.").message);
    } finally {
      setWeeksBestLoading(false);
    }
  };

  const downloadWeeksBestPdf = async () => {
    if (!weeksBestSelectionId) {
      setWeeksBestError('Choose a cluster or category first.');
      return;
    }
    setWeeksBestPdfLoading(true);
    setWeeksBestError(null);
    try {
      const params = new URLSearchParams({
        selection_type: weeksBestType,
        selection_id: weeksBestSelectionId,
        week_start: weeksBestWeekStart,
        week_end: weeksBestWeekEnd,
        use_llm: 'true',
      });
      const response = await fetch(`${backendBaseUrl}/bulletin/weeks-best/pdf?${params.toString()}`, {
        headers: getAuthHeaders(),
      });
      await ensureOk(response);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `weeks_best_${weeksBestType}_${weeksBestSelectionId}_${weeksBestWeekStart}_${weeksBestWeekEnd}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Failed to download Week's Best PDF", error);
      setWeeksBestError(normalizeUnknownError(error, "Week's Best PDF could not be downloaded.").message);
    } finally {
      setWeeksBestPdfLoading(false);
    }
  };

  if (loading) {
    return <LoadingState label="Loading bulletin..." />;
  }

  if (error) {
    return <StateMessage title="Bulletin unavailable" body={error} />;
  }

  if (!clusterOptions.length && !categoryOptions.length) {
    return <StateMessage title="No clusters yet" body="Run ingestion, embeddings, and clustering to populate the bulletin." />;
  }

  if (!configured) {
    return (
      <div className="h-screen overflow-y-auto bg-[var(--canvas)]">
        <header className="border-b border-[var(--border)] bg-[var(--surface)] px-6 py-4">
          <div className="flex items-center gap-3">
            <Newspaper size={20} className="text-emerald-500" />
            <div>
              <h1 className="text-lg font-semibold text-[var(--text-primary)]">Research Bulletin</h1>
              <p className="text-xs text-[var(--text-secondary)]">Choose clusters or categories to create your saved bulletin</p>
            </div>
          </div>
        </header>
        <div className="mx-auto max-w-5xl p-6">
          <BulletinPreferencePanel
            categoryOptions={categorySearchOptions}
            clusterOptions={topicOptions}
            configured={configured}
            onClear={() => selectionType === 'clusters' ? setSelectedClusterIds(new Set()) : setSelectedCategories(new Set())}
            onSave={saveBulletinPreference}
            onSelectAll={() => {
              if (selectionType === 'clusters') {
                setSelectedClusterIds(new Set(clusterOptions.map((cluster) => cluster.id)));
              } else {
                setSelectedCategories(new Set(categoryOptions.map((item) => item.category)));
              }
            }}
            onSelectionTypeChange={setSelectionType}
            onTopicSearchChange={setTopicSearch}
            selectedOnly={selectedOnly}
            onSelectedOnlyChange={setSelectedOnly}
            saving={saving}
            selectedCategories={selectedCategories}
            selectedClusterIds={selectedClusterIds}
            selectionType={selectionType}
            topicSearch={topicSearch}
            toggleCategory={toggleCategory}
            toggleTopic={toggleTopic}
          />
          <TelegramConnectionPanel />
        </div>
      </div>
    );
  }

  if (!groups.length) {
    return <StateMessage title="No matching papers" body="Your saved bulletin does not have matching papers yet. Update your selected topics or run ingestion again." />;
  }

  const allPapers = visibleGroups.flatMap(g => g.papers);
  const weeklyPapers = allPapers.filter((paper) => paper.is_weekly_pick)
    .sort((a, b) => (b.representation_score || 0) - (a.representation_score || 0))
    .slice(0, 6);
  const weeklyClusterIds = new Set(weeklyPapers.map((p) => p.cluster_id));

  return (
    <div className="h-screen overflow-y-auto bg-[var(--canvas)]">
      {/* Header */}
      <header className="bg-[var(--surface)] border-b border-[var(--border)] px-6 py-4 sticky top-0 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Newspaper size={20} className="text-emerald-500" />
            <div>
              <h1 className="text-lg font-semibold text-[var(--text-primary)]">Research Bulletin</h1>
              <p className="text-xs text-[var(--text-secondary)]">
                {preference?.selection_type === 'categories'
                  ? `Saved categories: ${preference.categories.map(categoryLabel).join(', ')}`
                  : `Saved clusters: ${preference?.cluster_ids.length || 0}`}
              </p>
            </div>
          </div>
          {weeklyPapers.length ? (
            <button
              onClick={() => setShowWeekly(!showWeekly)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer ${
                showWeekly
                  ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20'
                  : 'bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--text-secondary)] hover:border-emerald-300 hover:text-emerald-500'
              }`}
            >
              <Clock size={14} />
              <span>Week's Best</span>
            </button>
          ) : null}
        </div>
      </header>

      <div className="p-6">
        {/* Weekly Highlights Section */}
        {showWeekly && weeklyPapers.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-5">
              <Sparkles size={16} className="text-amber-500" />
              <h2 className="text-base font-semibold text-[var(--text-primary)]">This Week's Highlights</h2>
              <span className="px-2 py-0.5 bg-amber-50 text-amber-600 text-xs font-medium rounded-full">
                {weeklyPapers.length} papers
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {visibleGroups
                .filter((g) => weeklyClusterIds.has(g.cluster.id))
                .map(({ cluster, papers }) => {
                  const clusterWeekly = papers.slice(0, 2);
                  return (
                    <div
                      key={cluster.id}
                      className="bg-[var(--surface)] rounded-xl border border-[var(--border)] overflow-hidden hover:shadow-md transition-shadow duration-200"
                    >
                      <div className="relative h-28 overflow-hidden">
                        <img
                          src={getImageForTopic(cluster.keyword)}
                          alt={cluster.keyword}
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                        <div className="absolute bottom-3 left-4 right-4">
                          <span
                            className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold text-white uppercase tracking-wider"
                            style={{ background: cluster.color }}
                          >
                            {cluster.name}
                          </span>
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        {clusterWeekly.map((paper) => (
                          <div key={paper.id} className="group">
                            <h4 className="text-sm font-semibold text-[var(--text-primary)] group-hover:text-emerald-500 transition-colors line-clamp-2">
                              {paper.title}
                            </h4>
                            <p className="text-[10px] text-[var(--text-muted)] mt-0.5 italic">{paper.reference}</p>
                            <p className="text-xs text-[var(--text-secondary)] mt-1.5 line-clamp-3 leading-relaxed">
                              {paper.abstract}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        <BulletinPreferencePanel
          categoryOptions={categorySearchOptions}
          clusterOptions={topicOptions}
          configured={configured}
          onClear={() => selectionType === 'clusters' ? setSelectedClusterIds(new Set()) : setSelectedCategories(new Set())}
          onSave={saveBulletinPreference}
          onSelectAll={() => {
            if (selectionType === 'clusters') {
              setSelectedClusterIds(new Set(clusterOptions.map((cluster) => cluster.id)));
            } else {
              setSelectedCategories(new Set(categoryOptions.map((item) => item.category)));
            }
          }}
          onSelectionTypeChange={setSelectionType}
          onTopicSearchChange={setTopicSearch}
          onSelectedOnlyChange={setSelectedOnly}
          selectedOnly={selectedOnly}
          open={topicsOpen}
          onOpenChange={setTopicsOpen}
          saving={saving}
          selectedCategories={selectedCategories}
          selectedClusterIds={selectedClusterIds}
          selectionType={selectionType}
          topicSearch={topicSearch}
          toggleCategory={toggleCategory}
          toggleTopic={toggleTopic}
        />

        <TelegramConnectionPanel />

        <WeeksBestPanel
          bulletin={weeksBest}
          error={weeksBestError}
          loading={weeksBestLoading}
          pdfLoading={weeksBestPdfLoading}
          onDownloadPdf={downloadWeeksBestPdf}
          onGenerate={() => generateWeeksBest(false)}
          onRefresh={() => generateWeeksBest(true)}
          onSelectionChange={(value) => {
            setWeeksBestSelectionId(value);
            setWeeksBest(null);
          }}
          onWeekEndChange={(value) => {
            setWeeksBestWeekEnd(value);
            setWeeksBest(null);
          }}
          onWeekStartChange={(value) => {
            setWeeksBestWeekStart(value);
            setWeeksBest(null);
          }}
          onTypeChange={(type) => {
            setWeeksBestType(type);
            setWeeksBestSelectionId('');
            setWeeksBest(null);
          }}
          options={weeksBestOptions}
          selectionId={weeksBestSelectionId}
          selectionType={weeksBestType}
          weekEnd={weeksBestWeekEnd}
          weekStart={weeksBestWeekStart}
        />

        {/* Cluster Groups */}
        <div className="space-y-3">
          {visibleGroups.length ? visibleGroups.map(({ cluster, papers, digest }) => {
            const isExpanded = expandedClusters.has(cluster.id);
            const totalPages = Math.max(1, Math.ceil(papers.length / PAPERS_PER_PAGE));
            const requestedPage = currentPageByCluster[cluster.id] || 1;
            const currentPage = Math.min(Math.max(requestedPage, 1), totalPages);
            
            const startIndex = (currentPage - 1) * PAPERS_PER_PAGE;
            const visiblePapers = isExpanded 
              ? papers.slice(startIndex, startIndex + PAPERS_PER_PAGE) 
              : papers.slice(0, 3);

            return (
              <div
                key={cluster.id}
                className="bg-[var(--surface)] rounded-xl border border-[var(--border)] overflow-hidden shadow-sm"
              >
                {/* Cluster Header Accordion Trigger */}
                <button
                  onClick={() => toggleCluster(cluster.id)}
                  className="w-full flex items-center justify-between px-5 py-4 hover:bg-[var(--surface-elevated)] transition-colors cursor-pointer border-b border-transparent hover:border-[var(--border-muted)]"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ background: cluster.color }}
                    />
                    <h3 className="text-sm font-semibold text-[var(--text-primary)] text-left">{cluster.name}</h3>
                    <span className="text-xs text-[var(--text-muted)] font-medium">
                      ({papers.length} of {cluster.paper_count} papers loaded)
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        background: `${cluster.color}15`,
                        color: cluster.color,
                      }}
                    >
                      {cluster.paper_count} total papers
                    </span>
                    {isExpanded ? (
                      <ChevronUp size={16} className="text-[var(--text-muted)]" />
                    ) : (
                      <ChevronDown size={16} className="text-[var(--text-muted)]" />
                    )}
                  </div>
                </button>

                {/* Papers Grid */}
                <div className={`px-5 pb-5 pt-3 bg-[var(--surface-elevated)]/50 ${isExpanded ? 'block' : 'block'}`}>
                  {digest?.summary && (
                    <div className="mb-4 rounded-lg border border-emerald-500/30 bg-[var(--accent-soft)] p-3">
                      <p className="text-xs font-semibold text-emerald-700">Cluster digest</p>
                      <p className="mt-1 text-sm text-[var(--text-primary)] leading-relaxed">{digest.summary}</p>
                      {digest.highlights?.length ? (
                        <ul className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
                          {digest.highlights.map((highlight) => (
                            <li key={highlight}>{highlight}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  )}
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
                    {visiblePapers.length ? visiblePapers.map((paper) => (
                        <PaperCard
                          key={paper.id}
                          paper={paper}
                          clusterColor={cluster.color}
                          backendBaseUrl={backendBaseUrl}
                          onAsk={() => navigate('/session/new', {
                            state: { initialPrompt: `Summarize "${paper.title}" and explain how it fits the ${cluster.name} research cluster.` },
                          })}
                        />
                    )) : (
                      <div className="col-span-full py-6 text-sm text-[var(--text-secondary)] text-center">No representative papers in this cluster.</div>
                    )}
                  </div>

                  {isExpanded && totalPages > 1 && (
                    <PaginationControls
                      currentPage={currentPage}
                      pageSize={PAPERS_PER_PAGE}
                      totalItems={papers.length}
                      totalPages={totalPages}
                      onPageChange={(page) => {
                        setCurrentPageByCluster((prev) => ({ ...prev, [cluster.id]: page }));
                      }}
                    />
                  )}
                </div>
              </div>
            );
          }) : (
            <EmptyState title="No topics selected" body="Open topic management and select at least one cluster or category." />
          )}
        </div>
      </div>
    </div>
  );
}

function PaginationControls({
  currentPage,
  onPageChange,
  pageSize,
  totalItems,
  totalPages,
}: {
  currentPage: number;
  onPageChange: (page: number) => void;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}) {
  const startItem = totalItems ? (currentPage - 1) * pageSize + 1 : 0;
  const endItem = Math.min(currentPage * pageSize, totalItems);
  const pages = getVisiblePageNumbers(currentPage, totalPages);

  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-[var(--border)] pt-3 lg:flex-row lg:items-center lg:justify-between">
      <p className="text-xs font-medium text-[var(--text-secondary)]">
        Showing {startItem}-{endItem} of {totalItems} papers
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={currentPage === 1}
          onClick={() => onPageChange(currentPage - 1)}
          className="inline-flex h-8 items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-elevated)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft size={14} />
          Previous
        </button>
        {pages.map((page) => (
          <button
            key={page}
            type="button"
            onClick={() => onPageChange(page)}
            className={`h-8 min-w-8 rounded-md border px-2 text-xs font-semibold transition-colors ${
              page === currentPage
                ? 'border-emerald-400 bg-[var(--accent-soft)] text-emerald-600'
                : 'border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]'
            }`}
            aria-current={page === currentPage ? 'page' : undefined}
          >
            {page}
          </button>
        ))}
        <button
          type="button"
          disabled={currentPage === totalPages}
          onClick={() => onPageChange(currentPage + 1)}
          className="inline-flex h-8 items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-elevated)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

function getVisiblePageNumbers(currentPage: number, totalPages: number) {
  if (totalPages <= 5) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
  return Array.from({ length: 5 }, (_, index) => start + index);
}

function BulletinPreferencePanel({
  categoryOptions,
  clusterOptions,
  configured,
  open = true,
  onClear,
  onOpenChange,
  onSave,
  onSelectAll,
  onSelectionTypeChange,
  onSelectedOnlyChange,
  onTopicSearchChange,
  saving,
  selectedOnly,
  selectedCategories,
  selectedClusterIds,
  selectionType,
  topicSearch,
  toggleCategory,
  toggleTopic,
}: {
  categoryOptions: CategoryOption[];
  clusterOptions: Cluster[];
  configured: boolean;
  open?: boolean;
  onClear: () => void;
  onOpenChange?: (open: boolean) => void;
  onSave: () => void;
  onSelectAll: () => void;
  onSelectionTypeChange: (type: SelectionType) => void;
  onSelectedOnlyChange: (selectedOnly: boolean) => void;
  onTopicSearchChange: (value: string) => void;
  saving: boolean;
  selectedOnly: boolean;
  selectedCategories: Set<string>;
  selectedClusterIds: Set<string>;
  selectionType: SelectionType;
  topicSearch: string;
  toggleCategory: (category: string) => void;
  toggleTopic: (clusterId: string) => void;
}) {
  const selectedCount = selectionType === 'clusters' ? selectedClusterIds.size : selectedCategories.size;
  const totalCount = selectionType === 'clusters' ? clusterOptions.length : categoryOptions.length;
  const panelOpen = configured ? open : true;

  return (
    <section className="mb-6 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
      <div className="flex flex-col gap-3 border-b border-[var(--border-muted)] px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{configured ? 'Saved bulletin topics' : 'Create your bulletin'}</h2>
          <p className="text-xs text-[var(--text-secondary)]">{selectedCount} selected of {totalCount} visible</p>
        </div>
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          {configured ? (
            <button
              type="button"
              onClick={() => onOpenChange?.(!panelOpen)}
              className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              {panelOpen ? 'Hide topics' : 'Manage topics'}
            </button>
          ) : null}
          {panelOpen ? (
            <>
          <div className="inline-flex h-9 rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] p-0.5">
            <button
              type="button"
              onClick={() => onSelectionTypeChange('clusters')}
              className={`rounded px-3 text-xs font-semibold transition-colors ${
                selectionType === 'clusters' ? 'bg-[var(--surface)] text-emerald-600 shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              Clusters
            </button>
            <button
              type="button"
              onClick={() => onSelectionTypeChange('categories')}
              className={`rounded px-3 text-xs font-semibold transition-colors ${
                selectionType === 'categories' ? 'bg-[var(--surface)] text-emerald-600 shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              Categories
            </button>
          </div>
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              value={topicSearch}
              onChange={(event) => onTopicSearchChange(event.target.value)}
              className="h-9 w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] pl-8 pr-8 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-emerald-400 sm:w-72"
              placeholder={selectionType === 'clusters' ? 'Search clusters' : 'Search categories'}
            />
            {topicSearch && (
              <button
                type="button"
                onClick={() => onTopicSearchChange('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-[var(--text-muted)] hover:bg-[var(--surface-high)] hover:text-[var(--text-primary)]"
                aria-label="Clear topic search"
              >
                <X size={13} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onSelectedOnlyChange(!selectedOnly)}
              className={`h-9 rounded-md border px-3 text-xs font-semibold ${
                selectedOnly
                  ? 'border-emerald-400 bg-[var(--accent-soft)] text-emerald-600'
                  : 'border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              Selected
            </button>
            <button
              type="button"
              onClick={onSelectAll}
              className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-emerald-300 hover:text-emerald-600"
            >
              All
            </button>
            <button
              type="button"
              onClick={onClear}
              className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-rose-300 hover:text-rose-600"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={onSave}
              disabled={saving || selectedCount === 0}
              className="h-9 rounded-md bg-emerald-500 px-3 text-xs font-semibold text-white shadow-sm shadow-emerald-500/20 hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? 'Saving...' : configured ? 'Update' : 'Create'}
            </button>
          </div>
            </>
          ) : null}
        </div>
      </div>
      {panelOpen ? (
      <div className="max-h-64 overflow-y-auto p-3">
        {selectionType === 'clusters' ? (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
            {clusterOptions.length ? clusterOptions.map((cluster) => {
              const checked = selectedClusterIds.has(cluster.id);
              return (
                <label
                  key={cluster.id}
                  className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-md border px-3 py-2 transition-colors ${
                    checked
                      ? 'border-emerald-400/60 bg-[var(--accent-soft)]'
                      : 'border-[var(--border)] bg-[var(--surface)] hover:border-[var(--text-muted)]'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleTopic(cluster.id)}
                    className="h-4 w-4 rounded border-[var(--border)] text-emerald-500 focus:ring-emerald-400"
                  />
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: cluster.color }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-[var(--text-primary)]">{cluster.name}</span>
                    <span className="block text-xs text-[var(--text-muted)]">{cluster.paper_count} papers</span>
                  </span>
                </label>
              );
            }) : <div className="col-span-full py-6 text-center text-sm text-[var(--text-secondary)]">No clusters match the current filter.</div>}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
            {categoryOptions.length ? categoryOptions.map((item) => {
              const checked = selectedCategories.has(item.category);
              return (
                <label
                  key={item.category}
                  className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-md border px-3 py-2 transition-colors ${
                    checked
                      ? 'border-emerald-400/60 bg-[var(--accent-soft)]'
                      : 'border-[var(--border)] bg-[var(--surface)] hover:border-[var(--text-muted)]'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleCategory(item.category)}
                    className="h-4 w-4 rounded border-[var(--border)] text-emerald-500 focus:ring-emerald-400"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-[var(--text-primary)]">{categoryLabel(item.category)}</span>
                    <span className="block text-xs text-[var(--text-muted)]">{item.paper_count} papers</span>
                  </span>
                </label>
              );
            }) : <div className="col-span-full py-6 text-center text-sm text-[var(--text-secondary)]">No categories match the current filter.</div>}
          </div>
        )}
      </div>
      ) : null}
    </section>
  );
}

function TelegramConnectionPanel() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    try {
      setStatus(await fetchTelegramStatus());
      setError(null);
    } catch (err) {
      setError(normalizeUnknownError(err, 'Telegram status could not be loaded.').message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const connectTelegram = async () => {
    setLoading(true);
    try {
      const token = await createTelegramLinkToken();
      setLinkUrl(token.link_url);
      window.open(token.link_url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => {
        loadStatus();
      }, 4000);
      setError(null);
    } catch (err) {
      setError(normalizeUnknownError(err, 'Telegram link could not be created.').message);
    } finally {
      setLoading(false);
    }
  };

  const disconnectTelegram = async () => {
    setLoading(true);
    try {
      await unlinkTelegram();
      setLinkUrl(null);
      await loadStatus();
    } catch (err) {
      setError(normalizeUnknownError(err, 'Telegram connection could not be removed.').message);
      setLoading(false);
    }
  };

  const configured = status?.configured ?? true;

  return (
    <section className="mb-6 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Telegram notifications</h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {!configured
              ? 'Optional Telegram delivery is not configured on this instance. Add bot and ngrok settings to enable mobile PDF delivery.'
              : status?.linked
              ? `Connected${status.telegram_username ? ` as @${status.telegram_username}` : ''}. Week's Best bulletins will be sent as PDF documents.`
              : 'Connect Telegram to receive Week\'s Best bulletins when generation completes.'}
          </p>
          {status?.last_error ? <p className="mt-1 text-xs text-amber-600">{status.last_error}</p> : null}
          {error ? <p className="mt-1 text-xs text-rose-600">{error}</p> : null}
          {linkUrl ? (
            <a
              href={linkUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:underline"
            >
              <ExternalLink size={12} />
              Open Telegram link
            </a>
          ) : null}
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={loadStatus}
            disabled={loading}
            className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] disabled:opacity-50"
          >
            Refresh
          </button>
          {status?.linked ? (
            <button
              type="button"
              onClick={disconnectTelegram}
              disabled={loading}
              className="h-9 rounded-md border border-rose-300 bg-rose-50 px-3 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50"
            >
              Disconnect
            </button>
          ) : (
            <button
              type="button"
              onClick={connectTelegram}
              disabled={loading || !configured}
              className="h-9 rounded-md bg-emerald-500 px-3 text-xs font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Connect Telegram
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function WeeksBestPanel({
  bulletin,
  error,
  loading,
  pdfLoading,
  onDownloadPdf,
  onGenerate,
  onRefresh,
  onSelectionChange,
  onWeekEndChange,
  onWeekStartChange,
  onTypeChange,
  options,
  selectionId,
  selectionType,
  weekEnd,
  weekStart,
}: {
  bulletin: WeeksBestBulletin | null;
  error: string | null;
  loading: boolean;
  pdfLoading: boolean;
  onDownloadPdf: () => void;
  onGenerate: () => void;
  onRefresh: () => void;
  onSelectionChange: (value: string) => void;
  onWeekEndChange: (value: string) => void;
  onWeekStartChange: (value: string) => void;
  onTypeChange: (type: WeeksBestSelectionType) => void;
  options: Array<{ id: string; label: string }>;
  selectionId: string;
  selectionType: WeeksBestSelectionType;
  weekEnd: string;
  weekStart: string;
}) {
  const statusLabel = bulletin?.status === 'validated'
    ? 'Validated'
    : bulletin?.status === 'empty'
      ? 'No papers'
      : bulletin?.status === 'failed'
        ? 'Validation failed'
        : 'Not generated';

  return (
    <section className="mb-6 border border-[var(--border)] bg-[var(--surface)] rounded-lg">
      <div className="flex flex-col gap-3 border-b border-[var(--border-muted)] px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles size={15} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Week's Best Bulletin</h2>
            {bulletin ? (
              <span className="rounded bg-[var(--surface-elevated)] px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--text-secondary)]">
                {statusLabel}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {weekStart} - {weekEnd} · Ollama editorial generation from selected weekly papers
          </p>
        </div>
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="inline-flex h-9 rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] p-0.5">
            <button
              type="button"
              onClick={() => onTypeChange('cluster')}
              className={`rounded px-3 text-xs font-semibold ${selectionType === 'cluster' ? 'bg-[var(--surface)] text-emerald-600 shadow-sm' : 'text-[var(--text-secondary)]'}`}
            >
              Cluster
            </button>
            <button
              type="button"
              onClick={() => onTypeChange('category')}
              className={`rounded px-3 text-xs font-semibold ${selectionType === 'category' ? 'bg-[var(--surface)] text-emerald-600 shadow-sm' : 'text-[var(--text-secondary)]'}`}
            >
              Category
            </button>
          </div>
          <select
            value={selectionId}
            onChange={(event) => onSelectionChange(event.target.value)}
            className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-emerald-400 lg:w-80"
          >
            <option value="">Choose {selectionType}</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <label className="flex h-9 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-2 text-xs text-[var(--text-secondary)]">
            <span className="font-medium">From</span>
            <input
              type="date"
              value={weekStart}
              max={weekEnd}
              onChange={(event) => onWeekStartChange(event.target.value)}
              className="h-7 bg-transparent text-xs font-semibold text-[var(--text-primary)] outline-none"
            />
          </label>
          <label className="flex h-9 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-2 text-xs text-[var(--text-secondary)]">
            <span className="font-medium">To</span>
            <input
              type="date"
              value={weekEnd}
              min={weekStart}
              onChange={(event) => onWeekEndChange(event.target.value)}
              className="h-7 bg-transparent text-xs font-semibold text-[var(--text-primary)] outline-none"
            />
          </label>
          <button
            type="button"
            onClick={onGenerate}
            disabled={loading || !selectionId}
            className="h-9 rounded-md bg-emerald-500 px-3 text-xs font-semibold text-white shadow-sm shadow-emerald-500/20 hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Generating...' : 'Generate'}
          </button>
          {bulletin ? (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading || !selectionId}
              className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-emerald-300 hover:text-emerald-600 disabled:opacity-50"
            >
              Refresh
            </button>
          ) : null}
          {bulletin?.status === 'validated' ? (
            <button
              type="button"
              onClick={onDownloadPdf}
              disabled={loading || pdfLoading || !selectionId}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-emerald-500/40 bg-[var(--accent-soft)] px-3 text-xs font-semibold text-emerald-600 hover:border-emerald-400 disabled:opacity-50"
            >
              <Download size={13} />
              {pdfLoading ? 'Preparing...' : 'PDF'}
            </button>
          ) : null}
        </div>
      </div>

      <div className="p-4">
        {error ? (
          <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>
        ) : null}

        {!bulletin && !error ? (
          <div className="rounded-md border border-dashed border-[var(--border)] bg-[var(--surface-elevated)] px-4 py-6 text-center text-sm text-[var(--text-secondary)]">
            Generate a cached weekly editorial bulletin for the selected topic.
          </div>
        ) : null}

        {bulletin?.status === 'empty' ? (
          <div className="rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-4 py-3 text-sm text-[var(--text-secondary)]">
            {bulletin.message || 'No eligible papers were found for this week.'}
          </div>
        ) : null}

        {bulletin?.status === 'failed' ? (
          <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            The generated bulletin did not pass validation.
            {bulletin.validation?.errors?.length ? ` ${bulletin.validation.errors.join(' ')}` : ''}
          </div>
        ) : null}

        {bulletin?.status === 'validated' ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <article className="rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-secondary)]">
                <span>{bulletin.selection_label}</span>
                <span>·</span>
                <span>{bulletin.week_start} - {bulletin.week_end}</span>
                <span>·</span>
                <span>{bulletin.metadata?.selected_count || 0} selected papers</span>
                <span>·</span>
                <span>{bulletin.metadata?.candidate_count || 0} candidates reviewed</span>
                {bulletin.metadata?.model_name ? (
                  <>
                    <span>·</span>
                    <span>{bulletin.metadata.model_name}</span>
                  </>
                ) : null}
                {bulletin.metadata?.generation_source ? (
                  <>
                    <span>·</span>
                    <span>{bulletin.metadata.generation_source}</span>
                  </>
                ) : null}
              </div>
              {bulletin.metadata?.llm_error ? (
                <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  {bulletin.metadata.llm_error}
                </div>
              ) : null}
              <MarkdownContent content={bulletin.full_markdown || ''} />
            </article>
            <aside className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-4">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Sources</h3>
              <div className="mt-3 space-y-3">
                {(bulletin.sources || []).map((source) => (
                  <div key={source.source_id} className="rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] p-3">
                    <p className="text-xs font-semibold text-emerald-600">[{source.source_id}]</p>
                    <p className="mt-1 text-sm font-semibold leading-snug text-[var(--text-primary)]">{source.title}</p>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">
                      {(source.authors || []).slice(0, 3).join(', ') || 'Unknown authors'}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      {source.source_name || 'Unknown source'} · {source.published_date || 'Unknown date'}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {source.pdf_url ? (
                        <a href={source.pdf_url} target="_blank" rel="noreferrer" className="text-xs font-semibold text-emerald-600 hover:underline">PDF</a>
                      ) : null}
                      {source.external_url ? (
                        <a href={source.external_url} target="_blank" rel="noreferrer" className="text-xs font-semibold text-emerald-600 hover:underline">Source</a>
                      ) : null}
                      {source.doi ? <span className="text-xs text-[var(--text-muted)]">DOI: {source.doi}</span> : null}
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function previousWeekRange(): { start: string; end: string; label: string } {
  const today = new Date();
  const day = today.getDay();
  const daysSinceMonday = day === 0 ? 6 : day - 1;
  const thisMonday = new Date(today);
  thisMonday.setHours(0, 0, 0, 0);
  thisMonday.setDate(today.getDate() - daysSinceMonday);
  const previousMonday = new Date(thisMonday);
  previousMonday.setDate(thisMonday.getDate() - 7);
  const previousSunday = new Date(thisMonday);
  previousSunday.setDate(thisMonday.getDate() - 1);
  const start = previousMonday.toISOString().slice(0, 10);
  const end = previousSunday.toISOString().slice(0, 10);
  return { start, end, label: `${start} - ${end}` };
}

function PaperCard({
  paper,
  clusterColor,
  backendBaseUrl,
  onAsk,
}: {
  paper: Paper;
  clusterColor: string;
  backendBaseUrl: string;
  onAsk: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<PaperDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const openPaper = async () => {
    const nextExpanded = !expanded;
    setExpanded(nextExpanded);
    if (!nextExpanded || detail || detailLoading) {
      return;
    }

    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await fetch(`${backendBaseUrl}/bulletin/articles/${paper.id}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setDetail({
        ...paper,
        ...data,
        id: String(data.id),
        cluster_id: String(data.cluster_id ?? paper.cluster_id),
        published_at: data.published_at || paper.published_at,
        is_representative: paper.is_representative,
        representation_score: paper.representation_score,
        is_weekly_pick: paper.is_weekly_pick,
        week_label: paper.week_label,
        created_at: paper.created_at,
      });
    } catch (error) {
      console.error("Failed to fetch paper detail", error);
      setDetailError("Paper detail is unavailable.");
    } finally {
      setDetailLoading(false);
    }
  };

  const visiblePaper = detail || paper;
  const abstractText = visiblePaper.abstract || 'No abstract available.';
  const sourceUrl = visiblePaper.url || paper.url;
  const pdfUrl = visiblePaper.pdf_url || paper.pdf_url || null;

  return (
    <div
      className="group border border-[var(--border)] bg-[var(--surface)] rounded-lg p-3.5 hover:border-[var(--text-muted)] hover:shadow-md transition-all duration-200 cursor-pointer"
      onClick={openPaper}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-[var(--text-primary)] group-hover:text-emerald-500 transition-colors line-clamp-2 leading-snug">
          {paper.title}
        </h4>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="text-[var(--text-muted)] hover:text-emerald-400 transition-colors"
            aria-label="Open paper source"
          >
            <ExternalLink size={12} />
          </a>
        ) : (
          <ExternalLink size={12} className="text-[var(--text-muted)] shrink-0 mt-0.5" />
        )}
      </div>
      <p className="text-[10px] text-[var(--text-muted)] mt-1 italic">{paper.reference}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {visiblePaper.source ? (
          <span className="rounded bg-[var(--surface-elevated)] px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--text-secondary)]">
            {visiblePaper.source}
          </span>
        ) : null}
        {visiblePaper.citation_count ? (
          <span className="rounded bg-[var(--surface-elevated)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
            {visiblePaper.citation_count} citations
          </span>
        ) : null}
        {visiblePaper.has_pdf ? (
          <span className="rounded bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
            PDF
          </span>
        ) : null}
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <div className="flex-1 bg-[var(--surface-high)] rounded-full h-1">
          <div
            className="h-1 rounded-full transition-all duration-500"
            style={{
              width: `${paper.representation_score * 100}%`,
              background: clusterColor,
              opacity: 0.7,
            }}
          />
        </div>
        <span className="text-[10px] text-[var(--text-muted)] font-semibold">
          {Math.round(paper.representation_score * 100)}% Match
        </span>
      </div>
      <p className={`text-xs text-[var(--text-secondary)] mt-2.5 leading-relaxed ${expanded ? '' : 'line-clamp-3'}`}>
        {detailLoading ? 'Loading full abstract...' : abstractText}
      </p>
      {detailError && <p className="mt-2 text-xs text-rose-500">{detailError}</p>}
      {expanded && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onAsk();
            }}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--text-primary)] px-2.5 text-xs font-semibold text-[var(--canvas)] hover:opacity-90"
          >
            Ask
          </button>
          {pdfUrl ? (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-emerald-500/40 bg-[var(--accent-soft)] px-2.5 text-xs font-semibold text-emerald-600 hover:border-emerald-400"
            >
              <ExternalLink size={12} />
              PDF
            </a>
          ) : null}
          {sourceUrl ? (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
            >
              <ExternalLink size={12} />
              Source
            </a>
          ) : null}
          {visiblePaper.doi ? (
            <span className="rounded-md bg-[var(--surface-elevated)] px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)]">
              DOI: {visiblePaper.doi}
            </span>
          ) : null}
        </div>
      )}
      {paper.published_at && (
        <p className="text-[9px] font-medium text-[var(--text-muted)] mt-2.5">
          Published: {new Date(paper.published_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
          })}
        </p>
      )}
    </div>
  );
}

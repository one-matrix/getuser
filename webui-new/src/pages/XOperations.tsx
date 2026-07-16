import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Empty,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
  theme,
} from 'antd';
import {
  ApiOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CommentOutlined,
  CopyOutlined,
  ExportOutlined,
  EyeOutlined,
  GlobalOutlined,
  LockOutlined,
  MessageOutlined,
  ReadOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  StopOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  UserOutlined,
  WalletOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { authStorage } from '../api/auth';
import {
  analyzeXConversation,
  approveXReview,
  collectXTopicPosts,
  collectXThread,
  generateXReplyCandidates,
  getXAccounts,
  getXAuditLogs,
  getXAutomationStatus,
  getXConversation,
  getXPosts,
  getXReviews,
  getXTopics,
  getXUsage,
  publishXReview,
  refreshXTopics,
  regenerateXReview,
  rejectXReview,
  saveXAccountApprovalEvidence,
  startXOAuth,
  testXAccount,
  updateXAccount,
  updateXAutomationControls,
  type XAccount,
  type XAuditLog,
  type XAutomationStatus,
  type XConversation,
  type XEndpointUsage,
  type XPolicyCheck,
  type XPost,
  type XPublicMetrics,
  type XReplyCandidate,
  type XReviewTask,
  type XThreadAnalysis,
  type XTopic,
  type XUsageSummary,
} from '../api/xOperations';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const SAFE_AUTOMATION_DEFAULTS: XAutomationStatus = {
  read_enabled: false,
  write_enabled: false,
  auto_reply_enabled: false,
  global_kill_switch: true,
  require_human_review: true,
  effective_write_allowed: false,
  reasons: ['尚未读取后端安全状态，前端按最严格模式处理'],
};

const REVIEW_STATUS_LABELS: Record<string, string> = {
  PENDING: '待审核',
  IN_REVIEW: '审核中',
  NEW: '待生成',
  AI_GENERATED: 'AI 已生成',
  NEEDS_FACT_CHECK: '待事实核验',
  NEEDS_REVIEW: '待审核',
  APPROVED: '已批准',
  REJECTED: '已拒绝',
  QUEUED: '待发布',
  PUBLISHING: '发布中',
  PUBLISHED: '已发布',
  CANCELLED: '已取消',
  PUBLISH_FAILED: '发布失败',
  BLOCKED: '已阻断',
  DEFERRED: '预算延后',
};

const REVIEW_STATUS_COLORS: Record<string, string> = {
  PENDING: 'gold',
  IN_REVIEW: 'processing',
  NEW: 'default',
  AI_GENERATED: 'processing',
  NEEDS_FACT_CHECK: 'warning',
  NEEDS_REVIEW: 'gold',
  APPROVED: 'blue',
  REJECTED: 'default',
  QUEUED: 'cyan',
  PUBLISHING: 'processing',
  PUBLISHED: 'success',
  CANCELLED: 'default',
  PUBLISH_FAILED: 'error',
  BLOCKED: 'error',
  DEFERRED: 'orange',
};

const RISK_COLORS: Record<string, string> = {
  low: 'success',
  medium: 'warning',
  high: 'error',
  blocked: 'error',
  unknown: 'default',
};

const RISK_LABELS: Record<string, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  blocked: '禁止参与',
  unknown: '未评估',
};

interface ReviewDraft {
  candidateId?: string | number;
  text: string;
  tone: string;
}

interface PolicyDraft {
  daily_write_limit?: number;
  hourly_write_limit?: number;
  max_interactions_per_user?: number;
  min_reply_interval_seconds?: number;
  duplicate_threshold?: number;
  paused_regions: string;
  paused_keywords: string;
  high_risk_topics: string;
  auto_reply_intents: string;
}

function normalizeStatus(value?: string): string {
  return (value || 'NEW').trim().toUpperCase();
}

function normalizeRisk(value?: string): string {
  const risk = (value || 'unknown').trim().toLowerCase();
  return RISK_LABELS[risk] ? risk : 'unknown';
}

function parseMaybeJson<T>(value: unknown, fallback: T): T {
  if (value == null) return fallback;
  if (typeof value !== 'string') return value as T;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function listFromResponse<T>(value: unknown, aliases: string[] = []): T[] {
  if (Array.isArray(value)) return value as T[];
  if (!value || typeof value !== 'object') return [];
  const record = value as Record<string, unknown>;
  if (Array.isArray(record.items)) return record.items as T[];
  for (const alias of aliases) {
    if (Array.isArray(record[alias])) return record[alias] as T[];
  }
  if (Array.isArray(record.data)) return record.data as T[];
  return [];
}

function listText(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const row = item as Record<string, unknown>;
          return String(row.summary || row.label || row.text || '');
        }
        return '';
      })
      .filter(Boolean);
  }
  if (typeof value === 'string') {
    const parsed = parseMaybeJson<unknown>(value, value);
    if (Array.isArray(parsed)) return listText(parsed);
    return value
      .split(/\n|；|;/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function errorDetail(error: unknown): string {
  const err = error as {
    response?: { data?: { detail?: unknown; message?: unknown }; status?: number };
    message?: string;
  };
  const detail = err?.response?.data?.detail ?? err?.response?.data?.message;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === 'string') return record.message;
    try {
      return JSON.stringify(detail);
    } catch {
      return '请求失败';
    }
  }
  return err?.message || '请求失败';
}

function formatDate(value?: string | number): string {
  if (!value) return '—';
  const timestamp = typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value;
  const parsed = dayjs(timestamp);
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : String(value);
}

function formatCount(value?: number): string {
  if (value == null || Number.isNaN(value)) return '—';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function formatPercentage(value?: number): string {
  if (value == null || Number.isNaN(value)) return '—';
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return `${normalized.toFixed(0)}%`;
}

async function sha256(value: string): Promise<string> {
  const canonical = value
    .replaceAll('\u200b', '')
    .replaceAll('\u200c', '')
    .replaceAll('\u200d', '')
    .replaceAll('\ufeff', '')
    .trim()
    .split(/\s+/)
    .join(' ');
  const bytes = new TextEncoder().encode(canonical);
  const digest = await window.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

function topicName(topic: XTopic): string {
  return topic.name || topic.topic_name || topic.raw_name || topic.normalized_name || `热点 ${topic.id}`;
}

function topicRegionName(topic: XTopic): string {
  if (topic.region && typeof topic.region === 'object') {
    return topic.region.name || `WOEID ${topic.region.woeid || '—'}`;
  }
  return topic.region_name || topic.region || `WOEID ${topic.woeid || '—'}`;
}

function topicLanguage(topic: XTopic): string {
  if (topic.language) return topic.language;
  return typeof topic.region === 'object' ? topic.region.language || '未标注' : '未标注';
}

function topicRank(topic: XTopic): number | undefined {
  return topic.rank ?? topic.latest_snapshot?.rank;
}

function topicRankChange(topic: XTopic): number | undefined {
  return topic.rank_change ?? topic.latest_snapshot?.rank_delta;
}

function topicVolume(topic: XTopic): number | undefined {
  return topic.volume ?? topic.post_count ?? topic.latest_snapshot?.post_volume ?? topic.latest_snapshot?.post_count_estimate;
}

function topicGrowth(topic: XTopic): number | undefined {
  if (topic.growth_rate != null) return topic.growth_rate;
  const volume = topic.latest_snapshot?.post_volume;
  const delta = topic.latest_snapshot?.volume_delta;
  if (volume == null || delta == null) return undefined;
  const previous = volume - delta;
  if (previous <= 0) return delta > 0 ? 1 : 0;
  return delta / previous;
}

function topicRisk(topic: XTopic): string {
  if (topic.risk_level) return topic.risk_level;
  if (topic.is_sensitive || (topic.risk_score || 0) >= 0.7) return 'high';
  if ((topic.risk_score || 0) >= 0.35) return 'medium';
  return 'low';
}

function postAuthorName(post?: XPost | null): string {
  return post?.author_name || post?.author_display_name || post?.author_username || '未知作者';
}

function postIdentifier(post?: XPost | null): string {
  if (!post) return '';
  return String(post.x_post_id || post.id || '');
}

function postLink(post?: XPost | null, fallbackPostId?: string): string {
  if (post?.post_url) return post.post_url;
  if (post?.url) return post.url;
  const id = postIdentifier(post) || fallbackPostId || '';
  return id ? `https://x.com/i/web/status/${id}` : 'https://x.com/';
}

function postMetrics(post?: XPost | null): XPublicMetrics {
  if (!post) return {};
  const raw = parseMaybeJson<XPublicMetrics>(post.public_metrics_json, {});
  return {
    like_count: post.like_count ?? post.public_metrics?.like_count ?? raw.like_count,
    reply_count: post.reply_count ?? post.public_metrics?.reply_count ?? raw.reply_count,
    retweet_count: post.retweet_count ?? post.public_metrics?.retweet_count ?? raw.retweet_count,
    quote_count: post.quote_count ?? post.public_metrics?.quote_count ?? raw.quote_count,
    impression_count: post.public_metrics?.impression_count ?? raw.impression_count,
  };
}

function candidateText(candidate?: XReplyCandidate): string {
  return candidate?.edited_text || candidate?.generated_text || candidate?.text || '';
}

function reviewCandidates(review: XReviewTask): XReplyCandidate[] {
  const candidates = parseMaybeJson<XReplyCandidate[]>(review.candidates, []);
  if (candidates.length) return candidates;
  if (review.candidate) return [review.candidate];
  const fallbackText = review.final_text || review.edited_text;
  if (!fallbackText) return [];
  return [{
    id: review.selected_candidate_id || `review-${review.id}`,
    text: fallbackText,
    content_hash: review.content_hash,
    risk_level: review.risk_level,
    requires_fact_check: review.requires_fact_check,
  }];
}

function reviewPost(review: XReviewTask): XPost | undefined {
  return review.target_post || review.post;
}

function reviewTargetId(review: XReviewTask): string {
  return review.target_post_id
    || postIdentifier(reviewPost(review))
    || (review.source_post_id != null ? String(review.source_post_id) : '');
}

function reviewAccountUsername(review: XReviewTask): string {
  return review.account_username || review.account?.username || '';
}

function reviewEligibilityReason(review: XReviewTask): string {
  if (review.eligibility_reason) return review.eligibility_reason;
  if (review.eligibility?.reason) return review.eligibility.reason;
  if (review.eligibility?.reasons?.length) return review.eligibility.reasons.join('；');
  return '';
}

function normalizeAnalysis(value?: XThreadAnalysis | null): XThreadAnalysis | null {
  if (!value) return null;
  const output = parseMaybeJson<Record<string, unknown>>(value.output_json, {});
  const sentimentPayload = parseMaybeJson<Record<string, unknown>>(value.sentiment_json, {});
  const storedViewpoints = listText(value.viewpoints_json);
  const outputViewpoints = listText(output.viewpoints || output.main_viewpoints);
  const riskItems = listText(value.risks_json || output.risks || output.misinformation_risks);
  const factItems = listText(output.disputed_facts || output.facts_to_verify);
  const outputRisk = String(output.risk_level || '').toLowerCase();
  const inferredRisk = outputRisk
    || (riskItems.length ? 'medium' : undefined);
  return {
    ...value,
    summary: value.summary || String(output.summary || ''),
    viewpoints: value.viewpoints
      || value.core_viewpoints
      || (storedViewpoints.length ? storedViewpoints : outputViewpoints),
    common_questions: value.common_questions || listText(output.common_questions),
    disputed_facts: value.disputed_facts || (factItems.length ? factItems : riskItems),
    recommended_action: value.recommended_action
      || value.recommended_participation
      || value.reply_recommendation
      || String(output.recommended_action || output.recommended_participation || output.reply_recommendation || ''),
    risk_level: value.risk_level || inferredRisk,
    sentiment: value.sentiment
      || String(
        sentimentPayload.label
        || sentimentPayload.sentiment
        || sentimentPayload.dominant_sentiment
        || output.sentiment
        || output.dominant_sentiment
        || '',
      ),
    sample_count: value.sample_count || Number(output.sample_count || 0) || undefined,
  };
}

function policyChecks(review: XReviewTask): XPolicyCheck[] {
  return parseMaybeJson<XPolicyCheck[]>(review.policy_checks, []);
}

function percentOf(value?: number, budget?: number): number {
  if (!budget || budget <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round(((value || 0) / budget) * 100)));
}

function splitControlList(value: string): string[] {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function policyDraftFromStatus(status: XAutomationStatus): PolicyDraft {
  return {
    daily_write_limit: status.daily_write_limit,
    hourly_write_limit: status.hourly_write_limit,
    max_interactions_per_user: status.max_interactions_per_user,
    min_reply_interval_seconds: status.min_reply_interval_seconds,
    duplicate_threshold: status.duplicate_threshold,
    paused_regions: (status.paused_regions || []).join('\n'),
    paused_keywords: (status.paused_keywords || []).join('\n'),
    high_risk_topics: (status.high_risk_topics || []).join('\n'),
    auto_reply_intents: (status.auto_reply_intents || []).join('\n'),
  };
}

function RiskTag({ risk }: { risk?: string }) {
  const normalized = normalizeRisk(risk);
  return <Tag color={RISK_COLORS[normalized]}>{RISK_LABELS[normalized]}</Tag>;
}

function ReviewStatusTag({ status }: { status?: string }) {
  const normalized = normalizeStatus(status);
  return (
    <Tag color={REVIEW_STATUS_COLORS[normalized] || 'default'}>
      {REVIEW_STATUS_LABELS[normalized] || normalized}
    </Tag>
  );
}

export default function XOperations() {
  const {
    token: {
      colorBgLayout,
      colorBorderSecondary,
      colorErrorBg,
      colorInfoBg,
      colorSuccessBg,
      colorTextSecondary,
      colorWarningBg,
    },
  } = theme.useToken();
  const [messageApi, messageContextHolder] = message.useMessage();
  const [modal, modalContextHolder] = Modal.useModal();

  const currentUser = useMemo(() => authStorage.getUser(), []);
  const canOperate = currentUser?.role !== 'viewer';
  const isAdmin = currentUser?.role === 'admin';

  const [activeTab, setActiveTab] = useState('radar');
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [topics, setTopics] = useState<XTopic[]>([]);
  const [posts, setPosts] = useState<XPost[]>([]);
  const [reviews, setReviews] = useState<XReviewTask[]>([]);
  const [accounts, setAccounts] = useState<XAccount[]>([]);
  const [auditLogs, setAuditLogs] = useState<XAuditLog[]>([]);
  const [usage, setUsage] = useState<XUsageSummary>({});
  const [automation, setAutomation] = useState<XAutomationStatus>(SAFE_AUTOMATION_DEFAULTS);
  const [policyDraft, setPolicyDraft] = useState<PolicyDraft>(policyDraftFromStatus(SAFE_AUTOMATION_DEFAULTS));
  const [topicSearch, setTopicSearch] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState<string | number>();
  const [selectedAccountId, setSelectedAccountId] = useState<string | number>();
  const [postSearch, setPostSearch] = useState('');
  const [reviewStatus, setReviewStatus] = useState('ALL');
  const [selectedPost, setSelectedPost] = useState<XPost | null>(null);
  const [conversation, setConversation] = useState<XConversation | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, ReviewDraft>>({});

  const loadAll = useCallback(async (showSpinner = false) => {
    if (showSpinner) setInitialLoading(true);
    setRefreshing(true);
    const results = await Promise.allSettled([
      getXTopics({ limit: 100 }),
      getXPosts({ limit: 100 }),
      getXReviews({ limit: 100 }),
      getXAutomationStatus(),
      getXAccounts(),
      getXUsage(),
      getXAuditLogs({ limit: 50 }),
    ]);

    const errors: string[] = [];
    const labels = ['热点', '帖子', '审核队列', '安全状态', '账号', '预算', '审计日志'];
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        errors.push(`${labels[index]}：${errorDetail(result.reason)}`);
      }
    });

    if (results[0].status === 'fulfilled') {
      setTopics(listFromResponse<XTopic>(results[0].value, ['topics']));
    }
    if (results[1].status === 'fulfilled') {
      setPosts(listFromResponse<XPost>(results[1].value, ['posts']));
    }
    if (results[2].status === 'fulfilled') {
      setReviews(listFromResponse<XReviewTask>(results[2].value, ['reviews']));
    }
    if (results[3].status === 'fulfilled') {
      const raw = results[3].value as XAutomationStatus & { status?: XAutomationStatus; controls?: XAutomationStatus };
      const next = raw.status || raw.controls || raw;
      const safeStatus: XAutomationStatus = {
        ...SAFE_AUTOMATION_DEFAULTS,
        ...next,
        credentials: next.credentials || {},
        reasons: next.reasons || [],
      };
      setAutomation(safeStatus);
      setPolicyDraft(policyDraftFromStatus(safeStatus));
    } else {
      setAutomation(SAFE_AUTOMATION_DEFAULTS);
      setPolicyDraft(policyDraftFromStatus(SAFE_AUTOMATION_DEFAULTS));
    }
    if (results[4].status === 'fulfilled') {
      const nextAccounts = listFromResponse<XAccount>(results[4].value, ['accounts']);
      setAccounts(nextAccounts);
      setSelectedAccountId((previous) => {
        if (previous != null && nextAccounts.some((account) => String(account.id) === String(previous))) {
          return previous;
        }
        return nextAccounts.find((account) => account.status === 'active')?.id
          ?? nextAccounts[0]?.id;
      });
    }
    if (results[5].status === 'fulfilled') {
      const raw = results[5].value as XUsageSummary & {
        usage_date?: string;
        summary?: XUsageSummary & { read_resource_count?: number };
        items?: XEndpointUsage[];
        budgets?: {
          post_reads?: number;
          user_reads?: number;
          writes?: number;
          post_reads_status?: { exhausted?: boolean };
          writes_status?: { exhausted?: boolean };
        };
        rate_limits?: Array<{
          endpoint?: string;
          limit_total?: number;
          remaining?: number;
          reset_at?: string | number;
        }>;
      };
      const summary = raw.summary || {};
      const usageItems = raw.endpoints || raw.endpoint_usage || raw.items || [];
      const rateLimits = raw.rate_limits || [];
      const enrichedItems = usageItems.map((item) => {
        const rate = rateLimits.find((candidate) => candidate.endpoint === item.endpoint);
        return {
          ...item,
          limit: item.limit ?? rate?.limit_total,
          remaining: item.remaining ?? rate?.remaining,
          reset_at: item.reset_at ?? rate?.reset_at,
        };
      });
      const postReads = usageItems
        .filter((item) => !String(item.endpoint || '').includes('/users'))
        .reduce((total, item) => total + Number(item.read_resource_count ?? item.read_count ?? 0), 0);
      const userReads = usageItems
        .filter((item) => String(item.endpoint || '').includes('/users'))
        .reduce((total, item) => total + Number(item.read_resource_count ?? item.read_count ?? 0), 0);
      const estimatedCost = usageItems.reduce(
        (total, item) => total + Number(item.estimated_cost ?? ((item.estimated_cost_micros || 0) / 1_000_000)),
        0,
      );
      setUsage({
        ...raw,
        ...summary,
        date: raw.date || raw.usage_date,
        post_reads: raw.post_reads ?? postReads,
        user_reads: raw.user_reads ?? userReads,
        writes: raw.writes ?? summary.write_count,
        post_read_budget: raw.post_read_budget ?? raw.budgets?.post_reads,
        user_read_budget: raw.user_read_budget ?? raw.budgets?.user_reads,
        write_budget: raw.write_budget ?? raw.budgets?.writes,
        estimated_cost: raw.estimated_cost ?? estimatedCost,
        forced_read_only: raw.forced_read_only
          ?? Boolean(raw.budgets?.post_reads_status?.exhausted || raw.budgets?.writes_status?.exhausted),
        endpoints: enrichedItems,
      });
    }
    if (results[6].status === 'fulfilled') {
      setAuditLogs(listFromResponse<XAuditLog>(results[6].value, ['logs', 'audit_logs']));
    }

    setLoadErrors(Array.from(new Set(errors)));
    setInitialLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      void loadAll(true);
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [loadAll]);

  const runAction = async (
    key: string,
    action: () => Promise<unknown>,
    successMessage: string,
    refreshAfter = true,
  ) => {
    setActionLoading(key);
    try {
      const result = await action() as { message?: string };
      messageApi.success(result?.message || successMessage);
      if (refreshAfter) await loadAll(false);
      return result;
    } catch (error) {
      messageApi.error(errorDetail(error));
      return null;
    } finally {
      setActionLoading('');
    }
  };

  const loadPostsForTopic = async (topic?: XTopic) => {
    const topicId = topic?.id;
    setSelectedTopicId(topicId);
    setActiveTab('posts');
    setActionLoading(`topic-posts-${topicId}`);
    try {
      const response = await getXPosts({ topic_id: topicId, limit: 100 });
      setPosts(listFromResponse<XPost>(response, ['posts']));
      setSelectedPost(null);
      setConversation(null);
    } catch (error) {
      messageApi.error(errorDetail(error));
    } finally {
      setActionLoading('');
    }
  };

  const loadConversation = async (post: XPost) => {
    setSelectedPost(post);
    setConversation(null);
    const rootPostId = post.conversation_id || postIdentifier(post);
    if (!rootPostId) return;
    setConversationLoading(true);
    try {
      const response = await getXConversation(rootPostId);
      const raw = response as XConversation & { conversation?: Record<string, unknown> };
      setConversation({
        ...raw,
        root_post: raw.root_post || post,
        posts: listFromResponse<XPost>(raw.posts, ['posts']),
        analysis: normalizeAnalysis(raw.analysis),
      });
    } catch {
      setConversation({ root_post: post, posts: [], replies: [], analysis: null });
      messageApi.info('该帖子尚未采集线程，可先执行“采集线程”');
    } finally {
      setConversationLoading(false);
    }
  };

  const handleAnalyze = async (post: XPost) => {
    const rootPostId = post.conversation_id || postIdentifier(post);
    if (!rootPostId) return;
    const result = await runAction(
      `analyze-${postIdentifier(post)}`,
      () => analyzeXConversation(rootPostId),
      '线程分析任务已提交',
      false,
    ) as ({ analysis?: XThreadAnalysis } & Partial<XThreadAnalysis>) | null;
    if (!result) return;
    const analysis = result.analysis || (result.root_post_id ? result as XThreadAnalysis : undefined);
    if (analysis) {
      setConversation((previous) => ({
        ...(previous || { root_post: post, posts: [] }),
        analysis: normalizeAnalysis(analysis),
      }));
    } else {
      await loadConversation(post);
    }
  };

  const handleCollectThread = async (post: XPost) => {
    const result = await runAction(
      `collect-${postIdentifier(post)}`,
      () => collectXThread(post.conversation_id || post.id),
      '线程采集完成',
      false,
    ) as (XConversation & { conversation?: Record<string, unknown> }) | null;
    if (!result) return;
    setSelectedPost(post);
    setConversation({
      ...result,
      root_post: post,
      posts: listFromResponse<XPost>(result.posts, ['posts']),
      analysis: normalizeAnalysis(result.analysis),
    });
  };

  const handleGenerate = async (post: XPost) => {
    if (selectedAccountId == null) {
      messageApi.warning('请先在“账号与预算”中绑定 X 账号，再生成账号语气相关的回复草稿');
      setActiveTab('accounts');
      return;
    }
    const result = await runAction(
      `generate-${postIdentifier(post)}`,
      () => generateXReplyCandidates(post.id, {
        account_id: selectedAccountId,
        candidate_count: 3,
      }),
      '已生成 3 条候选并进入审核队列',
    );
    if (result) setActiveTab('reviews');
  };

  const getReviewDraft = (review: XReviewTask): ReviewDraft => {
    const key = String(review.id);
    const existing = reviewDrafts[key];
    if (existing) return existing;
    const candidates = reviewCandidates(review);
    const selected = candidates.find((candidate) => String(candidate.id) === String(review.selected_candidate_id))
      || candidates[0];
    return {
      candidateId: selected?.id,
      text: review.final_text || review.edited_text || candidateText(selected),
      tone: review.tone || selected?.style || 'informative',
    };
  };

  const updateReviewDraft = (review: XReviewTask, patch: Partial<ReviewDraft>) => {
    const key = String(review.id);
    setReviewDrafts((previous) => ({
      ...previous,
      [key]: {
        ...getReviewDraft(review),
        ...patch,
      },
    }));
  };

  const handleApprove = async (review: XReviewTask) => {
    const draft = getReviewDraft(review);
    if (!draft.text.trim()) {
      messageApi.warning('审核文本不能为空');
      return;
    }
    if (draft.candidateId == null) {
      messageApi.warning('请选择要批准的候选版本');
      return;
    }
    const finalText = draft.text.trim();
    const finalContentHash = await sha256(finalText);
    await runAction(
      `approve-${review.id}`,
      () => approveXReview(review.id, {
        candidate_id: draft.candidateId!,
        final_text: finalText,
        content_hash: finalContentHash,
        explicit_confirmation: true,
      }),
      '审核已批准',
    );
  };

  const showRejectDialog = (review: XReviewTask) => {
    let reason = '';
    modal.confirm({
      title: '确认拒绝这条回复',
      icon: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
      content: (
        <div style={{ marginTop: 16 }}>
          <Paragraph type="secondary">
            拒绝只影响当前审核任务，不会向 X 发布任何内容。
          </Paragraph>
          <TextArea
            rows={3}
            placeholder="请输入拒绝原因（必填）"
            onChange={(event) => { reason = event.target.value; }}
          />
        </div>
      ),
      okText: '确认拒绝',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (!reason.trim()) {
          messageApi.warning('请输入拒绝原因');
          return Promise.reject();
        }
        const result = await runAction(
          `reject-${review.id}`,
          () => rejectXReview(review.id, {
            reason: reason.trim(),
          }),
          '审核已拒绝',
        );
        if (!result) return Promise.reject();
      },
    });
  };

  const handlePublish = async (review: XReviewTask) => {
    const draft = getReviewDraft(review);
    if (draft.candidateId == null) {
      messageApi.warning('缺少已批准的候选版本');
      return;
    }
    const approvedHash = review.final_content_hash
      || await sha256(review.final_text || draft.text.trim());
    await runAction(
      `publish-${review.id}`,
      () => publishXReview(review.id, {
        candidate_id: draft.candidateId!,
        content_hash: approvedHash,
        explicit_confirmation: true,
        publish_mode: 'manual_review',
      }),
      '单条回复已进入发布流程',
    );
  };

  const copyDraft = async (review: XReviewTask) => {
    const text = getReviewDraft(review).text || review.manual_fallback?.copy_text || '';
    if (!text) {
      messageApi.warning('没有可复制的草稿');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      messageApi.success('草稿已复制');
    } catch {
      messageApi.error('浏览器拒绝访问剪贴板，请手动复制');
    }
  };

  const openOriginalPost = (review: XReviewTask) => {
    window.open(
      review.manual_fallback?.post_url || postLink(reviewPost(review), reviewTargetId(review)),
      '_blank',
      'noopener,noreferrer',
    );
  };

  const confirmControlChange = (
    field: keyof XAutomationStatus,
    value: boolean,
    title: string,
    description: string,
    danger = false,
  ) => {
    modal.confirm({
      title,
      content: description,
      okText: '确认变更',
      cancelText: '取消',
      okButtonProps: { danger },
      onOk: async () => {
        const result = await runAction(
          `control-${String(field)}`,
          () => updateXAutomationControls({ [field]: value }),
          '自动化控制已更新',
        );
        if (!result) return Promise.reject();
      },
    });
  };

  const savePolicyControls = async () => {
    await runAction(
      'save-policy',
      () => updateXAutomationControls({
        daily_write_limit: policyDraft.daily_write_limit,
        hourly_write_limit: policyDraft.hourly_write_limit,
        max_interactions_per_user: policyDraft.max_interactions_per_user,
        min_reply_interval_seconds: policyDraft.min_reply_interval_seconds,
        duplicate_threshold: policyDraft.duplicate_threshold,
        paused_regions: splitControlList(policyDraft.paused_regions),
        paused_keywords: splitControlList(policyDraft.paused_keywords),
        high_risk_topics: splitControlList(policyDraft.high_risk_topics),
        auto_reply_intents: splitControlList(policyDraft.auto_reply_intents),
      }),
      '发布策略已保存',
    );
  };

  const handleOAuth = async () => {
    setActionLoading('oauth');
    try {
      const response = await startXOAuth();
      const url = response.authorization_url || response.url;
      if (!url) throw new Error('后端未返回 X 授权地址');
      window.location.assign(url);
    } catch (error) {
      messageApi.error(errorDetail(error));
      setActionLoading('');
    }
  };

  const confirmAccountToggle = (
    account: XAccount,
    field: 'write_enabled' | 'auto_reply_enabled' | 'automated_label_enabled',
    value: boolean,
    label: string,
  ) => {
    modal.confirm({
      title: `确认${value ? '开启' : '关闭'}账号“${label}”？`,
      content: (
        field === 'write_enabled' && value
          ? '开启账号写入后仍不会自动发布；每条人工回复必须单独审核、确认，并通过发送前实时检查。'
          : field === 'auto_reply_enabled' && value
            ? '自动回复还必须满足 X 书面批准、自动账号标签、用户主动互动和全局白名单。'
            : `此变更只作用于 @${account.username || account.id}。`
      ),
      okText: '确认变更',
      cancelText: '取消',
      okButtonProps: { danger: value && field !== 'automated_label_enabled' },
      onOk: async () => {
        const result = await runAction(
          `account-${field}-${account.id}`,
          () => updateXAccount(account.id, { [field]: value }),
          `账号${label}已更新`,
        );
        if (!result) return Promise.reject();
      },
    });
  };

  const showApprovalEvidenceDialog = (account: XAccount) => {
    let reference = account.approval_reference || '';
    modal.confirm({
      title: '录入 X 书面批准证据',
      content: (
        <div style={{ marginTop: 16 }}>
          <Alert
            type="warning"
            showIcon
            message="仅在确实取得 X 书面批准后录入"
            description="可填写工单号、批准邮件编号或内部受控附件引用，不要粘贴 Token 或其他密钥。"
            style={{ marginBottom: 12 }}
          />
          <TextArea
            rows={4}
            defaultValue={reference}
            placeholder="例如：X Developer Support ticket #..."
            onChange={(event) => { reference = event.target.value; }}
          />
        </div>
      ),
      okText: '确认保存',
      cancelText: '取消',
      onOk: async () => {
        if (reference.trim().length < 3) {
          messageApi.warning('批准证据引用至少需要 3 个字符');
          return Promise.reject();
        }
        const result = await runAction(
          `account-approval-${account.id}`,
          () => saveXAccountApprovalEvidence(account.id, {
            approval_reference: reference.trim(),
            x_written_approval: true,
          }),
          'X 批准证据已记录',
        );
        if (!result) return Promise.reject();
      },
    });
  };

  const filteredTopics = useMemo(() => {
    const keyword = topicSearch.trim().toLowerCase();
    if (!keyword) return topics;
    return topics.filter((topic) => [
      topic.name,
      topic.topic_name,
      topic.raw_name,
      topic.normalized_name,
      topic.region_name,
      topicRegionName(topic),
      topic.summary,
    ].some((value) => String(value || '').toLowerCase().includes(keyword)));
  }, [topicSearch, topics]);

  const filteredPosts = useMemo(() => {
    const keyword = postSearch.trim().toLowerCase();
    if (!keyword) return posts;
    return posts.filter((post) => [
      post.text,
      post.author_name,
      post.author_display_name,
      post.author_username,
      post.topic_name,
    ].some((value) => String(value || '').toLowerCase().includes(keyword)));
  }, [postSearch, posts]);

  const filteredReviews = useMemo(() => {
    if (reviewStatus === 'ALL') return reviews;
    return reviews.filter((review) => normalizeStatus(review.status || review.review_status) === reviewStatus);
  }, [reviewStatus, reviews]);

  const pendingReviewCount = useMemo(() => reviews.filter((review) => {
    const status = normalizeStatus(review.status || review.review_status);
    return ['PENDING', 'IN_REVIEW', 'NEW', 'AI_GENERATED', 'NEEDS_FACT_CHECK', 'NEEDS_REVIEW', 'PUBLISH_FAILED'].includes(status);
  }).length, [reviews]);

  const effectiveWriteAllowed = Boolean(
    automation.effective_write_allowed
    ?? (automation.write_enabled && !automation.global_kill_switch),
  );
  const hasWrittenApproval = accounts.some((account) => (
    account.x_written_approval && account.automated_label_enabled
  ));
  const hasWriteToken = accounts.some((account) => (
    account.token_configured && !account.token_expired
  ));
  const draftEngineAvailable = Boolean(
    automation.credentials?.llm || automation.credentials?.fallback_drafts_available,
  );

  const automationReasons = automation.reasons || [];
  const endpointUsage = usage.endpoints || usage.endpoint_usage || [];
  const recentErrors = [
    ...(usage.recent_errors || []),
    ...auditLogs.filter((log) => (
      (log.http_status || 0) >= 400
      || ['FAILED', 'ERROR', 'BLOCKED'].includes(normalizeStatus(log.status || log.outcome))
      || Boolean(log.error_code)
    )),
  ].slice(0, 10);

  const analysis = conversation?.analysis || null;
  const threadPosts = [
    ...(conversation?.posts || []),
    ...(conversation?.replies || []),
  ].filter((post, index, all) => (
    postIdentifier(post) !== postIdentifier(selectedPost)
    && all.findIndex((item) => postIdentifier(item) === postIdentifier(post)) === index
  ));

  const safetyAlertType = automation.global_kill_switch
    ? 'error'
    : effectiveWriteAllowed
      ? 'warning'
      : 'info';
  const safetyAlertTitle = automation.global_kill_switch
    ? 'Kill Switch 已开启：全部 X 写入被停止'
    : effectiveWriteAllowed
      ? 'X 写入已开启：每次发布仍需单条明确确认'
      : '当前为只读模式：不会向 X 发布内容';

  const tabItems = [
    {
      key: 'radar',
      label: (
        <Space size={6}>
          <GlobalOutlined />
          热点雷达
        </Space>
      ),
      children: (
        <div>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Row gutter={[12, 12]} justify="space-between" align="middle">
              <Col xs={24} md={14}>
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索热点、地域或摘要"
                  value={topicSearch}
                  onChange={(event) => setTopicSearch(event.target.value)}
                />
              </Col>
              <Col>
                <Popconfirm
                  title="确认从 X 刷新热点？"
                  description="使用专用 Chrome/CDP 会话读取 X 页面，并计入每日采集数量上限。"
                  okText="确认刷新"
                  cancelText="取消"
                  onConfirm={() => runAction('refresh-topics', () => refreshXTopics(), '热点刷新任务已提交')}
                >
                  <Button
                    type="primary"
                    icon={<SyncOutlined />}
                    loading={actionLoading === 'refresh-topics'}
                    disabled={!canOperate || !automation.read_enabled}
                  >
                    从 X 刷新
                  </Button>
                </Popconfirm>
              </Col>
            </Row>
          </Card>

          <Table<XTopic>
            rowKey={(record) => String(record.id)}
            dataSource={filteredTopics}
            locale={{ emptyText: <Empty description="暂无热点数据，可在只读能力配置完成后刷新" /> }}
            scroll={{ x: 1280 }}
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 个热点` }}
            columns={[
              {
                title: '热点',
                key: 'topic',
                width: 220,
                fixed: 'left',
                render: (_, record) => (
                  <div>
                    <Text strong>{topicName(record)}</Text>
                    {record.representative_post && (
                      <Paragraph
                        type="secondary"
                        ellipsis={{ rows: 2 }}
                        style={{ margin: '4px 0 0', fontSize: 12, maxWidth: 260 }}
                      >
                        {record.representative_post}
                      </Paragraph>
                    )}
                  </div>
                ),
              },
              {
                title: '地域 / 语言',
                key: 'region',
                width: 130,
                render: (_, record) => (
                  <Space direction="vertical" size={2}>
                    <Text>{topicRegionName(record)}</Text>
                    <Text type="secondary">{topicLanguage(record)}</Text>
                  </Space>
                ),
              },
              {
                title: '排名',
                key: 'rank',
                width: 100,
                render: (_, record) => (
                  <Space direction="vertical" size={2}>
                    <Text strong>#{topicRank(record) ?? '—'}</Text>
                    {topicRankChange(record) != null && (
                      <Text type={(topicRankChange(record) || 0) >= 0 ? 'success' : 'danger'}>
                        {(topicRankChange(record) || 0) >= 0 ? '↑' : '↓'} {Math.abs(topicRankChange(record) || 0)}
                      </Text>
                    )}
                  </Space>
                ),
              },
              {
                title: '讨论量 / 增速',
                key: 'volume',
                width: 140,
                render: (_, record) => (
                  <Space direction="vertical" size={2}>
                    <Text>{formatCount(topicVolume(record))}</Text>
                    <Text type={(topicGrowth(record) || 0) >= 0 ? 'success' : 'danger'}>
                      {topicGrowth(record) == null ? '增速 —' : `${(topicGrowth(record) || 0) >= 0 ? '+' : ''}${formatPercentage(topicGrowth(record))}`}
                    </Text>
                  </Space>
                ),
              },
              {
                title: '核心观点',
                key: 'insight',
                width: 300,
                render: (_, record) => {
                  const viewpoints = listText(record.core_viewpoints);
                  return (
                    <div>
                      <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: viewpoints.length ? 6 : 0 }}>
                        {record.summary || '尚未生成热点摘要'}
                      </Paragraph>
                      {viewpoints.slice(0, 2).map((item) => (
                        <Tag key={item} style={{ marginBottom: 4 }}>{item}</Tag>
                      ))}
                    </div>
                  );
                },
              },
              {
                title: '倾向 / 风险',
                key: 'risk',
                width: 140,
                render: (_, record) => (
                  <Space direction="vertical" size={4}>
                    <Tag>{record.sentiment || '未分析'}</Tag>
                    <RiskTag risk={topicRisk(record)} />
                  </Space>
                ),
              },
              {
                title: '品牌相关度',
                key: 'brand_relevance',
                width: 120,
                render: (_, record) => {
                  const value = record.brand_relevance ?? record.relevance_score;
                  return (
                    <Progress
                      percent={value == null ? 0 : (Math.abs(value) <= 1 ? Math.round(value * 100) : Math.round(value))}
                      size="small"
                      format={(percent) => value == null ? '—' : `${percent}%`}
                    />
                  );
                },
              },
              {
                title: '采集来源',
                key: 'cost',
                width: 100,
                render: () => (
                  <Tooltip title="热点、帖子和评论均由 Playwright/CDP 浏览器采集，不调用 X Official API Read operations">
                    <Tag color="blue">浏览器</Tag>
                  </Tooltip>
                ),
              },
              {
                title: '操作',
                key: 'actions',
                fixed: 'right',
                width: 200,
                render: (_, record) => (
                  <Space>
                    <Button
                      type="link"
                      icon={<EyeOutlined />}
                      loading={actionLoading === `topic-posts-${record.id}`}
                      onClick={() => void loadPostsForTopic(record)}
                    >
                      查看
                    </Button>
                    <Popconfirm
                      title="确认采集该热点的相关帖子？"
                      description="默认最多从 X 搜索页采集 50 条近期帖子，并计入每日采集数量上限。"
                      okText="确认采集"
                      cancelText="取消"
                      onConfirm={() => runAction(
                        `collect-topic-${record.id}`,
                        () => collectXTopicPosts(record.id, { max_posts: 50 }),
                        '热点相关帖子采集完成',
                      )}
                    >
                      <Button
                        type="link"
                        icon={<SyncOutlined />}
                        disabled={!canOperate || !automation.read_enabled}
                        loading={actionLoading === `collect-topic-${record.id}`}
                      >
                        采集帖子
                      </Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </div>
      ),
    },
    {
      key: 'posts',
      label: (
        <Space size={6}>
          <CommentOutlined />
          线程分析 / 帖子
        </Space>
      ),
      children: (
        <div>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Row gutter={[12, 12]} align="middle">
              <Col xs={24} md={10}>
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索帖子、作者或热点"
                  value={postSearch}
                  onChange={(event) => setPostSearch(event.target.value)}
                />
              </Col>
              <Col xs={24} md={8}>
                <Select
                  style={{ width: '100%' }}
                  placeholder="选择生成回复的 X 账号"
                  value={selectedAccountId}
                  onChange={setSelectedAccountId}
                  options={accounts.map((account) => ({
                    value: account.id,
                    label: `${account.display_name || account.username || `账号 ${account.id}`}${account.username ? ` (@${account.username})` : ''}`,
                    disabled: account.status != null && account.status !== 'active',
                  }))}
                  notFoundContent="请先绑定 X 账号"
                />
                <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
                  {automation.credentials?.llm
                    ? '使用已配置的 LLM 生成，结果仍需人工审核'
                    : automation.credentials?.fallback_drafts_available
                      ? 'LLM 未配置：使用本地安全草稿，结果仍需人工审核'
                      : '草稿生成服务尚未配置'}
                </Text>
              </Col>
              <Col>
                {selectedTopicId != null && (
                  <Tag closable onClose={() => {
                    setSelectedTopicId(undefined);
                    void getXPosts({ limit: 100 })
                      .then((response) => setPosts(listFromResponse<XPost>(response, ['posts'])))
                      .catch((error) => messageApi.error(errorDetail(error)));
                  }}>
                    已按热点筛选：{String(selectedTopicId)}
                  </Tag>
                )}
              </Col>
            </Row>
          </Card>

          <Table<XPost>
            rowKey={(record) => postIdentifier(record)}
            dataSource={filteredPosts}
            locale={{ emptyText: <Empty description="暂无帖子数据，请先从热点雷达采集" /> }}
            scroll={{ x: 1150 }}
            pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (total) => `共 ${total} 条帖子` }}
            onRow={(record) => ({
              onClick: () => void loadConversation(record),
              style: { cursor: 'pointer' },
            })}
            columns={[
              {
                title: '作者',
                key: 'author',
                width: 150,
                render: (_, record) => (
                  <Space direction="vertical" size={0}>
                    <Text strong>{postAuthorName(record)}</Text>
                    {record.author_username && <Text type="secondary">@{record.author_username}</Text>}
                  </Space>
                ),
              },
              {
                title: '帖子',
                dataIndex: 'text',
                width: 420,
                render: (value: string, record) => (
                  <div>
                    <Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 4 }}>
                      {value || '帖子正文已删除或尚未同步'}
                    </Paragraph>
                    <Space size={4} wrap>
                      {record.topic_name && <Tag>{record.topic_name}</Tag>}
                      {record.lang && <Tag>{record.lang}</Tag>}
                      {record.possibly_sensitive && <Tag color="error">敏感标记</Tag>}
                    </Space>
                  </div>
                ),
              },
              {
                title: '互动',
                key: 'metrics',
                width: 180,
                render: (_, record) => {
                  const metrics = postMetrics(record);
                  return (
                    <Space size={10} wrap>
                      <Tooltip title="回复"><span>💬 {formatCount(metrics.reply_count)}</span></Tooltip>
                      <Tooltip title="喜欢"><span>♥ {formatCount(metrics.like_count)}</span></Tooltip>
                      <Tooltip title="转发"><span>↻ {formatCount(metrics.retweet_count)}</span></Tooltip>
                    </Space>
                  );
                },
              },
              {
                title: '风险',
                dataIndex: 'risk_level',
                width: 100,
                render: (value: string) => <RiskTag risk={value} />,
              },
              {
                title: '发布时间',
                key: 'created_at',
                width: 150,
                render: (_, record) => formatDate(record.created_at_x || record.created_at),
              },
              {
                title: '操作',
                key: 'actions',
                fixed: 'right',
                width: 280,
                onCell: () => ({ onClick: (event) => event.stopPropagation() }),
                render: (_, record) => (
                  <Space wrap>
                    <Popconfirm
                      title="确认采集该帖子线程？"
                      description="会通过浏览器展开原帖页面并采集可见回复。"
                      okText="确认采集"
                      cancelText="取消"
                      onConfirm={() => handleCollectThread(record)}
                    >
                      <Button
                        size="small"
                        icon={<MessageOutlined />}
                        disabled={!canOperate || !automation.read_enabled}
                        loading={actionLoading === `collect-${postIdentifier(record)}`}
                      >
                        采集
                      </Button>
                    </Popconfirm>
                    <Popconfirm
                      title="确认执行 AI 线程分析？"
                      description="系统只分析已采集数据，不会向 X 发布。"
                      okText="确认分析"
                      cancelText="取消"
                      onConfirm={() => handleAnalyze(record)}
                    >
                      <Button
                        size="small"
                        icon={<BarChartOutlined />}
                        disabled={!canOperate}
                        loading={actionLoading === `analyze-${postIdentifier(record)}`}
                      >
                        分析
                      </Button>
                    </Popconfirm>
                    <Popconfirm
                      title="确认生成 3 条 AI 回复草稿？"
                      description="草稿只进入人工审核队列，不会自动发布。"
                      okText="确认生成"
                      cancelText="取消"
                      onConfirm={() => handleGenerate(record)}
                    >
                      <Button
                        size="small"
                        type="primary"
                        ghost
                        icon={<RobotOutlined />}
                        disabled={!canOperate || !draftEngineAvailable || selectedAccountId == null}
                        loading={actionLoading === `generate-${postIdentifier(record)}`}
                      >
                        生成回复
                      </Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />

          <Divider />
          <Spin spinning={conversationLoading}>
            {!selectedPost ? (
              <Empty description="选择一条帖子查看线程与 AI 分析" />
            ) : (
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={13}>
                  <Card
                    title="原帖与回复线程"
                    extra={(
                      <Button
                        type="link"
                        icon={<ExportOutlined />}
                        onClick={() => window.open(postLink(selectedPost), '_blank', 'noopener,noreferrer')}
                      >
                        打开 X 原帖
                      </Button>
                    )}
                  >
                    <Card size="small" style={{ background: colorBgLayout, marginBottom: 12 }}>
                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        <Text strong>
                          {postAuthorName(selectedPost)}
                          {selectedPost.author_username ? ` @${selectedPost.author_username}` : ''}
                        </Text>
                        <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                          {selectedPost.text || '原帖正文已删除或尚未同步'}
                        </Paragraph>
                        <Text type="secondary">{formatDate(selectedPost.created_at_x || selectedPost.created_at)}</Text>
                      </Space>
                    </Card>
                    {threadPosts.length ? (
                      <List
                        size="small"
                        dataSource={threadPosts}
                        renderItem={(post) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<UserOutlined style={{ marginTop: 5 }} />}
                              title={(
                                <Space wrap>
                                  <Text strong>{postAuthorName(post)}</Text>
                                  {post.author_username && <Text type="secondary">@{post.author_username}</Text>}
                                  <Tag>{post.analysis_status || '样本'}</Tag>
                                </Space>
                              )}
                              description={(
                                <div>
                                  <Paragraph style={{ margin: '4px 0' }}>{post.text || '内容不可用'}</Paragraph>
                                  <Text type="secondary">{formatDate(post.created_at_x || post.created_at)}</Text>
                                </div>
                              )}
                            />
                          </List.Item>
                        )}
                      />
                    ) : (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未采集回复线程" />
                    )}
                  </Card>
                </Col>
                <Col xs={24} xl={11}>
                  <Card
                    title="AI 线程分析"
                    extra={analysis?.model_version ? <Tag>{analysis.model_version}</Tag> : null}
                  >
                    {!analysis ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未生成分析结果" />
                    ) : (
                      <Space direction="vertical" size={16} style={{ width: '100%' }}>
                        <div>
                          <Text strong>摘要</Text>
                          <Paragraph style={{ marginTop: 6 }}>{analysis.summary || '暂无摘要'}</Paragraph>
                        </div>
                        <div>
                          <Text strong>主要观点</Text>
                          <List
                            size="small"
                            dataSource={listText(analysis.viewpoints || analysis.core_viewpoints)}
                            locale={{ emptyText: '暂无观点聚类' }}
                            renderItem={(item) => <List.Item>• {item}</List.Item>}
                          />
                        </div>
                        <div>
                          <Text strong>常见问题</Text>
                          <Space wrap style={{ marginTop: 8 }}>
                            {listText(analysis.common_questions).length
                              ? listText(analysis.common_questions).map((item) => <Tag key={item}>{item}</Tag>)
                              : <Text type="secondary">暂无</Text>}
                          </Space>
                        </div>
                        <div>
                          <Text strong>争议事实</Text>
                          <List
                            size="small"
                            dataSource={listText(analysis.disputed_facts)}
                            locale={{ emptyText: '暂无待核验争议事实' }}
                            renderItem={(item) => <List.Item><WarningOutlined style={{ color: '#faad14' }} /> {item}</List.Item>}
                          />
                        </div>
                        <Alert
                          type={normalizeRisk(analysis.risk_level) === 'high' ? 'warning' : 'info'}
                          showIcon
                          message="推荐参与方式"
                          description={analysis.recommended_action || analysis.recommended_participation || '建议运营人员结合品牌语气人工判断'}
                        />
                        <Space>
                          <RiskTag risk={analysis.risk_level} />
                          <Tag>{analysis.sentiment || '情绪未标注'}</Tag>
                          <Tag>样本 {analysis.sample_count ?? threadPosts.length}</Tag>
                        </Space>
                      </Space>
                    )}
                  </Card>
                </Col>
              </Row>
            )}
          </Spin>
        </div>
      ),
    },
    {
      key: 'reviews',
      label: (
        <Space size={6}>
          <SafetyCertificateOutlined />
          审核队列
          {pendingReviewCount > 0 && <Badge count={pendingReviewCount} size="small" />}
        </Space>
      ),
      children: (
        <div>
          <Alert
            type="info"
            showIcon
            message="单条审核、单条发布"
            description="本页面不提供批量批准或批量发布。编辑文本后必须重新批准；发布时再次校验 Kill Switch、账号权限、浏览器中的目标帖子、内容哈希与写入预算。"
            style={{ marginBottom: 16 }}
          />
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space wrap>
              <Text>状态筛选：</Text>
              <Select
                value={reviewStatus}
                style={{ minWidth: 170 }}
                onChange={setReviewStatus}
                options={[
                  { value: 'ALL', label: '全部状态' },
                  ...Object.entries(REVIEW_STATUS_LABELS).map(([value, label]) => ({ value, label })),
                ]}
              />
              <Button icon={<ReloadOutlined />} onClick={() => void loadAll(false)} loading={refreshing}>
                刷新队列
              </Button>
            </Space>
          </Card>

          <List
            dataSource={filteredReviews}
            locale={{ emptyText: <Empty description="暂无待审核回复" /> }}
            renderItem={(review) => {
              const draft = getReviewDraft(review);
              const candidates = reviewCandidates(review);
              const status = normalizeStatus(review.status || review.review_status);
              const post = reviewPost(review);
              const checks = policyChecks(review);
              const selectedCandidate = candidates.find((candidate) => String(candidate.id) === String(draft.candidateId));
              const approvedTextChanged = ['APPROVED', 'QUEUED', 'PUBLISH_FAILED'].includes(status)
                && Boolean(review.final_text)
                && draft.text.trim() !== review.final_text?.trim();
              const reviewAccountWriteReady = review.account?.status === 'active'
                && review.account?.write_enabled === true;
              const canApprove = canOperate
                && [
                  'PENDING',
                  'IN_REVIEW',
                  'NEW',
                  'AI_GENERATED',
                  'NEEDS_FACT_CHECK',
                  'NEEDS_REVIEW',
                  'PUBLISH_FAILED',
                  ...(approvedTextChanged ? ['APPROVED', 'QUEUED'] : []),
                ].includes(status)
                && Boolean(draft.text.trim());
              const publishAllowed = canOperate
                && ['APPROVED', 'QUEUED', 'PUBLISH_FAILED'].includes(status)
                && effectiveWriteAllowed
                && reviewAccountWriteReady
                && review.api_reply_eligible === true
                && draft.candidateId != null
                && !approvedTextChanged;
              const publishReason = !effectiveWriteAllowed
                ? '写入关闭或 Kill Switch 已开启'
                : !reviewAccountWriteReady
                  ? '目标账号未启用写入或账号状态不可用'
                : review.api_reply_eligible !== true
                  ? (reviewEligibilityReason(review) || '目标不满足受控回复资格，请复制草稿后手工发布')
                  : approvedTextChanged
                    ? '当前文本与已批准版本不同，请重新批准后再发布'
                  : !['APPROVED', 'QUEUED', 'PUBLISH_FAILED'].includes(status)
                    ? '必须先完成当前文本的人工批准'
                    : '';

              return (
                <List.Item style={{ display: 'block', padding: '0 0 16px' }}>
                  <Card
                    title={(
                      <Space wrap>
                        <ReviewStatusTag status={status} />
                        <RiskTag risk={review.risk_level || selectedCandidate?.risk_level || selectedCandidate?.risk} />
                        <Text>目标帖子 {reviewTargetId(review) || '未知'}</Text>
                        {reviewAccountUsername(review) && <Tag>@{reviewAccountUsername(review)}</Tag>}
                      </Space>
                    )}
                    extra={<Text type="secondary">{formatDate(review.updated_at || review.created_at)}</Text>}
                  >
                    <Row gutter={[20, 16]}>
                      <Col xs={24} xl={9}>
                        <Text strong>目标帖子</Text>
                        <Card size="small" style={{ background: colorBgLayout, marginTop: 8 }}>
                          <Text strong>
                            {postAuthorName(post)}
                            {post?.author_username ? ` @${post.author_username}` : ''}
                          </Text>
                          <Paragraph ellipsis={{ rows: 6 }} style={{ margin: '8px 0' }}>
                            {post?.text || '帖子正文尚未随审核任务返回，可打开 X 原帖查看。'}
                          </Paragraph>
                          <Space wrap>
                            {review.api_reply_eligible === true
                              ? <Tag color="success" icon={<CheckCircleOutlined />}>受控写入可回复</Tag>
                              : <Tag color="warning" icon={<WarningOutlined />}>仅草稿 / 手工发布</Tag>}
                            {review.requires_fact_check && <Tag color="warning">需要事实核验</Tag>}
                          </Space>
                          {reviewEligibilityReason(review) && (
                            <Paragraph type="secondary" style={{ margin: '8px 0 0', fontSize: 12 }}>
                              {reviewEligibilityReason(review)}
                            </Paragraph>
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} xl={15}>
                        <Row gutter={[12, 12]}>
                          <Col xs={24} md={9}>
                            <Text strong>候选版本</Text>
                            <Select
                              style={{ width: '100%', marginTop: 8 }}
                              value={draft.candidateId}
                              placeholder="选择候选"
                              disabled={!canOperate || !candidates.length}
                              options={candidates.map((candidate, index) => ({
                                value: candidate.id,
                                label: `候选 ${index + 1} · ${candidate.style || '默认语气'} · ${formatPercentage(candidate.confidence)}`,
                              }))}
                              onChange={(candidateId) => {
                                const next = candidates.find((candidate) => String(candidate.id) === String(candidateId));
                                updateReviewDraft(review, {
                                  candidateId,
                                  text: candidateText(next),
                                  tone: next?.style || draft.tone,
                                });
                              }}
                            />
                          </Col>
                          <Col xs={24} md={7}>
                            <Text strong>重新生成语气</Text>
                            <Select
                              style={{ width: '100%', marginTop: 8 }}
                              value={draft.tone}
                              disabled={!canOperate}
                              onChange={(tone) => updateReviewDraft(review, { tone })}
                              options={[
                                { value: 'informative', label: '专业信息型' },
                                { value: 'empathetic', label: '共情回应型' },
                                { value: 'concise', label: '简洁直接型' },
                                { value: 'friendly', label: '友好品牌型' },
                              ]}
                            />
                          </Col>
                          <Col xs={24} md={8}>
                            <Text strong>候选元数据</Text>
                            <div style={{ marginTop: 8 }}>
                              <Space wrap>
                                {selectedCandidate?.model_version && <Tag>{selectedCandidate.model_version}</Tag>}
                                {selectedCandidate?.requires_fact_check && <Tag color="warning">事实核验</Tag>}
                                {selectedCandidate?.duplicate_score != null && (
                                  <Tag>重复度 {formatPercentage(selectedCandidate.duplicate_score)}</Tag>
                                )}
                              </Space>
                            </div>
                          </Col>
                        </Row>
                        <TextArea
                          rows={5}
                          showCount
                          maxLength={280}
                          value={draft.text}
                          disabled={!canOperate || ['PUBLISHED', 'PUBLISHING'].includes(status)}
                          placeholder="选择候选或输入最终审核文本"
                          style={{ marginTop: 12 }}
                          onChange={(event) => updateReviewDraft(review, { text: event.target.value })}
                        />

                        {checks.length > 0 && (
                          <Collapse
                            ghost
                            style={{ marginTop: 8 }}
                            items={[{
                              key: 'policy',
                              label: `查看风控规则（${checks.length}）`,
                              children: (
                                <List
                                  size="small"
                                  dataSource={checks}
                                  renderItem={(check) => {
                                    const passed = check.passed ?? normalizeStatus(check.result) === 'PASSED';
                                    return (
                                      <List.Item>
                                        <Space align="start">
                                          {passed
                                            ? <CheckCircleOutlined style={{ color: '#52c41a', marginTop: 4 }} />
                                            : <CloseCircleOutlined style={{ color: '#ff4d4f', marginTop: 4 }} />}
                                          <div>
                                            <Text strong>{check.name || check.rule || '策略规则'}</Text>
                                            {(check.reason || check.evidence) && (
                                              <Paragraph type="secondary" style={{ margin: 0 }}>
                                                {check.reason || check.evidence}
                                              </Paragraph>
                                            )}
                                          </div>
                                        </Space>
                                      </List.Item>
                                    );
                                  }}
                                />
                              ),
                            }]}
                          />
                        )}

                        <Divider style={{ margin: '12px 0' }} />
                        <Space wrap>
                          <Popconfirm
                            title="确认重新生成候选？"
                            description="现有草稿会保留在审计记录中，新候选仍需人工审核。"
                            okText="确认生成"
                            cancelText="取消"
                            onConfirm={() => runAction(
                              `regenerate-${review.id}`,
                              () => regenerateXReview(review.id, { tone: draft.tone }),
                              '候选已重新生成',
                            )}
                          >
                            <Button
                              icon={<ReloadOutlined />}
                              disabled={!canOperate || ['PUBLISHED', 'PUBLISHING'].includes(status)}
                              loading={actionLoading === `regenerate-${review.id}`}
                            >
                              重新生成
                            </Button>
                          </Popconfirm>

                          <Popconfirm
                            title="确认批准当前文本？"
                            description="批准绑定当前目标帖子、候选版本和文本哈希；后续编辑会使批准失效。"
                            okText="确认批准"
                            cancelText="取消"
                            onConfirm={() => handleApprove(review)}
                          >
                            <Button
                              type="primary"
                              icon={<CheckCircleOutlined />}
                              disabled={!canApprove}
                              loading={actionLoading === `approve-${review.id}`}
                            >
                              批准当前文本
                            </Button>
                          </Popconfirm>

                          <Button
                            danger
                            icon={<CloseCircleOutlined />}
                            disabled={!canOperate || ['REJECTED', 'PUBLISHED', 'PUBLISHING'].includes(status)}
                            loading={actionLoading === `reject-${review.id}`}
                            onClick={() => showRejectDialog(review)}
                          >
                            拒绝
                          </Button>

                          <Button icon={<CopyOutlined />} onClick={() => void copyDraft(review)}>
                            复制草稿
                          </Button>
                          <Button icon={<ExportOutlined />} onClick={() => openOriginalPost(review)}>
                            打开原帖
                          </Button>

                          <Tooltip title={publishReason || '发布前将再次执行全部资格与预算检查'}>
                            <span>
                              <Popconfirm
                                title="确认向 X 发布这一条回复？"
                                description={(
                                  <div>
                                    <Paragraph style={{ marginBottom: 6 }}>
                                      这会代表已绑定账号真实发布，且只发布当前这一条。
                                    </Paragraph>
                                    <Text type="danger">目标：{reviewTargetId(review)}</Text>
                                  </div>
                                )}
                                okText="确认单条发布"
                                cancelText="取消"
                                okButtonProps={{ danger: true }}
                                onConfirm={() => handlePublish(review)}
                                disabled={!publishAllowed}
                              >
                                <Button
                                  danger
                                  type="primary"
                                  icon={<SendOutlined />}
                                  disabled={!publishAllowed}
                                  loading={actionLoading === `publish-${review.id}`}
                                >
                                  发布到 X
                                </Button>
                              </Popconfirm>
                            </span>
                          </Tooltip>
                        </Space>
                      </Col>
                    </Row>
                  </Card>
                </List.Item>
              );
            }}
          />
        </div>
      ),
    },
    {
      key: 'automation',
      label: (
        <Space size={6}>
          <SettingOutlined />
          自动化控制
        </Space>
      ),
      children: (
        <div>
          <Alert
            type="warning"
            showIcon
            message="安全控制仅管理员可修改"
            description="自动回复必须同时满足 X 书面批准、用户主动互动、浏览器实时校验、低风险策略和写入预算限制。任何单项开关都不能绕过后端资格检查。"
            style={{ marginBottom: 16 }}
          />

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={10}>
              <Card
                title={<Space><StopOutlined /> 紧急停止</Space>}
                style={{
                  height: '100%',
                  background: automation.global_kill_switch ? colorErrorBg : undefined,
                }}
              >
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                  <div>
                    <Title level={4} style={{ marginBottom: 4 }}>
                      {automation.global_kill_switch ? '全部 X 写入已停止' : 'Kill Switch 未开启'}
                    </Title>
                    <Text type="secondary">
                      开启后，待发布任务和自动回复都会在发送前被后端阻断；只读采集可继续运行。
                    </Text>
                  </div>
                  {automation.global_kill_switch ? (
                    <Button
                      block
                      disabled={!isAdmin}
                      onClick={() => confirmControlChange(
                        'global_kill_switch',
                        false,
                        '确认解除 Kill Switch？',
                        '解除后不代表自动允许发布；仍需写入开关、账号凭证、人工审核和全部策略检查通过。',
                        true,
                      )}
                    >
                      解除紧急停止
                    </Button>
                  ) : (
                    <Popconfirm
                      title="立即停止全部 X 写入？"
                      description="确认后，所有账号的人工发布和自动回复都会被后端阻断。"
                      okText="立即停止"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => runAction(
                        'control-global_kill_switch',
                        () => updateXAutomationControls({ global_kill_switch: true }),
                        '已停止全部 X 写入',
                      )}
                    >
                      <Button
                        block
                        danger
                        type="primary"
                        size="large"
                        icon={<StopOutlined />}
                        disabled={!isAdmin}
                        loading={actionLoading === 'control-global_kill_switch'}
                      >
                        立即停止全部 X 写入
                      </Button>
                    </Popconfirm>
                  )}
                </Space>
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card title={<Space><SafetyCertificateOutlined /> 运行模式</Space>}>
                <List
                  dataSource={[
                    {
                      key: 'read_enabled' as const,
                      title: '只读采集',
                      description: '允许专用 Playwright/CDP 浏览器读取热点、帖子、评论和主动互动。',
                      value: automation.read_enabled,
                    },
                    {
                      key: 'write_enabled' as const,
                      title: 'X 写入',
                      description: '允许已批准的单条任务进入发布资格复检。',
                      value: automation.write_enabled,
                      danger: true,
                    },
                    {
                      key: 'require_human_review' as const,
                      title: '强制人工审核',
                      description: '热点和公开帖子应始终保持开启；关闭只适用于已获批的主动互动自动回复。',
                      value: automation.require_human_review,
                      danger: !automation.require_human_review,
                    },
                    {
                      key: 'auto_reply_enabled' as const,
                      title: '受控自动回复',
                      description: '仅处理用户主动 @、引用或回复，且每次互动最多回复一次。',
                      value: automation.auto_reply_enabled,
                      danger: true,
                    },
                  ]}
                  renderItem={(item) => (
                    <List.Item
                      actions={[
                        <Switch
                          key={item.key}
                          checked={item.value}
                          disabled={!isAdmin || (
                            item.key === 'auto_reply_enabled'
                            && !item.value
                            && !hasWrittenApproval
                          )}
                          loading={actionLoading === `control-${item.key}`}
                          onChange={(checked) => confirmControlChange(
                            item.key,
                            checked,
                            `确认${checked ? '开启' : '关闭'}“${item.title}”？`,
                            item.description,
                            Boolean(item.danger && checked),
                          )}
                        />,
                      ]}
                    >
                      <List.Item.Meta
                        avatar={item.danger ? <WarningOutlined style={{ color: '#faad14' }} /> : <ReadOutlined />}
                        title={item.title}
                        description={item.description}
                      />
                    </List.Item>
                  )}
                />
                {!hasWrittenApproval && (
                  <Alert
                    type="warning"
                    showIcon
                    message="尚未记录 X 书面批准，受控自动回复不可开启"
                    style={{ marginTop: 12 }}
                  />
                )}
              </Card>
            </Col>
          </Row>

          <Card title="频率、预算与策略阈值" style={{ marginTop: 16 }}>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>每小时最大发布数</Text>
                <InputNumber
                  min={0}
                  max={100}
                  style={{ width: '100%', marginTop: 8 }}
                  value={policyDraft.hourly_write_limit}
                  disabled={!isAdmin}
                  onChange={(value) => setPolicyDraft((previous) => ({ ...previous, hourly_write_limit: value ?? undefined }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>每日最大发布数</Text>
                <InputNumber
                  min={0}
                  max={1000}
                  style={{ width: '100%', marginTop: 8 }}
                  value={policyDraft.daily_write_limit}
                  disabled={!isAdmin}
                  onChange={(value) => setPolicyDraft((previous) => ({ ...previous, daily_write_limit: value ?? undefined }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>单一用户最大互动次数</Text>
                <InputNumber
                  min={1}
                  max={20}
                  style={{ width: '100%', marginTop: 8 }}
                  value={policyDraft.max_interactions_per_user}
                  disabled={!isAdmin}
                  onChange={(value) => setPolicyDraft((previous) => ({ ...previous, max_interactions_per_user: value ?? undefined }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>回复最短间隔（秒）</Text>
                <InputNumber
                  min={0}
                  max={86400}
                  style={{ width: '100%', marginTop: 8 }}
                  value={policyDraft.min_reply_interval_seconds}
                  disabled={!isAdmin}
                  onChange={(value) => setPolicyDraft((previous) => ({ ...previous, min_reply_interval_seconds: value ?? undefined }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>重复文本阈值（0-1）</Text>
                <InputNumber
                  min={0}
                  max={1}
                  step={0.05}
                  style={{ width: '100%', marginTop: 8 }}
                  value={policyDraft.duplicate_threshold}
                  disabled={!isAdmin}
                  onChange={(value) => setPolicyDraft((previous) => ({ ...previous, duplicate_threshold: value ?? undefined }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>暂停地域</Text>
                <TextArea
                  rows={3}
                  placeholder="每行一个 WOEID、地域名或内部 ID"
                  style={{ marginTop: 8 }}
                  value={policyDraft.paused_regions}
                  disabled={!isAdmin}
                  onChange={(event) => setPolicyDraft((previous) => ({ ...previous, paused_regions: event.target.value }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>暂停关键词</Text>
                <TextArea
                  rows={3}
                  placeholder="匹配后停止采集、生成和发布"
                  style={{ marginTop: 8 }}
                  value={policyDraft.paused_keywords}
                  disabled={!isAdmin}
                  onChange={(event) => setPolicyDraft((previous) => ({ ...previous, paused_keywords: event.target.value }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>高风险话题黑名单</Text>
                <TextArea
                  rows={3}
                  placeholder="匹配后只允许监控，不生成或发布"
                  style={{ marginTop: 8 }}
                  value={policyDraft.high_risk_topics}
                  disabled={!isAdmin}
                  onChange={(event) => setPolicyDraft((previous) => ({ ...previous, high_risk_topics: event.target.value }))}
                />
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Text strong>自动回复意图白名单</Text>
                <TextArea
                  rows={3}
                  placeholder="售后查询、产品说明等"
                  style={{ marginTop: 8 }}
                  value={policyDraft.auto_reply_intents}
                  disabled={!isAdmin}
                  onChange={(event) => setPolicyDraft((previous) => ({ ...previous, auto_reply_intents: event.target.value }))}
                />
              </Col>
            </Row>
            <Divider />
            <Popconfirm
              title="确认保存自动化策略？"
              description="后端会继续执行硬性安全规则，此配置不能放宽平台合规要求。"
              okText="确认保存"
              cancelText="取消"
              onConfirm={savePolicyControls}
            >
              <Button
                type="primary"
                icon={<SettingOutlined />}
                disabled={!isAdmin}
                loading={actionLoading === 'save-policy'}
              >
                保存策略
              </Button>
            </Popconfirm>
          </Card>
        </div>
      ),
    },
    {
      key: 'accounts',
      label: (
        <Space size={6}>
          <WalletOutlined />
          账号与用量
        </Space>
      ),
      children: (
        <div>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} xl={6}>
              <Card>
                <Statistic
                  title="本日浏览器采集条目"
                  value={usage.unique_post_reads ?? usage.post_reads ?? 0}
                  suffix={usage.post_read_budget ? `/ ${usage.post_read_budget}` : undefined}
                  prefix={<MessageOutlined />}
                />
                <Progress
                  percent={percentOf(usage.unique_post_reads ?? usage.post_reads, usage.post_read_budget)}
                  status={percentOf(usage.unique_post_reads ?? usage.post_reads, usage.post_read_budget) >= 100 ? 'exception' : 'normal'}
                  size="small"
                  style={{ marginTop: 12 }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Card>
                <Statistic
                  title="本日采集操作"
                  value={usage.request_count ?? 0}
                  prefix={<UserOutlined />}
                />
                <Text type="secondary">热点、搜索、线程、mentions 与账号识别</Text>
              </Card>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Card>
                <Statistic
                  title="本日写入"
                  value={usage.writes ?? usage.write_count ?? 0}
                  suffix={usage.write_budget ? `/ ${usage.write_budget}` : undefined}
                  prefix={<SendOutlined />}
                />
                <Progress
                  percent={percentOf(usage.writes ?? usage.write_count, usage.write_budget)}
                  status={percentOf(usage.writes ?? usage.write_count, usage.write_budget) >= 100 ? 'exception' : 'normal'}
                  size="small"
                  style={{ marginTop: 12 }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Card>
                <Statistic
                  title="读取通道"
                  value="Playwright / CDP"
                  prefix={<GlobalOutlined />}
                />
                <Space style={{ marginTop: 12 }}>
                  {usage.forced_read_only
                    ? <Tag color="error">达到采集上限</Tag>
                    : <Tag color="success">不调用付费 Read API</Tag>}
                  {automation.credentials?.browser_use_fallback && <Tag color="blue">browser-use 兜底</Tag>}
                </Space>
              </Card>
            </Col>
          </Row>

          {usage.forced_read_only && (
            <Alert
              type="error"
              showIcon
              message="每日浏览器采集数量已达到上限；写入仍由独立安全开关控制"
              style={{ marginTop: 16 }}
            />
          )}

          <Card
            title={<Space><ApiOutlined /> OAuth 账号</Space>}
            style={{ marginTop: 16 }}
            extra={(
              <Button
                type="primary"
                icon={<GlobalOutlined />}
                disabled={!isAdmin}
                loading={actionLoading === 'oauth'}
                onClick={() => {
                  modal.confirm({
                    title: '连接 X 账号',
                    content: '即将跳转到 X 官方 OAuth 授权页面。请确认使用正确的品牌或运营账号，并只授予所需 scope。',
                    okText: '继续授权',
                    cancelText: '取消',
                    onOk: handleOAuth,
                  });
                }}
              >
                连接 X 账号
              </Button>
            )}
          >
            <Table<XAccount>
              rowKey={(record) => String(record.id)}
              dataSource={accounts}
              locale={{ emptyText: <Empty description="尚未绑定 X OAuth 账号" /> }}
              pagination={false}
              scroll={{ x: 1320 }}
              columns={[
                {
                  title: '账号',
                  key: 'account',
                  width: 180,
                  render: (_, record) => (
                    <Space direction="vertical" size={0}>
                      <Text strong>{record.display_name || record.username || `账号 ${record.id}`}</Text>
                      {record.username && <Text type="secondary">@{record.username}</Text>}
                    </Space>
                  ),
                },
                {
                  title: '状态',
                  key: 'status',
                  width: 120,
                  render: (_, record) => (
                    <Space direction="vertical" size={4}>
                      <Tag color={record.status === 'active' ? 'success' : 'default'}>{record.status || '未知'}</Tag>
                      <Switch
                        size="small"
                        checked={Boolean(record.write_enabled)}
                        checkedChildren="可写"
                        unCheckedChildren="只读"
                        disabled={!isAdmin || record.status !== 'active'}
                        loading={actionLoading === `account-write_enabled-${record.id}`}
                        onChange={(checked) => confirmAccountToggle(record, 'write_enabled', checked, '写入')}
                      />
                    </Space>
                  ),
                },
                {
                  title: 'Scopes',
                  dataIndex: 'granted_scopes',
                  width: 240,
                  render: (value: string[] | string | undefined) => (
                    <Space wrap>
                      {listText(value).length
                        ? listText(value).map((scope) => <Tag key={scope}>{scope}</Tag>)
                        : <Text type="secondary">未返回 scope</Text>}
                    </Space>
                  ),
                },
                {
                  title: 'Token 过期',
                  dataIndex: 'token_expires_at',
                  width: 150,
                  render: (value: string | number | undefined) => formatDate(value),
                },
                {
                  title: '自动账号标签',
                  dataIndex: 'automated_label_enabled',
                  width: 130,
                  render: (value: boolean, record) => (
                    <Switch
                      size="small"
                      checked={Boolean(value)}
                      checkedChildren="已启用"
                      unCheckedChildren="未启用"
                      disabled={!isAdmin}
                      loading={actionLoading === `account-automated_label_enabled-${record.id}`}
                      onChange={(checked) => confirmAccountToggle(
                        record,
                        'automated_label_enabled',
                        checked,
                        '自动账号标签',
                      )}
                    />
                  ),
                },
                {
                  title: '账号自动回复',
                  dataIndex: 'auto_reply_enabled',
                  width: 130,
                  render: (value: boolean, record) => (
                    <Switch
                      size="small"
                      checked={Boolean(value)}
                      checkedChildren="开启"
                      unCheckedChildren="关闭"
                      disabled={!isAdmin || (!value && (!record.x_written_approval || !record.automated_label_enabled))}
                      loading={actionLoading === `account-auto_reply_enabled-${record.id}`}
                      onChange={(checked) => confirmAccountToggle(record, 'auto_reply_enabled', checked, '自动回复')}
                    />
                  ),
                },
                {
                  title: 'X 批准证据',
                  key: 'approval',
                  width: 170,
                  render: (_, record) => (
                    <Space direction="vertical" size={2}>
                      {record.x_written_approval
                        ? <Tag color="success">已记录</Tag>
                        : <Tag color="error">未记录</Tag>}
                      <Text type="secondary" ellipsis style={{ maxWidth: 160 }}>
                        {record.approval_reference || '—'}
                      </Text>
                      <Button
                        type="link"
                        size="small"
                        style={{ padding: 0 }}
                        disabled={!isAdmin}
                        loading={actionLoading === `account-approval-${record.id}`}
                        onClick={() => showApprovalEvidenceDialog(record)}
                      >
                        {record.x_written_approval ? '更新证据' : '录入证据'}
                      </Button>
                    </Space>
                  ),
                },
                {
                  title: '操作',
                  key: 'actions',
                  fixed: 'right',
                  width: 120,
                  render: (_, record) => (
                    <Popconfirm
                      title="确认测试账号连接？"
                      description="只验证 Token、scope 和账号状态，不会发布内容。"
                      okText="确认测试"
                      cancelText="取消"
                      onConfirm={() => runAction(
                        `test-account-${record.id}`,
                        () => testXAccount(record.id),
                        '账号连接测试完成',
                      )}
                    >
                      <Button
                        icon={<ThunderboltOutlined />}
                        loading={actionLoading === `test-account-${record.id}`}
                        disabled={!isAdmin}
                      >
                        测试
                      </Button>
                    </Popconfirm>
                  ),
                },
              ]}
            />
          </Card>

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} xl={14}>
              <Card title="采集与写入用量">
                <Table<XEndpointUsage>
                  rowKey={(record, index) => `${record.endpoint || record.resource || 'endpoint'}-${index}`}
                  dataSource={endpointUsage}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无采集或写入用量记录" /> }}
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: 'Endpoint',
                      dataIndex: 'endpoint',
                      render: (value: string, record) => value || record.resource || '—',
                    },
                    {
                      title: '请求',
                      key: 'requests',
                      render: (_, record) => record.requests ?? record.request_count ?? 0,
                    },
                    {
                      title: '采集 / 写入',
                      key: 'resources',
                      render: (_, record) => `${record.read_count ?? record.read_resource_count ?? 0} / ${record.write_count ?? 0}`,
                    },
                    {
                      title: 'Remaining',
                      key: 'remaining',
                      render: (_, record) => record.remaining == null
                        ? '—'
                        : `${record.remaining}${record.limit ? ` / ${record.limit}` : ''}`,
                    },
                    {
                      title: 'Reset',
                      dataIndex: 'reset_at',
                      render: (value: string | number | undefined) => formatDate(value),
                    },
                    {
                      title: '通道',
                      key: 'channel',
                      render: (_, record) => String(record.endpoint || '').startsWith('BROWSER')
                        ? <Tag color="blue">浏览器</Tag>
                        : <Tag color="warning">Official Write</Tag>,
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card title="最近运行错误">
                <List
                  size="small"
                  dataSource={recentErrors}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 403、429 或余额错误" /> }}
                  renderItem={(log) => (
                    <List.Item>
                      <List.Item.Meta
                        avatar={<WarningOutlined style={{ color: '#faad14' }} />}
                        title={(
                          <Space wrap>
                            {log.http_status && <Tag color="error">{log.http_status}</Tag>}
                            {log.error_code && <Tag>{log.error_code}</Tag>}
                            <Text>{log.action || 'X 运行任务'}</Text>
                          </Space>
                        )}
                        description={(
                          <div>
                            <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
                              {log.message || '未提供错误详情'}
                            </Paragraph>
                            <Text type="secondary">{formatDate(log.created_at)}</Text>
                          </div>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>
        </div>
      ),
    },
  ];

  if (initialLoading) {
    return (
      <div style={{ minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {messageContextHolder}
        {modalContextHolder}
        <Spin size="large" tip="加载 X 运营状态..." />
      </div>
    );
  }

  return (
    <div>
      {messageContextHolder}
      {modalContextHolder}

      <Row gutter={[16, 12]} justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Space align="start">
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 12,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: colorInfoBg,
              }}
            >
              <GlobalOutlined style={{ fontSize: 22 }} />
            </div>
            <div>
              <Title level={3} style={{ margin: 0 }}>X 运营中心</Title>
              <Text type="secondary">热点监听、线程分析、AI 草稿与受控单条回复</Text>
            </div>
          </Space>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => void loadAll(false)}>
            刷新页面数据
          </Button>
        </Col>
      </Row>

      <Alert
        type={safetyAlertType}
        showIcon
        icon={automation.global_kill_switch ? <StopOutlined /> : effectiveWriteAllowed ? <SendOutlined /> : <LockOutlined />}
        message={safetyAlertTitle}
        description={(
          <Space wrap style={{ marginTop: 6 }}>
            <Tag color={automation.read_enabled ? 'success' : 'default'}>
              读取 {automation.read_enabled ? '开启' : '关闭'}
            </Tag>
            <Tag color={automation.write_enabled ? 'warning' : 'default'}>
              写入 {automation.write_enabled ? '开启' : '关闭'}
            </Tag>
            <Tag color={automation.global_kill_switch ? 'error' : 'success'}>
              Kill Switch {automation.global_kill_switch ? '开启' : '关闭'}
            </Tag>
            <Tag color={automation.require_human_review ? 'blue' : 'warning'}>
              人工审核 {automation.require_human_review ? '强制' : '非强制'}
            </Tag>
            <Tag color={automation.auto_reply_enabled ? 'warning' : 'default'}>
              自动回复 {automation.auto_reply_enabled ? '开启' : '关闭'}
            </Tag>
            <Tag color={automation.credentials?.browser_read_source ? 'success' : 'default'}>
              浏览器读取 {automation.credentials?.browser_read_source ? '已启用' : '不可用'}
            </Tag>
            <Tag color={hasWriteToken ? 'success' : 'default'}>
              写入凭证 {hasWriteToken ? '就绪' : '未配置'}
            </Tag>
            <Tag color={draftEngineAvailable ? 'success' : 'default'}>
              草稿引擎 {automation.credentials?.llm ? 'LLM' : draftEngineAvailable ? '本地安全模式' : '未配置'}
            </Tag>
          </Space>
        )}
        style={{ marginBottom: 12 }}
      />

      {automationReasons.length > 0 && (
        <Alert
          type="info"
          showIcon
          message="当前能力限制"
          description={(
            <Space wrap>
              {automationReasons.map((reason) => <Tag key={reason}>{reason}</Tag>)}
            </Space>
          )}
          style={{ marginBottom: 12 }}
        />
      )}

      {loadErrors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          closable
          message="部分 X 接口尚不可用，页面已降级为空态"
          description={loadErrors.join('；')}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card styles={{ body: { paddingTop: 8 } }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>

      <div
        style={{
          marginTop: 16,
          padding: 12,
          border: `1px solid ${colorBorderSecondary}`,
          borderRadius: 8,
          background: effectiveWriteAllowed ? colorWarningBg : colorSuccessBg,
          color: colorTextSecondary,
          fontSize: 12,
        }}
      >
        X 内容仅用于当前运营任务的分析与推理，不用于训练、微调或敏感属性画像。热点或关键词匹配不会触发对陌生用户的自动回复。
      </div>
    </div>
  );
}

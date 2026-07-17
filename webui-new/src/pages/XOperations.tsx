import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
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
import { useNavigate, useSearchParams } from 'react-router-dom';
import { authStorage } from '../api/auth';
import {
  analyzeXConversation,
  approveXReview,
  collectXTopicPosts,
  collectXThread,
  evaluateXInteraction,
  flagXReview,
  generateXReplyCandidates,
  getXAccounts,
  getXAuditLogs,
  getXAutomationStatus,
  getXBrowserStatus,
  getXConversation,
  getXInteractions,
  getXPosts,
  getXReviews,
  getXTopics,
  getXUsage,
  openXBrowserLogin,
  optOutXUser,
  publishXReview,
  refreshXInteractions,
  refreshXTopics,
  regenerateXReview,
  rejectXReview,
  startXOAuth,
  syncXBrowserAccount,
  testXAccount,
  updateXAccount,
  updateXAutomationControls,
  type XAccount,
  type XAuditLog,
  type XAutomationStatus,
  type XBrowserStatus,
  type XConversation,
  type XEndpointUsage,
  type XInteraction,
  type XPolicyCheck,
  type XPost,
  type XPublicMetrics,
  type XReplyCandidate,
  type XReviewTask,
  type XThreadAnalysis,
  type XThreadNode,
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
  effective_browser_write_allowed: false,
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

function auditDetail(log: XAuditLog): string {
  if (log.message) return log.message;
  const metadata = parseMaybeJson<Record<string, unknown>>(log.metadata_json, {});
  const after = parseMaybeJson<Record<string, unknown>>(log.after_state_json, {});
  return String(
    metadata.message
    || metadata.error_message
    || metadata.reason
    || after.error_message
    || after.reason
    || log.outcome
    || '未提供错误详情',
  );
}

function auditHttpStatus(log: XAuditLog): number | undefined {
  if (log.http_status) return log.http_status;
  const metadata = parseMaybeJson<Record<string, unknown>>(log.metadata_json, {});
  const value = Number(metadata.http_status || metadata.status_code || 0);
  return value > 0 ? value : undefined;
}

function auditErrorCode(log: XAuditLog): string {
  if (log.error_code) return log.error_code;
  const metadata = parseMaybeJson<Record<string, unknown>>(log.metadata_json, {});
  return String(metadata.error_code || '');
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

function interactionEligibility(interaction: XInteraction): Record<string, unknown> {
  return parseMaybeJson<Record<string, unknown>>(interaction.eligibility_json, {});
}

function interactionEvidence(interaction: XInteraction): Record<string, unknown> {
  return parseMaybeJson<Record<string, unknown>>(interaction.opt_in_evidence_json, {});
}

function interactionIntent(interaction: XInteraction): string {
  const intent = interactionEvidence(interaction).intent;
  if (!intent || typeof intent !== 'object') return '未分类';
  const record = intent as Record<string, unknown>;
  return String(record.label || record.code || '未分类');
}

function interactionStatusColor(status?: string): string {
  const normalized = normalizeStatus(status);
  if (normalized === 'ELIGIBLE') return 'success';
  if (normalized === 'BLOCKED') return 'error';
  if (['DRAFTED', 'REVIEWED', 'PUBLISHED'].includes(normalized)) return 'processing';
  return 'default';
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

function ThreadTreeList({ nodes, depth = 0 }: { nodes: XThreadNode[]; depth?: number }) {
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      {nodes.map((post) => (
        <div
          key={postIdentifier(post)}
          style={{
            marginLeft: Math.min(depth, 4) * 20,
            padding: '10px 12px',
            borderLeft: depth > 0 ? '2px solid rgba(22, 119, 255, 0.25)' : undefined,
            borderRadius: 8,
            background: depth % 2 === 0 ? 'rgba(0, 0, 0, 0.02)' : undefined,
          }}
        >
          <Space wrap>
            <Text strong>{postAuthorName(post)}</Text>
            {post.author_username && <Text type="secondary">@{post.author_username}</Text>}
            <Tag>{depth === 0 ? '直接回复' : `层级 ${depth + 1}`}</Tag>
          </Space>
          <Paragraph style={{ margin: '6px 0 2px', whiteSpace: 'pre-wrap' }}>
            {post.text || '内容不可用'}
          </Paragraph>
          <Text type="secondary">{formatDate(post.created_at_x || post.created_at)}</Text>
          {post.children?.length ? (
            <div style={{ marginTop: 8 }}>
              <ThreadTreeList nodes={post.children} depth={depth + 1} />
            </div>
          ) : null}
        </div>
      ))}
    </Space>
  );
}

export default function XOperations() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
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

  const requestedTab = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState(
    ['radar', 'posts', 'interactions', 'reviews', 'automation', 'accounts'].includes(requestedTab || '')
      ? requestedTab || 'radar'
      : 'radar',
  );
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [topics, setTopics] = useState<XTopic[]>([]);
  const [posts, setPosts] = useState<XPost[]>([]);
  const [reviews, setReviews] = useState<XReviewTask[]>([]);
  const [accounts, setAccounts] = useState<XAccount[]>([]);
  const [browserStatus, setBrowserStatus] = useState<XBrowserStatus>({});
  const [interactions, setInteractions] = useState<XInteraction[]>([]);
  const [auditLogs, setAuditLogs] = useState<XAuditLog[]>([]);
  const [usage, setUsage] = useState<XUsageSummary>({});
  const [automation, setAutomation] = useState<XAutomationStatus>(SAFE_AUTOMATION_DEFAULTS);
  const [policyDraft, setPolicyDraft] = useState<PolicyDraft>(policyDraftFromStatus(SAFE_AUTOMATION_DEFAULTS));
  const [topicSearch, setTopicSearch] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState<string | number>();
  const [selectedAccountId, setSelectedAccountId] = useState<string | number>();
  const [postSearch, setPostSearch] = useState('');
  const [reviewStatus, setReviewStatus] = useState('ALL');
  const [selectedReviewIds, setSelectedReviewIds] = useState<string[]>([]);
  const [interactionStatus, setInteractionStatus] = useState('ALL');
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
      getXBrowserStatus(),
      getXAccounts(),
      getXInteractions({ limit: 100 }),
      getXUsage(),
      getXAuditLogs({ limit: 50 }),
    ]);

    const errors: string[] = [];
    const labels = ['热点', '帖子', '审核队列', '安全状态', '浏览器会话', '账号', '主动互动', '预算', '审计日志'];
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
      setBrowserStatus(results[4].value as XBrowserStatus);
    }
    if (results[5].status === 'fulfilled') {
      const nextAccounts = listFromResponse<XAccount>(results[5].value, ['accounts']);
      setAccounts(nextAccounts);
      setSelectedAccountId((previous) => {
        if (previous != null && nextAccounts.some((account) => String(account.id) === String(previous))) {
          return previous;
        }
        return nextAccounts.find((account) => account.status === 'active')?.id
          ?? nextAccounts[0]?.id;
      });
    }
    if (results[6].status === 'fulfilled') {
      setInteractions(listFromResponse<XInteraction>(results[6].value, ['interactions']));
    }
    if (results[7].status === 'fulfilled') {
      const raw = results[7].value as XUsageSummary & {
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
          ?? Boolean(raw.budgets?.post_reads_status?.exhausted),
        write_budget_exhausted: raw.write_budget_exhausted
          ?? Boolean(raw.budgets?.writes_status?.exhausted),
        endpoints: enrichedItems,
      });
    }
    if (results[8].status === 'fulfilled') {
      setAuditLogs(listFromResponse<XAuditLog>(results[8].value, ['logs', 'audit_logs']));
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
      const responsePosts = listFromResponse<XPost>(raw.posts, ['posts']);
      const rootPost = responsePosts.find((item) => postIdentifier(item) === String(rootPostId)) || post;
      setSelectedPost(rootPost);
      setConversation({
        ...raw,
        root_post: raw.root_post || rootPost,
        posts: responsePosts,
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
      navigate(`/x/posts/${encodeURIComponent(rootPostId)}`);
    } else {
      await loadConversation(post);
      navigate(`/x/posts/${encodeURIComponent(rootPostId)}`);
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
    const responsePosts = listFromResponse<XPost>(result.posts, ['posts']);
    const rootPostId = post.conversation_id || postIdentifier(post);
    const rootPost = responsePosts.find((item) => postIdentifier(item) === String(rootPostId)) || post;
    setSelectedPost(rootPost);
    setConversation({
      ...result,
      root_post: rootPost,
      posts: responsePosts,
      analysis: normalizeAnalysis(result.analysis),
    });
    navigate(`/x/posts/${encodeURIComponent(rootPostId)}`);
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

  const handleOpenBrowserLogin = async () => {
    await runAction(
      'browser-open-login',
      () => openXBrowserLogin(),
      '已打开专用 X 登录窗口',
    );
  };

  const handleSyncBrowserAccount = async () => {
    const result = await runAction(
      'browser-sync',
      () => syncXBrowserAccount(),
      '浏览器登录账号已同步',
    );
    if (result) setActiveTab('accounts');
  };

  const handleRefreshInteractions = async () => {
    if (selectedAccountId == null) {
      messageApi.warning('请先检测并同步浏览器账号');
      setActiveTab('accounts');
      return;
    }
    const result = await runAction(
      'refresh-interactions',
      () => refreshXInteractions({
        account_id: selectedAccountId,
        max_posts: 50,
      }),
      'mentions 已完成增量采集',
    );
    if (result) setActiveTab('interactions');
  };

  const handleEvaluateInteraction = async (interaction: XInteraction) => {
    await runAction(
      `evaluate-interaction-${interaction.id}`,
      () => evaluateXInteraction(interaction.id),
      '互动资格已重新评估',
    );
  };

  const handleGenerateInteractionReply = async (interaction: XInteraction) => {
    const post = interaction.post;
    if (!post?.id) {
      messageApi.warning('该互动缺少本地帖子记录，无法生成草稿');
      return;
    }
    const result = await runAction(
      `generate-interaction-${interaction.id}`,
      () => generateXReplyCandidates(post.id, {
        account_id: interaction.account_id,
        candidate_count: 3,
      }),
      '已生成 3 条候选并进入人工审核队列',
    );
    if (result) setActiveTab('reviews');
  };

  const handleOptOutInteractionUser = async (interaction: XInteraction) => {
    if (!interaction.actor_x_user_id) {
      messageApi.warning('该互动缺少用户 ID，无法写入退出名单');
      return;
    }
    await runAction(
      `opt-out-${interaction.id}`,
      () => optOutXUser(interaction.actor_x_user_id!, {
        account_id: interaction.account_id,
        source_interaction_id: interaction.id,
        source_post_id: interaction.interaction_post_id,
        detected_phrase: 'manual opt-out from X operations UI',
        evidence: { source: 'x_operations_ui' },
      }),
      '该用户已加入停止互动名单',
    );
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

  const showReviewFlagDialog = (
    review: XReviewTask,
    action: 'fact_check' | 'block',
  ) => {
    let reason = '';
    const isBlock = action === 'block';
    modal.confirm({
      title: isBlock ? '标记禁止参与' : '要求事实核验',
      icon: isBlock
        ? <StopOutlined style={{ color: '#ff4d4f' }} />
        : <WarningOutlined style={{ color: '#faad14' }} />,
      content: (
        <div style={{ marginTop: 16 }}>
          <Paragraph type="secondary">
            {isBlock
              ? '禁止参与会使当前候选失效，后续不能批准或发布。'
              : '标记后仍可在完成核验、修订文本后重新批准。'}
          </Paragraph>
          <TextArea
            rows={3}
            placeholder={isBlock ? '请输入禁止参与原因' : '请输入需要核验的事实或依据'}
            onChange={(event) => { reason = event.target.value; }}
          />
        </div>
      ),
      okText: isBlock ? '确认阻断' : '确认标记',
      cancelText: '取消',
      okButtonProps: { danger: isBlock },
      onOk: async () => {
        if (!reason.trim()) {
          messageApi.warning('请输入原因');
          return Promise.reject();
        }
        const result = await runAction(
          `flag-${action}-${review.id}`,
          () => flagXReview(review.id, { action, reason: reason.trim() }),
          isBlock ? '已标记禁止参与' : '已标记需要事实核验',
        );
        if (!result) return Promise.reject();
      },
    });
  };

  const showBatchRejectDialog = () => {
    let reason = '';
    modal.confirm({
      title: `批量拒绝 ${selectedReviewIds.length} 条审核任务`,
      icon: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
      content: (
        <div style={{ marginTop: 16 }}>
          <Alert
            type="warning"
            showIcon
            message="只会批量拒绝，不会批量批准或发布"
            style={{ marginBottom: 12 }}
          />
          <TextArea
            rows={3}
            placeholder="请输入统一拒绝原因"
            onChange={(event) => { reason = event.target.value; }}
          />
        </div>
      ),
      okText: '确认批量拒绝',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (!reason.trim()) {
          messageApi.warning('请输入拒绝原因');
          return Promise.reject();
        }
        setActionLoading('batch-reject');
        let completed = 0;
        try {
          for (const reviewId of selectedReviewIds) {
            await rejectXReview(reviewId, { reason: reason.trim() });
            completed += 1;
          }
          setSelectedReviewIds([]);
          messageApi.success(`已拒绝 ${completed} 条审核任务`);
          await loadAll(false);
        } catch (error) {
          messageApi.error(`已完成 ${completed} 条；后续失败：${errorDetail(error)}`);
          return Promise.reject();
        } finally {
          setActionLoading('');
        }
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
            ? '自动回复仍必须满足自动账号标签、用户主动互动、低风险策略、频率限制和全局白名单。'
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

  const filteredInteractions = useMemo(() => {
    if (interactionStatus === 'ALL') return interactions;
    return interactions.filter((interaction) => normalizeStatus(interaction.status) === interactionStatus);
  }, [interactionStatus, interactions]);

  const eligibleInteractionCount = useMemo(
    () => interactions.filter((interaction) => normalizeStatus(interaction.status) === 'ELIGIBLE').length,
    [interactions],
  );

  const pendingReviewCount = useMemo(() => reviews.filter((review) => {
    const status = normalizeStatus(review.status || review.review_status);
    return ['PENDING', 'IN_REVIEW', 'NEW', 'AI_GENERATED', 'NEEDS_FACT_CHECK', 'NEEDS_REVIEW', 'PUBLISH_FAILED'].includes(status);
  }).length, [reviews]);

  const effectiveWriteAllowed = Boolean(
    automation.effective_browser_write_allowed
    ?? (automation.write_enabled && !automation.global_kill_switch),
  );
  const hasAutomatedAccount = accounts.some((account) => (
    account.status === 'active' && account.automated_label_enabled
  ));
  const draftEngineAvailable = Boolean(
    automation.credentials?.llm || automation.credentials?.fallback_drafts_available,
  );

  const automationReasons = automation.reasons || [];
  const endpointUsage = usage.endpoints || usage.endpoint_usage || [];
  const recentErrors = [
    ...(usage.recent_errors || []),
    ...auditLogs.filter((log) => (
      (auditHttpStatus(log) || 0) >= 400
      || ['FAILED', 'ERROR', 'BLOCKED'].includes(normalizeStatus(log.status || log.outcome))
      || Boolean(auditErrorCode(log))
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
  const conversationTree = conversation?.tree || [];
  const treeRoot = conversationTree.find(
    (node) => postIdentifier(node) === postIdentifier(selectedPost),
  );
  const threadTreeNodes = treeRoot?.children?.length
    ? treeRoot.children
    : conversationTree.filter((node) => postIdentifier(node) !== postIdentifier(selectedPost));

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
              onClick: () => navigate(`/x/posts/${encodeURIComponent(postIdentifier(record))}`),
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
                    <Button
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => navigate(`/x/posts/${encodeURIComponent(postIdentifier(record))}`)}
                    >
                      查看
                    </Button>
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
                    {threadTreeNodes.length ? (
                      <ThreadTreeList nodes={threadTreeNodes} />
                    ) : threadPosts.length ? (
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
      key: 'interactions',
      label: (
        <Space size={6}>
          <MessageOutlined />
          主动互动
          {eligibleInteractionCount > 0 && <Badge count={eligibleInteractionCount} size="small" />}
        </Space>
      ),
      children: (
        <div>
          <Alert
            type="info"
            showIcon
            message="mentions 只采集和生成草稿，不会自动发布"
            description="仅处理用户主动 @、引用或回复。生成的候选必须进入人工审核队列；当前页面不会创建自动发布任务。"
            style={{ marginBottom: 16 }}
          />
          <Card size="small" style={{ marginBottom: 16 }}>
            <Row gutter={[12, 12]} align="middle">
              <Col xs={24} md={9}>
                <Select
                  style={{ width: '100%' }}
                  placeholder="选择采集 mentions 的浏览器账号"
                  value={selectedAccountId}
                  onChange={setSelectedAccountId}
                  options={accounts.map((account) => ({
                    value: account.id,
                    label: `${account.display_name || account.username || `账号 ${account.id}`}${account.username ? ` (@${account.username})` : ''}`,
                    disabled: account.status != null && account.status !== 'active',
                  }))}
                  notFoundContent="请先在账号与用量中同步浏览器账号"
                />
              </Col>
              <Col>
                <Select
                  value={interactionStatus}
                  style={{ minWidth: 150 }}
                  onChange={setInteractionStatus}
                  options={[
                    { value: 'ALL', label: '全部状态' },
                    { value: 'PENDING', label: '待评估' },
                    { value: 'ELIGIBLE', label: '可生成草稿' },
                    { value: 'BLOCKED', label: '已阻断' },
                    { value: 'DRAFTED', label: '已生成' },
                    { value: 'PUBLISHED', label: '已发布' },
                  ]}
                />
              </Col>
              <Col>
                <Popconfirm
                  title="确认增量采集 mentions？"
                  description="使用专用浏览器读取 notifications/mentions，最多采集 50 条；不会自动生成或发布回复。"
                  okText="确认采集"
                  cancelText="取消"
                  onConfirm={handleRefreshInteractions}
                >
                  <Button
                    type="primary"
                    icon={<SyncOutlined />}
                    disabled={!canOperate || !automation.read_enabled || selectedAccountId == null}
                    loading={actionLoading === 'refresh-interactions'}
                  >
                    刷新 mentions
                  </Button>
                </Popconfirm>
              </Col>
            </Row>
          </Card>

          <Table<XInteraction>
            rowKey={(record) => String(record.id)}
            dataSource={filteredInteractions}
            locale={{ emptyText: <Empty description="暂无主动互动，请先同步浏览器账号并刷新 mentions" /> }}
            scroll={{ x: 1220 }}
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条互动` }}
            columns={[
              {
                title: '互动',
                key: 'interaction',
                width: 160,
                render: (_, record) => (
                  <Space direction="vertical" size={2}>
                    <Tag>{record.interaction_type || 'mention'}</Tag>
                    <Text type="secondary">{formatDate(record.received_at || record.created_at)}</Text>
                  </Space>
                ),
              },
              {
                title: '用户 / 内容',
                key: 'post',
                width: 430,
                render: (_, record) => (
                  <div>
                    <Space wrap>
                      <Text strong>
                        {record.post?.author_username
                          ? `@${record.post.author_username}`
                          : record.actor_x_user_id || '未知用户'}
                      </Text>
                      {record.post?.lang && <Tag>{record.post.lang}</Tag>}
                    </Space>
                    <Paragraph ellipsis={{ rows: 3 }} style={{ margin: '6px 0 0' }}>
                      {record.post?.text || '互动正文尚未同步'}
                    </Paragraph>
                  </div>
                ),
              },
              {
                title: '意图',
                key: 'intent',
                width: 150,
                render: (_, record) => <Tag color="blue">{interactionIntent(record)}</Tag>,
              },
              {
                title: '资格证据',
                key: 'eligibility',
                width: 240,
                render: (_, record) => {
                  const eligibility = interactionEligibility(record);
                  const reasons = Array.isArray(eligibility.reasons)
                    ? eligibility.reasons.map(String)
                    : [];
                  const eligible = eligibility.eligible === true && !record.is_opted_out;
                  return (
                    <Space direction="vertical" size={4}>
                      <Tag color={eligible ? 'success' : 'warning'}>
                        {eligible ? '用户主动互动，可生成草稿' : '不满足受控回复资格'}
                      </Tag>
                      {reasons.length > 0 && (
                        <Text type="secondary" ellipsis={{ tooltip: reasons.join('；') }} style={{ maxWidth: 220 }}>
                          {reasons.join('；')}
                        </Text>
                      )}
                      {record.is_opted_out && <Tag color="error">用户已退出互动</Tag>}
                    </Space>
                  );
                },
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 110,
                render: (value: string) => (
                  <Tag color={interactionStatusColor(value)}>{value || 'pending'}</Tag>
                ),
              },
              {
                title: '操作',
                key: 'actions',
                fixed: 'right',
                width: 300,
                render: (_, record) => {
                  const eligible = interactionEligibility(record).eligible === true
                    && !record.is_opted_out;
                  return (
                    <Space wrap>
                      <Button
                        size="small"
                        icon={<SafetyCertificateOutlined />}
                        disabled={!canOperate}
                        loading={actionLoading === `evaluate-interaction-${record.id}`}
                        onClick={() => void handleEvaluateInteraction(record)}
                      >
                        重新评估
                      </Button>
                      <Popconfirm
                        title="确认生成 3 条 AI 回复草稿？"
                        description="只进入人工审核队列，不会自动发布。"
                        okText="确认生成"
                        cancelText="取消"
                        onConfirm={() => handleGenerateInteractionReply(record)}
                      >
                        <Button
                          size="small"
                          type="primary"
                          ghost
                          icon={<RobotOutlined />}
                          disabled={!canOperate || !eligible || !draftEngineAvailable || !record.post?.id}
                          loading={actionLoading === `generate-interaction-${record.id}`}
                        >
                          生成回复
                        </Button>
                      </Popconfirm>
                      <Button
                        size="small"
                        icon={<ExportOutlined />}
                        onClick={() => window.open(postLink(record.post, record.interaction_post_id), '_blank', 'noopener,noreferrer')}
                      >
                        原帖
                      </Button>
                      <Popconfirm
                        title="确认停止与该用户互动？"
                        description="该用户的现有互动会被阻断，后续 mentions 也不会进入回复候选。"
                        okText="确认停止"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => handleOptOutInteractionUser(record)}
                      >
                        <Button
                          size="small"
                          danger
                          disabled={!canOperate || record.is_opted_out || !record.actor_x_user_id}
                          loading={actionLoading === `opt-out-${record.id}`}
                        >
                          停止互动
                        </Button>
                      </Popconfirm>
                    </Space>
                  );
                },
              },
            ]}
          />
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
              <Button
                danger
                icon={<CloseCircleOutlined />}
                disabled={!canOperate || selectedReviewIds.length === 0}
                loading={actionLoading === 'batch-reject'}
                onClick={showBatchRejectDialog}
              >
                批量拒绝 ({selectedReviewIds.length})
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
              const reviewAccountWriteReady = review.account?.status === 'active';
              const selectable = !['REJECTED', 'PUBLISHED', 'PUBLISHING', 'CANCELLED'].includes(status);
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
                && review.manual_browser_publish_eligible !== false
                && draft.candidateId != null
                && !approvedTextChanged;
              const publishReason = !effectiveWriteAllowed
                ? '写入关闭或 Kill Switch 已开启'
                : !reviewAccountWriteReady
                  ? '审核记录绑定的账号状态不可用'
                  : review.manual_browser_publish_eligible === false
                    ? (reviewEligibilityReason(review) || '当前审核记录不允许浏览器人工发布')
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
                        {selectable && (
                          <Checkbox
                            checked={selectedReviewIds.includes(String(review.id))}
                            onChange={(event) => {
                              const id = String(review.id);
                              setSelectedReviewIds((previous) => (
                                event.target.checked
                                  ? Array.from(new Set([...previous, id]))
                                  : previous.filter((item) => item !== id)
                              ));
                            }}
                          />
                        )}
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

                          <Button
                            icon={<WarningOutlined />}
                            disabled={!canOperate || ['REJECTED', 'BLOCKED', 'PUBLISHED', 'PUBLISHING'].includes(status)}
                            loading={actionLoading === `flag-fact_check-${review.id}`}
                            onClick={() => showReviewFlagDialog(review, 'fact_check')}
                          >
                            事实核验
                          </Button>

                          <Button
                            danger
                            icon={<StopOutlined />}
                            disabled={!canOperate || ['REJECTED', 'BLOCKED', 'PUBLISHED', 'PUBLISHING'].includes(status)}
                            loading={actionLoading === `flag-block-${review.id}`}
                            onClick={() => showReviewFlagDialog(review, 'block')}
                          >
                            禁止参与
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
                                      将使用专用浏览器当前登录账号真实发布，且只发布当前这一条。
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
            description="受控自动回复不要求额外录入书面批准，但仍必须满足自动账号标签、用户主动互动、浏览器实时校验、低风险策略、频率限制和写入预算。"
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
                            && !hasAutomatedAccount
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
                {!hasAutomatedAccount && (
                  <Alert
                    type="warning"
                    showIcon
                    message="请先为至少一个活跃账号启用自动账号标签，再开启受控自动回复"
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
          <Card
            title={<Space><GlobalOutlined /> 浏览器采集会话</Space>}
            style={{ marginBottom: 16 }}
            extra={(
              <Space wrap>
                <Button
                  icon={<GlobalOutlined />}
                  disabled={!canOperate}
                  loading={actionLoading === 'browser-open-login'}
                  onClick={() => void handleOpenBrowserLogin()}
                >
                  打开专用 X 登录窗口
                </Button>
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  disabled={
                    !canOperate
                    || !automation.read_enabled
                    || (browserStatus.profile_in_use && !browserStatus.cdp_ready)
                  }
                  loading={actionLoading === 'browser-sync'}
                  onClick={() => void handleSyncBrowserAccount()}
                >
                  检测登录并同步账号
                </Button>
              </Space>
            )}
          >
            <Alert
              type={
                browserStatus.profile_in_use && browserStatus.cdp_ready
                  ? 'success'
                  : browserStatus.profile_in_use
                    ? 'warning'
                    : browserStatus.cookie_store_detected
                      ? 'info'
                      : 'warning'
              }
              showIcon
              message={browserStatus.profile_in_use && browserStatus.cdp_ready
                ? `专用 X 浏览器已连接 CDP :${browserStatus.debug_port || 9222}，可以保持窗口打开`
                : browserStatus.profile_in_use
                  ? '专用 X Profile 被未开启 CDP 的浏览器占用，请关闭后重新打开'
                : browserStatus.cookie_store_detected
                  ? '已检测到专用浏览器 Cookie 存储；仍需执行登录检测确认 X 会话有效'
                  : '尚未检测到专用浏览器登录数据'}
              description="系统不会复制普通 Chrome 的 Cookie。首次使用请打开专用窗口登录 X；窗口开启 CDP 后可保持运行，直接检测账号、刷新热点和采集评论。同步只创建采集/AI 草稿账号，不创建 OAuth Token，也不会开启写入。"
              style={{ marginBottom: 16 }}
            />
            <Row gutter={[16, 12]}>
              <Col xs={24} md={12} xl={8}>
                <Text type="secondary">Profile</Text>
                <Paragraph code copyable style={{ margin: '4px 0 0' }}>
                  {browserStatus.profile_dir || '尚未返回'}
                </Paragraph>
              </Col>
              <Col xs={12} md={6} xl={4}>
                <Text type="secondary">启动方式</Text>
                <div style={{ marginTop: 6 }}>
                  <Tag color={browserStatus.cdp_mode ? 'blue' : 'default'}>
                    {browserStatus.cdp_mode ? 'Playwright + CDP' : 'Playwright'}
                  </Tag>
                </div>
              </Col>
              <Col xs={12} md={6} xl={4}>
                <Text type="secondary">已有浏览器连接</Text>
                <div style={{ marginTop: 6 }}>
                  <Tag color={browserStatus.connect_existing ? 'success' : 'default'}>
                    {browserStatus.connect_existing
                      ? `CDP :${browserStatus.debug_port || 9222}`
                      : '使用专用 Profile'}
                  </Tag>
                </div>
              </Col>
              <Col xs={12} md={6} xl={4}>
                <Text type="secondary">浏览器账号</Text>
                <div style={{ marginTop: 6 }}>
                  <Tag color={(browserStatus.synced_account_count || 0) > 0 ? 'success' : 'default'}>
                    已同步 {browserStatus.synced_account_count || 0}
                  </Tag>
                </div>
              </Col>
              <Col xs={12} md={6} xl={4}>
                <Text type="secondary">LLM</Text>
                <div style={{ marginTop: 6 }}>
                  <Tag color={browserStatus.llm_configured ? 'success' : 'error'}>
                    {browserStatus.llm_configured ? '已配置' : '未配置'}
                  </Tag>
                </div>
              </Col>
            </Row>
          </Card>

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
          {usage.write_budget_exhausted && (
            <Alert
              type="warning"
              showIcon
              message="本日写入预算已达到上限；浏览器采集仍可继续"
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
                disabled={!isAdmin || !automation.credentials?.x_client_id || !automation.credentials?.token_encryption_key}
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
            {(!automation.credentials?.x_client_id || !automation.credentials?.token_encryption_key) && (
              <Alert
                type="info"
                showIcon
                message="OAuth 写入未配置；浏览器采集和 AI 草稿仍可正常使用"
                description="只有需要通过官方写入接口发布时，才需要配置 X_CLIENT_ID、回调地址和 TOKEN_ENCRYPTION_KEY。"
                style={{ marginBottom: 12 }}
              />
            )}
            <Table<XAccount>
              rowKey={(record) => String(record.id)}
              dataSource={accounts}
              locale={{ emptyText: <Empty description="尚未同步浏览器账号或绑定 OAuth 账号" /> }}
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
                      {!record.token_configured && <Tag color="blue">浏览器草稿账号</Tag>}
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
                        disabled={!isAdmin || record.status !== 'active' || !record.token_configured}
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
                      disabled={!isAdmin || (!value && !record.automated_label_enabled)}
                      loading={actionLoading === `account-auto_reply_enabled-${record.id}`}
                      onChange={(checked) => confirmAccountToggle(record, 'auto_reply_enabled', checked, '自动回复')}
                    />
                  ),
                },
                {
                  title: '操作',
                  key: 'actions',
                  fixed: 'right',
                  width: 150,
                  render: (_, record) => record.token_configured ? (
                    <Popconfirm
                      title="确认测试 OAuth 写入账号连接？"
                      description="验证 Token、scope 和浏览器身份，不会发布内容。"
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
                        测试 OAuth
                      </Button>
                    </Popconfirm>
                  ) : (
                    <Button
                      icon={<ThunderboltOutlined />}
                      loading={actionLoading === 'browser-sync'}
                      disabled={
                        !canOperate
                        || !automation.read_enabled
                        || (browserStatus.profile_in_use && !browserStatus.cdp_ready)
                      }
                      onClick={() => void handleSyncBrowserAccount()}
                    >
                      检测浏览器
                    </Button>
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
                            {auditHttpStatus(log) && <Tag color="error">{auditHttpStatus(log)}</Tag>}
                            {auditErrorCode(log) && <Tag>{auditErrorCode(log)}</Tag>}
                            <Text>{log.action || 'X 运行任务'}</Text>
                          </Space>
                        )}
                        description={(
                          <div>
                            <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
                              {auditDetail(log)}
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
            <Tag color={browserStatus.cdp_ready ? 'success' : 'processing'}>
              浏览器写入 {browserStatus.cdp_ready ? '已连接' : '发送时连接'}
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

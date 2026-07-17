import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Divider,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Result,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
  theme,
} from 'antd';
import {
  ArrowLeftOutlined,
  BarChartOutlined,
  CommentOutlined,
  ExclamationCircleOutlined,
  ExportOutlined,
  EyeOutlined,
  HeartOutlined,
  MessageOutlined,
  ReloadOutlined,
  RetweetOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useNavigate, useParams } from 'react-router-dom';
import { authStorage } from '../api/auth';
import {
  analyzeXConversation,
  collectXThread,
  generateXReplyCandidates,
  getXAccounts,
  getXAutomationStatus,
  getXBrowserStatus,
  getXConversation,
  getXPost,
  sendXPostComment,
  type XAccount,
  type XAutomationStatus,
  type XBrowserStatus,
  type XConversation,
  type XConversationMeta,
  type XPost,
  type XPublicMetrics,
  type XThreadAnalysis,
  type XThreadNode,
} from '../api/xOperations';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const STATUS_LABELS: Record<string, string> = {
  pending: '等待采集',
  sampling: '采集中',
  ready: '采集完成',
  analysed: '分析完成',
  archived: '已归档',
  failed: '采集失败',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  sampling: 'processing',
  ready: 'success',
  analysed: 'blue',
  archived: 'default',
  failed: 'error',
};

const SENTIMENT_LABELS: Record<string, string> = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
};

const SENTIMENT_COLORS: Record<string, string> = {
  positive: '#52c41a',
  neutral: '#1677ff',
  negative: '#ff4d4f',
};

const RECOMMENDATION_LABELS: Record<string, string> = {
  human_review: '建议人工审核后参与',
  monitor_only: '建议仅监控，不主动参与',
  do_not_reply: '不建议回复',
  reply: '可以准备回复草稿',
};

function parseJson<T>(value: unknown, fallback: T): T {
  if (value == null) return fallback;
  if (typeof value !== 'string') return value as T;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function errorDetail(error: unknown): string {
  const candidate = error as {
    response?: { data?: { detail?: unknown; message?: unknown }; status?: number };
    message?: string;
  };
  const detail = candidate.response?.data?.detail ?? candidate.response?.data?.message;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === 'string') return record.message;
  }
  return candidate.message || '请求失败';
}

function errorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } }).response?.status;
}

function formatDate(value?: string | number): string {
  if (!value) return '—';
  const timestamp = typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value;
  const parsed = dayjs(timestamp);
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : String(value);
}

function formatCount(value?: number): string {
  if (value == null || Number.isNaN(value)) return '0';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function postId(post?: XPost | null): string {
  return String(post?.x_post_id || post?.id || '');
}

function postAuthor(post?: XPost | null): string {
  return post?.author_display_name || post?.author_name || post?.author_username || '未知作者';
}

function postUrl(post?: XPost | null, fallback = ''): string {
  return post?.post_url || post?.url || `https://x.com/i/web/status/${postId(post) || fallback}`;
}

function metricsOf(post?: XPost | null): XPublicMetrics {
  if (!post) return {};
  const stored = parseJson<XPublicMetrics>(post.public_metrics_json, {});
  return {
    reply_count: post.reply_count ?? post.public_metrics?.reply_count ?? stored.reply_count,
    like_count: post.like_count ?? post.public_metrics?.like_count ?? stored.like_count,
    retweet_count: post.retweet_count ?? post.public_metrics?.retweet_count ?? stored.retweet_count,
    quote_count: post.quote_count ?? post.public_metrics?.quote_count ?? stored.quote_count,
    impression_count: post.public_metrics?.impression_count ?? stored.impression_count,
    view_count: post.public_metrics?.view_count ?? stored.view_count,
  };
}

function uniquePosts(posts: XPost[]): XPost[] {
  const seen = new Set<string>();
  return posts.filter((post) => {
    const id = postId(post);
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

interface ViewpointRow {
  text: string;
  sentiment?: string;
  share?: number;
  postIds?: string[];
}

interface RiskRow {
  category: string;
  count?: number;
}

function stringList(value: unknown): string[] {
  const parsed = parseJson<unknown>(value, value);
  if (Array.isArray(parsed)) {
    return parsed.map((item) => {
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object') {
        const row = item as Record<string, unknown>;
        return String(row.text || row.summary || row.label || row.question || '');
      }
      return '';
    }).filter(Boolean);
  }
  if (typeof parsed === 'string') {
    return parsed.split(/\n|；|;/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function viewpointRows(value: unknown): ViewpointRow[] {
  const parsed = parseJson<unknown>(value, []);
  if (!Array.isArray(parsed)) return [];
  return parsed.map((item) => {
    if (typeof item === 'string') return { text: item };
    const row = (item || {}) as Record<string, unknown>;
    const shareValue = Number(row.sample_share_estimate ?? row.share ?? 0);
    return {
      text: String(row.viewpoint || row.summary || row.label || row.text || ''),
      sentiment: String(row.sentiment || ''),
      share: Number.isFinite(shareValue) && shareValue > 0 ? shareValue : undefined,
      postIds: Array.isArray(row.representative_post_ids)
        ? row.representative_post_ids.map(String)
        : undefined,
    };
  }).filter((item) => item.text);
}

function riskRows(value: unknown): RiskRow[] {
  const parsed = parseJson<unknown>(value, []);
  if (!Array.isArray(parsed)) return [];
  return parsed.map((item) => {
    if (typeof item === 'string') return { category: item };
    const row = (item || {}) as Record<string, unknown>;
    const count = Number(row.sample_count ?? row.count ?? 0);
    return {
      category: String(row.category || row.risk || row.label || row.summary || ''),
      count: Number.isFinite(count) && count > 0 ? count : undefined,
    };
  }).filter((item) => item.category);
}

function ThreadNodes({ nodes, depth = 0 }: { nodes: XThreadNode[]; depth?: number }) {
  const {
    token: { colorBgContainer, colorBorderSecondary, colorFillAlter, colorPrimary },
  } = theme.useToken();

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {nodes.map((node) => {
        const metrics = metricsOf(node);
        return (
          <div
            key={postId(node)}
            style={{
              marginLeft: Math.min(depth, 3) * 18,
              padding: '14px 16px',
              border: `1px solid ${colorBorderSecondary}`,
              borderLeft: depth > 0 ? `3px solid ${colorPrimary}` : undefined,
              borderRadius: 10,
              background: depth % 2 ? colorFillAlter : colorBgContainer,
            }}
          >
            <Row justify="space-between" align="middle" gutter={[12, 8]}>
              <Col>
                <Space wrap>
                  <Avatar size="small" icon={<UserOutlined />} />
                  <Text strong>{postAuthor(node)}</Text>
                  {node.author_username && <Text type="secondary">@{node.author_username}</Text>}
                  <Tag>{depth === 0 ? '直接回复' : `第 ${depth + 1} 层回复`}</Tag>
                </Space>
              </Col>
              <Col>
                <Button
                  type="link"
                  size="small"
                  icon={<ExportOutlined />}
                  onClick={() => window.open(postUrl(node), '_blank', 'noopener,noreferrer')}
                >
                  X 原文
                </Button>
              </Col>
            </Row>
            <Paragraph style={{ margin: '10px 0 8px', whiteSpace: 'pre-wrap', fontSize: 14 }}>
              {node.text || '该回复正文不可用'}
            </Paragraph>
            <Space size={16} wrap>
              <Text type="secondary">{formatDate(node.created_at_x || node.created_at)}</Text>
              <Text type="secondary"><MessageOutlined /> {formatCount(metrics.reply_count)}</Text>
              <Text type="secondary"><HeartOutlined /> {formatCount(metrics.like_count)}</Text>
              <Text type="secondary"><RetweetOutlined /> {formatCount(metrics.retweet_count)}</Text>
              {node.lang && <Tag bordered={false}>{node.lang}</Tag>}
            </Space>
            {node.children?.length ? (
              <div style={{ marginTop: 12 }}>
                <ThreadNodes nodes={node.children} depth={depth + 1} />
              </div>
            ) : null}
          </div>
        );
      })}
    </Space>
  );
}

export default function XPostDetail() {
  const { postId: routePostId = '' } = useParams();
  const navigate = useNavigate();
  const [messageApi, messageContextHolder] = message.useMessage();
  const {
    token: {
      colorBgLayout,
      colorBorderSecondary,
      colorFillAlter,
      colorInfoBg,
      colorPrimary,
      colorTextSecondary,
    },
  } = theme.useToken();
  const currentUser = useMemo(() => authStorage.getUser(), []);
  const canOperate = currentUser?.role !== 'viewer';

  const [post, setPost] = useState<XPost | null>(null);
  const [conversation, setConversation] = useState<XConversation | null>(null);
  const [conversationMeta, setConversationMeta] = useState<XConversationMeta | null>(null);
  const [accounts, setAccounts] = useState<XAccount[]>([]);
  const [automation, setAutomation] = useState<XAutomationStatus | null>(null);
  const [browserStatus, setBrowserStatus] = useState<XBrowserStatus>({});
  const [selectedAccountId, setSelectedAccountId] = useState<string | number>();
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [pageError, setPageError] = useState('');
  const [conversationError, setConversationError] = useState('');
  const [generatedCount, setGeneratedCount] = useState(0);
  const [commentModalOpen, setCommentModalOpen] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [commentConfirmed, setCommentConfirmed] = useState(false);
  const [sentComment, setSentComment] = useState<{ id?: string; url?: string; username?: string } | null>(null);

  const loadPage = useCallback(async (showInitial = false) => {
    if (!routePostId) {
      setPageError('缺少帖子 ID');
      setInitialLoading(false);
      return;
    }
    if (showInitial) setInitialLoading(true);
    setRefreshing(true);
    setPageError('');
    setConversationError('');
    try {
      const [detailResult, accountResult, automationResult, browserResult] = await Promise.allSettled([
        getXPost(routePostId),
        getXAccounts(),
        getXAutomationStatus(),
        getXBrowserStatus(),
      ]);
      if (detailResult.status === 'rejected') throw detailResult.reason;

      const detail = detailResult.value;
      setPost(detail.post);
      setConversationMeta(detail.conversation || null);

      if (accountResult.status === 'fulfilled') {
        const nextAccounts = accountResult.value.items || [];
        setAccounts(nextAccounts);
        setSelectedAccountId((previous) => {
          if (previous != null && nextAccounts.some((account) => String(account.id) === String(previous))) {
            return previous;
          }
          return nextAccounts.find((account) => (
            account.status === 'active' && account.write_enabled && account.token_configured
          ))?.id ?? nextAccounts.find((account) => account.status === 'active')?.id ?? nextAccounts[0]?.id;
        });
      }
      if (automationResult.status === 'fulfilled') {
        const raw = automationResult.value as XAutomationStatus & {
          status?: XAutomationStatus;
          controls?: XAutomationStatus;
        };
        setAutomation(raw.status || raw.controls || raw);
      }
      if (browserResult.status === 'fulfilled') setBrowserStatus(browserResult.value);

      const rootId = String(
        detail.conversation?.root_post_id
        || detail.post.conversation_id
        || detail.post.x_post_id
        || routePostId,
      );
      try {
        const thread = await getXConversation(rootId);
        setConversation(thread);
        setConversationMeta(thread.conversation || detail.conversation || null);
      } catch (error) {
        setConversation(null);
        if (errorStatus(error) !== 404) setConversationError(errorDetail(error));
      }
    } catch (error) {
      setPageError(errorDetail(error));
    } finally {
      setInitialLoading(false);
      setRefreshing(false);
    }
  }, [routePostId]);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      void loadPage(true);
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [loadPage]);

  const rootPostId = String(
    conversationMeta?.root_post_id
    || post?.conversation_id
    || post?.x_post_id
    || routePostId,
  );
  const allPosts = useMemo(() => uniquePosts([
    ...(post ? [post] : []),
    ...(conversation?.posts || []),
    ...(conversation?.replies || []),
  ]), [post, conversation]);
  const rootPost = allPosts.find((item) => postId(item) === rootPostId) || post;
  const replies = allPosts.filter((item) => postId(item) !== postId(rootPost));
  const rootMetrics = metricsOf(rootPost);
  const totalEngagement = Number(rootMetrics.like_count || 0)
    + Number(rootMetrics.reply_count || 0)
    + Number(rootMetrics.retweet_count || 0)
    + Number(rootMetrics.quote_count || 0);

  const analysis: XThreadAnalysis | null = conversation?.analysis || null;
  const analysisOutput = parseJson<Record<string, unknown>>(analysis?.output_json, {});
  const sentimentPayload = parseJson<Record<string, unknown>>(analysis?.sentiment_json, {});
  const distribution = (
    sentimentPayload.distribution
    || analysisOutput.sentiment_distribution
    || {}
  ) as Record<string, number>;
  const dominantSentiment = String(
    sentimentPayload.dominant_sentiment
    || sentimentPayload.sentiment
    || analysisOutput.dominant_sentiment
    || 'neutral',
  );
  const sampleCount = Number(analysis?.sample_count || analysisOutput.sample_count || replies.length || 0);
  const sentimentTotal = Object.values(distribution).reduce((total, value) => total + Number(value || 0), 0)
    || sampleCount
    || 1;
  const viewpoints = viewpointRows(
    analysis?.viewpoints
    || analysis?.core_viewpoints
    || analysis?.viewpoints_json
    || analysisOutput.main_viewpoints,
  );
  const risks = riskRows(analysis?.risks_json || analysisOutput.misinformation_risks);
  const questions = stringList(analysis?.common_questions || analysisOutput.common_questions);
  const analysisRisk = String(analysis?.risk_level || analysisOutput.risk_level || (risks.length ? 'medium' : 'low'));
  const recommendation = String(
    analysis?.reply_recommendation
    || analysis?.recommended_action
    || analysisOutput.reply_recommendation
    || 'human_review',
  );
  const brandOpportunity = String(
    analysisOutput.brand_opportunity
    || analysis?.recommended_participation
    || analysis?.recommended_action
    || '仅在能够直接回答问题、且事实经过核验时参与。',
  );

  const conversationTree = conversation?.tree || [];
  const treeRoot = conversationTree.find((node) => postId(node) === postId(rootPost));
  const threadNodes = treeRoot?.children?.length
    ? treeRoot.children
    : conversationTree.length
      ? conversationTree.filter((node) => postId(node) !== postId(rootPost))
      : replies as XThreadNode[];
  const conversationStatus = String(conversationMeta?.status || (analysis ? 'analysed' : conversation ? 'ready' : 'pending'));
  const draftEngineAvailable = Boolean(
    automation?.credentials?.llm || automation?.credentials?.fallback_drafts_available,
  );
  const browserSessionAvailable = Boolean(
    browserStatus.cdp_ready
    || (
      browserStatus.profile_exists
      && browserStatus.cookie_store_detected
      && !browserStatus.profile_in_use
    ),
  );
  const commentWriteReady = Boolean(
    automation?.write_enabled
    && !automation.global_kill_switch
    && browserSessionAvailable,
  );
  const commentUnavailableReason = !canOperate
    ? '当前账号没有 X 运营操作权限'
    : !automation?.write_enabled
      ? '请先在“自动化控制”中开启全局写入'
      : automation.global_kill_switch
        ? '全局 Kill Switch 已开启，当前禁止写入 X'
        : browserStatus.profile_in_use && !browserStatus.cdp_ready
          ? '专用 X 浏览器未开放 CDP，请从系统重新打开专用登录窗口'
          : !browserStatus.cookie_store_detected
            ? '请先在专用 X 浏览器中登录账号'
            : '专用 X 浏览器尚不可用';

  const runAction = async (
    key: string,
    action: () => Promise<unknown>,
    successMessage: string,
  ): Promise<unknown | null> => {
    setActionLoading(key);
    try {
      const result = await action() as { message?: string };
      messageApi.success(result.message || successMessage);
      return result;
    } catch (error) {
      messageApi.error(errorDetail(error));
      return null;
    } finally {
      setActionLoading('');
    }
  };

  const handleCollect = async () => {
    const result = await runAction(
      'collect',
      () => collectXThread(rootPostId || routePostId),
      '帖子线程采集完成',
    );
    if (result) await loadPage(false);
  };

  const handleAnalyze = async () => {
    const result = await runAction(
      'analyze',
      () => analyzeXConversation(rootPostId),
      '线程分析完成',
    );
    if (result) await loadPage(false);
  };

  const handleGenerate = async () => {
    if (!post || selectedAccountId == null) {
      messageApi.warning('请先选择用于生成回复语气的 X 账号');
      return;
    }
    const result = await runAction(
      'generate',
      () => generateXReplyCandidates(post.id, {
        account_id: selectedAccountId,
        candidate_count: 3,
      }),
      '已生成回复候选并进入人工审核队列',
    ) as { total?: number; items?: unknown[] } | null;
    if (result) setGeneratedCount(result.total || result.items?.length || 3);
  };

  const handleSendComment = async () => {
    if (!post || !commentText.trim() || !commentConfirmed) return;
    const result = await runAction(
      'send-comment',
      () => sendXPostComment(post.id, {
        text: commentText.trim(),
        explicit_confirmation: true,
      }),
      '评论已通过当前登录浏览器发布到 X',
    ) as {
      x_post_id?: string;
      x_post_url?: string;
      prepared?: { identity?: { username?: string } };
    } | null;
    if (!result) return;
    setSentComment({
      id: result.x_post_id,
      url: result.x_post_url,
      username: result.prepared?.identity?.username,
    });
    setCommentModalOpen(false);
    setCommentText('');
    setCommentConfirmed(false);
  };

  if (initialLoading) {
    return (
      <div style={{ minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {messageContextHolder}
        <Spin size="large" tip="正在加载帖子、评论线程和分析结果" />
      </div>
    );
  }

  if (pageError || !post) {
    return (
      <Result
        status="error"
        title="帖子详情加载失败"
        subTitle={pageError || '帖子不存在或无权访问'}
        extra={[
          <Button key="back" onClick={() => navigate('/x')}>返回 X 运营</Button>,
          <Button key="retry" type="primary" onClick={() => void loadPage(true)}>重新加载</Button>,
        ]}
      />
    );
  }

  return (
    <div style={{ maxWidth: 1540, margin: '0 auto' }}>
      {messageContextHolder}
      <Row justify="space-between" align="middle" gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col>
          <Space align="start">
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/x?tab=posts')}
              style={{ marginTop: 4 }}
            />
            <div>
              <Space wrap>
                <Title level={3} style={{ margin: 0 }}>帖子分析详情</Title>
                <Tag color={STATUS_COLORS[conversationStatus] || 'default'}>
                  {STATUS_LABELS[conversationStatus] || conversationStatus}
                </Tag>
                {analysis && <Tag color="blue">已有分析</Tag>}
              </Space>
              <Text type="secondary">帖子 ID：{postId(rootPost) || routePostId}</Text>
            </div>
          </Space>
        </Col>
        <Col>
          <Space wrap>
            <Button
              icon={<ReloadOutlined />}
              loading={refreshing}
              onClick={() => void loadPage(false)}
            >
              刷新数据
            </Button>
            <Button
              icon={<ExportOutlined />}
              onClick={() => window.open(postUrl(rootPost, routePostId), '_blank', 'noopener,noreferrer')}
            >
              打开 X 原帖
            </Button>
          </Space>
        </Col>
      </Row>

      {conversationError && (
        <Alert
          type="warning"
          showIcon
          message="评论线程读取失败"
          description={conversationError}
          style={{ marginBottom: 16 }}
        />
      )}
      {!conversation && !conversationError && (
        <Alert
          type="info"
          showIcon
          message="该帖子尚未采集评论线程"
          description="可以先点击“采集评论”，系统会通过当前登录的专用 Chrome 会话读取可见回复。"
          style={{ marginBottom: 16 }}
        />
      )}
      {conversationMeta?.last_error && (
        <Alert
          type="error"
          showIcon
          message="最近一次采集失败"
          description={conversationMeta.last_error}
          style={{ marginBottom: 16 }}
        />
      )}
      {generatedCount > 0 && (
        <Alert
          type="success"
          showIcon
          closable
          message={`已生成 ${generatedCount} 条回复候选`}
          description={(
            <Space wrap>
              <Text>候选不会自动发布，已进入人工审核队列。</Text>
              <Button type="link" onClick={() => navigate('/x?tab=reviews')}>前往审核队列</Button>
            </Space>
          )}
          style={{ marginBottom: 16 }}
        />
      )}
      {sentComment && (
        <Alert
          type="success"
          showIcon
          closable
          onClose={() => setSentComment(null)}
          message="评论已成功发布到 X"
          description={(
            <Space wrap>
              {sentComment.username && <Text>浏览器账号：@{sentComment.username}</Text>}
              {sentComment.id && <Text>评论帖子 ID：{sentComment.id}</Text>}
              {sentComment.url && (
                <Button
                  type="link"
                  icon={<ExportOutlined />}
                  onClick={() => window.open(sentComment.url, '_blank', 'noopener,noreferrer')}
                >
                  查看已发布评论
                </Button>
              )}
            </Space>
          )}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card size="small" style={{ marginBottom: 16, background: colorBgLayout }}>
        <Row gutter={[12, 12]} align="middle">
          <Col flex="auto">
            <Space wrap size={12}>
              <Popconfirm
                title="采集该帖的评论线程？"
                description="将控制专用浏览器打开 X 帖子页并采集当前可见回复。"
                okText="确认采集"
                cancelText="取消"
                onConfirm={handleCollect}
              >
                <Button
                  type="primary"
                  icon={<CommentOutlined />}
                  loading={actionLoading === 'collect'}
                  disabled={!canOperate || automation?.read_enabled === false}
                >
                  {conversation ? '重新采集评论' : '采集评论'}
                </Button>
              </Popconfirm>
              <Popconfirm
                title="分析已采集的评论线程？"
                description="分析结果只保存在系统内，不会向 X 发布内容。"
                okText="确认分析"
                cancelText="取消"
                onConfirm={handleAnalyze}
              >
                <Button
                  icon={<BarChartOutlined />}
                  loading={actionLoading === 'analyze'}
                  disabled={!canOperate || !conversation}
                >
                  {analysis ? '重新分析' : '分析线程'}
                </Button>
              </Popconfirm>
              <Select
                style={{ minWidth: 230 }}
                placeholder="选择生成回复的 X 账号"
                value={selectedAccountId}
                onChange={setSelectedAccountId}
                options={accounts.map((account) => ({
                  value: account.id,
                  label: `${account.display_name || account.username || `账号 ${account.id}`}${account.username ? ` (@${account.username})` : ''}`,
                  disabled: Boolean(account.status && account.status !== 'active'),
                }))}
                notFoundContent="尚未绑定 X 账号"
              />
              <Popconfirm
                title="生成 3 条 AI 回复候选？"
                description="候选只进入人工审核队列，不会自动发布。"
                okText="确认生成"
                cancelText="取消"
                onConfirm={handleGenerate}
              >
                <Button
                  icon={<RobotOutlined />}
                  loading={actionLoading === 'generate'}
                  disabled={!canOperate || !analysis || !draftEngineAvailable || selectedAccountId == null}
                >
                  生成回复候选
                </Button>
              </Popconfirm>
              <Tooltip title={commentWriteReady ? '核对账号和最终文本后发送单条评论' : commentUnavailableReason}>
                <span>
                  <Button
                    danger
                    icon={<SendOutlined />}
                    disabled={!canOperate || !commentWriteReady}
                    onClick={() => setCommentModalOpen(true)}
                  >
                    发送评论
                  </Button>
                </span>
              </Tooltip>
            </Space>
          </Col>
          <Col>
            <Text type="secondary">
              {automation?.credentials?.llm
                ? '使用已配置 LLM，结果需人工审核'
                : draftEngineAvailable
                  ? '使用本地安全草稿，结果需人工审核'
                  : '回复生成服务尚未配置'}
            </Text>
          </Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small"><Statistic title="X 显示回复" value={rootMetrics.reply_count || 0} prefix={<MessageOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small"><Statistic title="本地已采集" value={replies.length} suffix="条" prefix={<CommentOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small"><Statistic title="线程最大深度" value={conversationMeta?.max_depth || (threadNodes.length ? 1 : 0)} suffix="层" /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small"><Statistic title="原帖总互动" value={totalEngagement} /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small"><Statistic title="分析样本" value={sampleCount} suffix="条" /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic title="主导情绪" value={SENTIMENT_LABELS[dominantSentiment] || dominantSentiment || '未分析'} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} xl={15}>
          <Card
            title="原帖"
            extra={<Tag>{rootPost?.lang || '语言未标注'}</Tag>}
            style={{ height: '100%' }}
          >
            <Row justify="space-between" align="top" gutter={[12, 12]}>
              <Col>
                <Space>
                  <Avatar size={42} icon={<UserOutlined />} style={{ background: colorPrimary }} />
                  <div>
                    <Text strong style={{ fontSize: 16 }}>{postAuthor(rootPost)}</Text>
                    <br />
                    <Text type="secondary">
                      {rootPost?.author_username ? `@${rootPost.author_username}` : '用户名未同步'}
                    </Text>
                  </div>
                </Space>
              </Col>
              <Col><Text type="secondary">{formatDate(rootPost?.created_at_x || rootPost?.created_at)}</Text></Col>
            </Row>
            <Paragraph style={{ margin: '20px 0', whiteSpace: 'pre-wrap', fontSize: 16, lineHeight: 1.8 }}>
              {rootPost?.text || '原帖正文已删除或尚未同步'}
            </Paragraph>
            <Divider style={{ margin: '12px 0' }} />
            <Space size={22} wrap>
              <Text><MessageOutlined /> {formatCount(rootMetrics.reply_count)} 回复</Text>
              <Text><HeartOutlined /> {formatCount(rootMetrics.like_count)} 喜欢</Text>
              <Text><RetweetOutlined /> {formatCount(rootMetrics.retweet_count)} 转发</Text>
              <Text><EyeOutlined /> {formatCount(rootMetrics.view_count ?? rootMetrics.impression_count)} 浏览</Text>
              {rootPost?.possibly_sensitive && <Tag color="error">X 敏感内容标记</Tag>}
              {rootPost?.compliance_status && <Tag>{rootPost.compliance_status}</Tag>}
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card
            title="AI 分析摘要"
            extra={analysis ? <Tag color={analysisRisk === 'high' ? 'error' : analysisRisk === 'medium' ? 'warning' : 'success'}>{analysisRisk === 'low' ? '低风险' : analysisRisk === 'medium' ? '中风险' : analysisRisk === 'high' ? '高风险' : analysisRisk}</Tag> : null}
            style={{ height: '100%' }}
          >
            {!analysis ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={conversation ? '线程已采集，尚未执行分析' : '请先采集评论线程'}
              >
                <Button
                  type="primary"
                  icon={<BarChartOutlined />}
                  disabled={!canOperate || !conversation}
                  onClick={() => void handleAnalyze()}
                >
                  开始分析
                </Button>
              </Empty>
            ) : (
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                <Paragraph style={{ fontSize: 15, lineHeight: 1.7, marginBottom: 0 }}>
                  {analysis.summary || String(analysisOutput.summary || '暂无摘要')}
                </Paragraph>
                <Alert
                  type={recommendation === 'monitor_only' || recommendation === 'do_not_reply' ? 'warning' : 'info'}
                  showIcon
                  icon={<SafetyCertificateOutlined />}
                  message={RECOMMENDATION_LABELS[recommendation] || recommendation}
                  description={brandOpportunity}
                />
                <Space wrap>
                  <Tag color={SENTIMENT_COLORS[dominantSentiment]}>
                    主导情绪：{SENTIMENT_LABELS[dominantSentiment] || dominantSentiment}
                  </Tag>
                  <Tag>样本 {sampleCount}</Tag>
                  {analysis.model_version && <Tag>{analysis.model_version}</Tag>}
                </Space>
                <Text type="secondary">分析时间：{formatDate(analysis.analysed_at || analysis.analyzed_at)}</Text>
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Card styles={{ body: { paddingTop: 8 } }}>
        <Tabs
          defaultActiveKey="thread"
          items={[
            {
              key: 'thread',
              label: `评论线程（${replies.length}）`,
              children: threadNodes.length ? (
                <ThreadNodes nodes={threadNodes} />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={conversation ? '本次没有采集到可见回复' : '尚未采集评论线程'}
                />
              ),
            },
            {
              key: 'insights',
              label: '分析洞察',
              children: !analysis ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未生成分析结果" />
              ) : (
                <Row gutter={[20, 20]}>
                  <Col xs={24} lg={8}>
                    <Card size="small" title="情绪分布" style={{ height: '100%' }}>
                      <Space direction="vertical" size={14} style={{ width: '100%' }}>
                        {['positive', 'neutral', 'negative'].map((sentiment) => {
                          const count = Number(distribution[sentiment] || 0);
                          const percent = Math.round((count / sentimentTotal) * 100);
                          return (
                            <div key={sentiment}>
                              <Row justify="space-between">
                                <Text>{SENTIMENT_LABELS[sentiment]}</Text>
                                <Text type="secondary">{count} 条 / {percent}%</Text>
                              </Row>
                              <Progress
                                percent={percent}
                                showInfo={false}
                                strokeColor={SENTIMENT_COLORS[sentiment]}
                              />
                            </div>
                          );
                        })}
                      </Space>
                    </Card>
                  </Col>
                  <Col xs={24} lg={8}>
                    <Card size="small" title="主要观点" style={{ height: '100%' }}>
                      {viewpoints.length ? (
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                          {viewpoints.map((viewpoint, index) => (
                            <div key={`${viewpoint.text}-${index}`} style={{ padding: 12, borderRadius: 8, background: colorFillAlter }}>
                              <Space wrap style={{ marginBottom: 6 }}>
                                <Tag color="blue">观点 {index + 1}</Tag>
                                {viewpoint.sentiment && (
                                  <Tag color={SENTIMENT_COLORS[viewpoint.sentiment]}>
                                    {SENTIMENT_LABELS[viewpoint.sentiment] || viewpoint.sentiment}
                                  </Tag>
                                )}
                                {viewpoint.share != null && <Tag>约 {Math.round(viewpoint.share * 100)}%</Tag>}
                              </Space>
                              <Paragraph style={{ marginBottom: 0 }}>{viewpoint.text}</Paragraph>
                            </div>
                          ))}
                        </Space>
                      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无观点聚类" />}
                    </Card>
                  </Col>
                  <Col xs={24} lg={8}>
                    <Card size="small" title="风险与待核验事项" style={{ height: '100%' }}>
                      {risks.length ? (
                        <Space direction="vertical" size={10} style={{ width: '100%' }}>
                          {risks.map((risk, index) => (
                            <Alert
                              key={`${risk.category}-${index}`}
                              type="warning"
                              showIcon
                              icon={<ExclamationCircleOutlined />}
                              message={risk.category}
                              description={risk.count ? `代表样本 ${risk.count} 条` : undefined}
                            />
                          ))}
                        </Space>
                      ) : (
                        <Alert type="success" showIcon message="当前样本未发现显式风险信号" />
                      )}
                    </Card>
                  </Col>
                  <Col xs={24} lg={12}>
                    <Card size="small" title="常见问题">
                      {questions.length ? (
                        <Space wrap>{questions.map((question) => <Tag key={question}>{question}</Tag>)}</Space>
                      ) : <Text type="secondary">当前样本没有提取到明确问题。</Text>}
                    </Card>
                  </Col>
                  <Col xs={24} lg={12}>
                    <Card size="small" title="运营参与建议">
                      <Alert
                        type={recommendation === 'monitor_only' ? 'warning' : 'info'}
                        showIcon
                        message={RECOMMENDATION_LABELS[recommendation] || recommendation}
                        description={brandOpportunity}
                      />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'collection',
              label: '采集与分析记录',
              children: (
                <Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
                  <Descriptions.Item label="根帖 ID">{rootPostId || '—'}</Descriptions.Item>
                  <Descriptions.Item label="X Conversation ID">{conversationMeta?.x_conversation_id || post?.conversation_id || '—'}</Descriptions.Item>
                  <Descriptions.Item label="会话状态">
                    <Tag color={STATUS_COLORS[conversationStatus] || 'default'}>
                      {STATUS_LABELS[conversationStatus] || conversationStatus}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="采样策略">{conversationMeta?.sample_strategy || 'balanced'}</Descriptions.Item>
                  <Descriptions.Item label="采样上限">{conversationMeta?.sample_limit ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label="本地帖子总数">{conversationMeta?.total_post_count ?? allPosts.length}</Descriptions.Item>
                  <Descriptions.Item label="已采样数量">{conversationMeta?.sampled_post_count ?? allPosts.length}</Descriptions.Item>
                  <Descriptions.Item label="最大线程深度">{conversationMeta?.max_depth ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label="线程语言">{conversationMeta?.language || rootPost?.lang || '—'}</Descriptions.Item>
                  <Descriptions.Item label="最后采集时间">{formatDate(conversationMeta?.last_collected_at)}</Descriptions.Item>
                  <Descriptions.Item label="最新帖子时间">{formatDate(conversationMeta?.newest_post_at)}</Descriptions.Item>
                  <Descriptions.Item label="下次计划刷新">{formatDate(conversationMeta?.next_refresh_at)}</Descriptions.Item>
                  <Descriptions.Item label="分析模型">{analysis?.model_version || '—'}</Descriptions.Item>
                  <Descriptions.Item label="Prompt 版本">{analysis?.prompt_version || '—'}</Descriptions.Item>
                  <Descriptions.Item label="分析状态">{analysis?.status || (analysis ? 'succeeded' : '—')}</Descriptions.Item>
                  <Descriptions.Item label="分析完成时间">{formatDate(analysis?.analysed_at || analysis?.analyzed_at)}</Descriptions.Item>
                  <Descriptions.Item label="输入内容哈希" span={2}>
                    <Text copyable={Boolean(analysis?.input_content_hash)} style={{ wordBreak: 'break-all' }}>
                      {analysis?.input_content_hash || '—'}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="最近采集错误" span={3}>
                    <Text type={conversationMeta?.last_error ? 'danger' : 'secondary'}>
                      {conversationMeta?.last_error || '无'}
                    </Text>
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
          ]}
        />
      </Card>

      <div
        style={{
          marginTop: 16,
          padding: 12,
          border: `1px solid ${colorBorderSecondary}`,
          borderRadius: 8,
          background: colorInfoBg,
          color: colorTextSecondary,
          fontSize: 12,
        }}
      >
        页面只展示当前租户已采集的数据。AI 回复候选仍进入审核队列；“发送评论”会自动使用专用浏览器当前登录的 X 账号，并在明确核对目标和最终文本后执行单条浏览器写入。
      </div>

      <Modal
        open={commentModalOpen}
        title="向该帖子发送评论"
        okText="确认发送到 X"
        cancelText="取消"
        width={680}
        confirmLoading={actionLoading === 'send-comment'}
        okButtonProps={{
          danger: true,
          disabled: !commentWriteReady || !commentText.trim() || !commentConfirmed,
        }}
        onOk={() => void handleSendComment()}
        onCancel={() => {
          if (actionLoading !== 'send-comment') setCommentModalOpen(false);
        }}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="这是一次真实的 X 写入操作"
            description="发送后评论会立即出现在 X。系统会自动识别专用浏览器当前登录账号，并重新检查 Kill Switch、目标帖子、预算、重复内容和策略限制；不需要 OAuth Token。"
          />
          <Card size="small" style={{ background: colorBgLayout }}>
            <Text type="secondary">回复目标</Text>
            <Paragraph ellipsis={{ rows: 3 }} style={{ margin: '6px 0 0' }}>
              {rootPost?.text || post.text || '原帖正文不可用'}
            </Paragraph>
          </Card>
          <Card size="small">
            <Space direction="vertical" size={4}>
              <Text strong>发送账号：专用浏览器当前登录账号</Text>
              <Text type="secondary">
                发送时自动识别并核对，不需要选择数据库账号或配置 OAuth Token。
              </Text>
              <Tag color={browserStatus.cdp_ready ? 'success' : 'processing'}>
                {browserStatus.cdp_ready
                  ? `CDP :${browserStatus.debug_port || 9222} 已连接`
                  : '发送时启动专用浏览器会话'}
              </Tag>
            </Space>
          </Card>
          <div>
            <Text strong>评论内容</Text>
            <TextArea
              autoFocus
              rows={5}
              maxLength={280}
              showCount
              value={commentText}
              placeholder="输入要发布到 X 的评论，最多 280 个字符"
              onChange={(event) => setCommentText(event.target.value)}
              style={{ marginTop: 8 }}
            />
          </div>
          <Checkbox
            checked={commentConfirmed}
            onChange={(event) => setCommentConfirmed(event.target.checked)}
          >
            我已核对目标帖子和最终评论文本，并确认使用浏览器当前登录账号立即发送
          </Checkbox>
        </Space>
      </Modal>
    </div>
  );
}

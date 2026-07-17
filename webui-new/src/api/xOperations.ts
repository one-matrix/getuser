import request from './request';

const X_BROWSER_REQUEST = { timeout: 210_000, skipRetry: true };
const X_MODEL_REQUEST = { timeout: 120_000, skipRetry: true };
const X_WRITE_REQUEST = { timeout: 120_000, skipRetry: true };

export interface XListResponse<T> {
  items: T[];
  total: number;
  limit?: number;
  offset?: number;
}

export interface XPublicMetrics {
  like_count?: number;
  reply_count?: number;
  retweet_count?: number;
  quote_count?: number;
  impression_count?: number;
  view_count?: number;
}

export interface XTopic {
  id: string | number;
  raw_name?: string;
  name?: string;
  topic_name?: string;
  normalized_name?: string;
  region_name?: string;
  region?: string | {
    id?: string | number;
    name?: string;
    woeid?: string | number;
    language?: string;
    country_code?: string;
  };
  woeid?: string | number;
  language?: string;
  rank?: number;
  rank_change?: number;
  volume?: number;
  post_count?: number;
  growth_rate?: number;
  representative_post?: string;
  summary?: string;
  core_viewpoints?: string[] | string;
  sentiment?: string;
  sentiment_score?: number;
  risk_level?: string;
  risk_score?: number;
  is_sensitive?: boolean;
  brand_relevance?: number;
  relevance_score?: number;
  estimated_cost?: number;
  read_cost?: number;
  captured_at?: string | number;
  updated_at?: string | number;
  latest_snapshot?: {
    rank?: number;
    rank_delta?: number;
    post_volume?: number;
    volume_delta?: number;
    post_count_estimate?: number;
    captured_at?: string | number;
  };
}

export interface XPost {
  id: string | number;
  x_post_id?: string;
  topic_id?: string | number;
  topic_name?: string;
  source_topic_id?: string | number;
  author_x_user_id?: string;
  author_username?: string;
  author_name?: string;
  author_display_name?: string;
  text?: string;
  lang?: string;
  created_at?: string | number;
  created_at_x?: string | number;
  conversation_id?: string;
  parent_post_id?: string;
  post_url?: string;
  url?: string;
  public_metrics?: XPublicMetrics;
  public_metrics_json?: XPublicMetrics | string;
  like_count?: number;
  reply_count?: number;
  retweet_count?: number;
  quote_count?: number;
  possibly_sensitive?: boolean;
  reply_settings?: string;
  risk_level?: string;
  analysis_status?: string;
  compliance_status?: string;
}

export interface XReplyCandidate {
  id: string | number;
  text?: string;
  generated_text?: string;
  edited_text?: string;
  style?: string;
  risk?: string;
  risk_level?: string;
  confidence?: number;
  requires_fact_check?: boolean;
  content_hash?: string;
  duplicate_score?: number;
  model_version?: string;
  prompt_version?: string;
  review_status?: string;
  created_at?: string | number;
}

export interface XPolicyCheck {
  rule?: string;
  name?: string;
  passed?: boolean;
  result?: string;
  reason?: string;
  evidence?: string;
}

export interface XThreadAnalysis {
  id?: string | number;
  root_post_id?: string;
  status?: string;
  input_content_hash?: string;
  schema_version?: string;
  error_message?: string;
  summary?: string;
  viewpoints?: Array<string | { label?: string; summary?: string; count?: number }>;
  core_viewpoints?: Array<string | { label?: string; summary?: string; count?: number }>;
  common_questions?: string[];
  disputed_facts?: string[];
  recommended_action?: string;
  recommended_participation?: string;
  risk_level?: string;
  sentiment?: string;
  sentiment_json?: Record<string, unknown> | string;
  viewpoints_json?: Array<string | { label?: string; summary?: string; count?: number }> | string;
  risks_json?: string[] | string;
  output_json?: Record<string, unknown> | string;
  reply_recommendation?: string;
  model_version?: string;
  prompt_version?: string;
  sample_count?: number;
  candidates?: XReplyCandidate[];
  analyzed_at?: string | number;
  analysed_at?: string | number;
}

export interface XThreadNode extends XPost {
  children?: XThreadNode[];
}

export interface XConversationMeta {
  id?: string | number;
  root_post_id?: string;
  x_conversation_id?: string;
  language?: string;
  status?: string;
  sample_strategy?: string;
  sample_limit?: number;
  total_post_count?: number;
  sampled_post_count?: number;
  max_depth?: number;
  newest_post_at?: string | number;
  last_collected_at?: string | number;
  next_refresh_at?: string | number;
  last_error?: string;
  created_at?: string | number;
  updated_at?: string | number;
}

export interface XConversation {
  conversation?: XConversationMeta;
  root_post?: XPost;
  posts?: XPost[];
  replies?: XPost[];
  tree?: XThreadNode[];
  analysis?: XThreadAnalysis | null;
  candidates?: XReplyCandidate[];
  total?: number;
}

export interface XReviewTask {
  id: string | number;
  status?: string;
  review_status?: string;
  source_post_id?: string | number;
  target_post_id?: string;
  target_post?: XPost;
  post?: XPost;
  account_id?: string | number;
  account_username?: string;
  account?: XAccount;
  interaction?: Record<string, unknown>;
  candidates?: XReplyCandidate[];
  candidate?: XReplyCandidate;
  selected_candidate_id?: string | number;
  final_text?: string;
  edited_text?: string;
  content_hash?: string;
  final_content_hash?: string;
  tone?: string;
  risk_level?: string;
  requires_fact_check?: boolean;
  api_reply_eligible?: boolean;
  manual_browser_publish_eligible?: boolean;
  eligibility_reason?: string;
  eligibility?: {
    eligible?: boolean;
    reason?: string;
    reasons?: string[];
    evidence?: Record<string, unknown>;
  };
  policy_checks?: XPolicyCheck[];
  rejection_reason?: string;
  review_reason?: string;
  reviewer_name?: string;
  created_at?: string | number;
  updated_at?: string | number;
  post_url?: string;
  manual_fallback?: {
    copy_text?: string;
    post_url?: string;
  };
}

export interface XCredentialStatus {
  browser_read_source?: boolean;
  browser_use_fallback?: boolean;
  llm?: boolean;
  write_token?: boolean;
  fallback_drafts_available?: boolean;
  x_client_id?: boolean;
  token_encryption_key?: boolean;
}

export interface XAutomationStatus {
  read_enabled: boolean;
  write_enabled: boolean;
  auto_reply_enabled: boolean;
  global_kill_switch: boolean;
  require_human_review: boolean;
  effective_write_allowed?: boolean;
  effective_browser_write_allowed?: boolean;
  credentials?: XCredentialStatus;
  reasons?: string[];
  daily_write_limit?: number;
  hourly_write_limit?: number;
  max_interactions_per_user?: number;
  min_reply_interval_seconds?: number;
  duplicate_threshold?: number;
  paused_regions?: string[];
  paused_keywords?: string[];
  high_risk_topics?: string[];
  auto_reply_intents?: string[];
  x_written_approval?: boolean;
  approval_reference?: string;
}

export interface XAccount {
  id: string | number;
  x_user_id?: string;
  username?: string;
  display_name?: string;
  account_type?: string;
  status?: string;
  granted_scopes?: string[] | string;
  token_expires_at?: string | number;
  token_configured?: boolean;
  token_expired?: boolean;
  automated_label_enabled?: boolean;
  x_written_approval?: boolean;
  approval_reference?: string;
  auto_reply_enabled?: boolean;
  write_enabled?: boolean;
  last_test_at?: string | number;
  last_error?: string;
  browser_synced?: boolean;
}

export interface XBrowserStatus {
  profile_source?: 'configured' | 'project_default' | string;
  profile_dir?: string;
  profile_exists?: boolean;
  cookie_store_detected?: boolean;
  profile_lock_detected?: boolean;
  profile_in_use?: boolean;
  cdp_mode?: boolean;
  cdp_ready?: boolean;
  connect_existing?: boolean;
  debug_port?: number;
  headless?: boolean;
  browser_use_fallback_enabled?: boolean;
  read_enabled?: boolean;
  synced_account_count?: number;
  llm_configured?: boolean;
}

export interface XInteraction {
  id: string | number;
  account_id: string | number;
  interaction_post_id?: string;
  actor_x_user_id?: string;
  interaction_type?: string;
  status?: string;
  opt_in_evidence_json?: Record<string, unknown> | string;
  eligibility_json?: Record<string, unknown> | string;
  is_opted_out?: boolean;
  replied_publish_job_id?: string | number;
  received_at?: string | number;
  processed_at?: string | number;
  created_at?: string | number;
  updated_at?: string | number;
  post?: XPost;
}

export interface XEndpointUsage {
  endpoint?: string;
  resource?: string;
  requests?: number;
  request_count?: number;
  read_count?: number;
  read_resource_count?: number;
  write_count?: number;
  estimated_cost?: number;
  estimated_cost_micros?: number;
  success_count?: number;
  error_count?: number;
  budget_limit_micros?: number;
  budget_exhausted?: boolean;
  limit?: number;
  remaining?: number;
  reset_at?: string | number;
}

export interface XUsageSummary {
  date?: string;
  post_reads?: number;
  unique_post_reads?: number;
  post_read_budget?: number;
  user_reads?: number;
  unique_user_reads?: number;
  user_read_budget?: number;
  writes?: number;
  write_count?: number;
  write_budget?: number;
  estimated_cost?: number;
  budget_ratio?: number;
  forced_read_only?: boolean;
  write_budget_exhausted?: boolean;
  request_count?: number;
  success_count?: number;
  error_count?: number;
  endpoints?: XEndpointUsage[];
  endpoint_usage?: XEndpointUsage[];
  recent_errors?: XAuditLog[];
}

export interface XAuditLog {
  id: string | number;
  action?: string;
  status?: string;
  outcome?: string;
  message?: string;
  error_code?: string;
  http_status?: number;
  account_id?: string | number;
  target_post_id?: string;
  request_id?: string;
  before_state_json?: Record<string, unknown> | string;
  after_state_json?: Record<string, unknown> | string;
  metadata_json?: Record<string, unknown> | string;
  created_at?: string | number;
}

export interface XTopicQuery {
  keyword?: string;
  region?: string;
  risk_level?: string;
  limit?: number;
  offset?: number;
}

export interface XPostQuery {
  topic_id?: string | number;
  keyword?: string;
  conversation_id?: string;
  risk_level?: string;
  limit?: number;
  offset?: number;
}

export interface XReviewQuery {
  status?: string;
  risk_level?: string;
  limit?: number;
  offset?: number;
}

export const getXTopics = (params?: XTopicQuery): Promise<XListResponse<XTopic>> =>
  request.get('/x/topics', { params });

export const refreshXTopics = (data?: { region_ids?: Array<string | number> }): Promise<{ success: boolean; message?: string; job_id?: string }> =>
  request.post('/x/topics/refresh', data || {}, X_BROWSER_REQUEST);

export const collectXTopicPosts = (
  topicId: string | number,
  data?: { max_posts?: number; language?: string },
): Promise<{ success: boolean; message?: string; items?: XPost[]; total?: number }> =>
  request.post(`/x/topics/${topicId}/collect-posts`, data || { max_posts: 50 }, X_BROWSER_REQUEST);

export const getXPosts = (params?: XPostQuery): Promise<XListResponse<XPost>> =>
  request.get('/x/posts', { params });

export const getXPost = (postId: string | number): Promise<{ post: XPost; conversation?: XConversationMeta }> =>
  request.get(`/x/posts/${postId}`);

export const collectXThread = (postId: string | number): Promise<XConversation & { success: boolean; message?: string }> =>
  request.post(`/x/posts/${postId}/collect-thread`, { max_posts: 50 }, X_BROWSER_REQUEST);

export const getXConversation = (rootPostId: string): Promise<XConversation> =>
  request.get(`/x/conversations/${rootPostId}`);

export const analyzeXConversation = (rootPostId: string): Promise<{ success?: boolean; message?: string; job_id?: string; analysis?: XThreadAnalysis } | XThreadAnalysis> =>
  request.post(`/x/conversations/${rootPostId}/analyze`, { max_samples: 25 }, X_MODEL_REQUEST);

export const generateXReplyCandidates = (
  postId: string | number,
  data: { account_id: string | number; tone?: string; candidate_count?: number },
): Promise<{
  success?: boolean;
  message?: string;
  account?: XAccount;
  post?: XPost;
  items?: Array<{ candidate?: XReplyCandidate; review?: XReviewTask }>;
  total?: number;
  recommended_index?: number;
  reason?: string;
  fallback_used?: boolean;
}> =>
  request.post(`/x/posts/${postId}/reply-candidates`, data, X_MODEL_REQUEST);

export interface XPreparedComment {
  success: boolean;
  reused?: boolean;
  already_published?: boolean;
  candidate: XReplyCandidate;
  review: XReviewTask;
  content_hash: string;
  x_post_id?: string;
  x_post_url?: string;
  account?: XAccount;
  identity?: { id?: string; username?: string; name?: string; source?: string };
  browser?: XBrowserStatus;
}

export const prepareXPostComment = (
  postId: string | number,
  data: { text: string; explicit_confirmation: true },
): Promise<XPreparedComment> =>
  request.post(`/x/posts/${postId}/comments/prepare`, data, X_WRITE_REQUEST);

export const getXReviews = (params?: XReviewQuery): Promise<XListResponse<XReviewTask>> =>
  request.get('/x/reviews', { params });

export const getXReview = (reviewId: string | number): Promise<XReviewTask> =>
  request.get(`/x/reviews/${reviewId}`);

export const regenerateXReview = (
  reviewId: string | number,
  data?: { tone?: string },
): Promise<{ success: boolean; message?: string; candidates?: XReplyCandidate[] }> =>
  request.post(`/x/reviews/${reviewId}/regenerate`, data || {}, X_MODEL_REQUEST);

export const approveXReview = (
  reviewId: string | number,
  data: {
    candidate_id: string | number;
    final_text: string;
    content_hash: string;
    explicit_confirmation: true;
  },
): Promise<{ success: boolean; message?: string; status?: string }> =>
  request.post(`/x/reviews/${reviewId}/approve`, data);

export const rejectXReview = (
  reviewId: string | number,
  data: { reason: string },
): Promise<{ success: boolean; message?: string; status?: string }> =>
  request.post(`/x/reviews/${reviewId}/reject`, data);

export const flagXReview = (
  reviewId: string | number,
  data: { action: 'fact_check' | 'block'; reason: string },
): Promise<{ success: boolean; message?: string; review?: XReviewTask }> =>
  request.post(`/x/reviews/${reviewId}/flag`, data);

export const publishXReview = (
  reviewId: string | number,
  data: {
    candidate_id: string | number;
    content_hash: string;
    explicit_confirmation: true;
    publish_mode: 'manual_review';
  },
): Promise<{ success: boolean; message?: string; status?: string; x_post_id?: string }> =>
  request.post(`/x/reviews/${reviewId}/publish`, data, X_WRITE_REQUEST);

export const sendXPostComment = async (
  postId: string | number,
  data: { text: string; explicit_confirmation: true },
): Promise<{
  success: boolean;
  message?: string;
  x_post_id?: string;
  x_post_url?: string;
  prepared: XPreparedComment;
}> => {
  const prepared = await prepareXPostComment(postId, data);
  if (prepared.already_published) {
    return {
      success: true,
      message: '该评论已发布',
      x_post_id: prepared.x_post_id,
      x_post_url: prepared.x_post_url,
      prepared,
    };
  }
  if (prepared.review.id == null || prepared.candidate.id == null) {
    throw new Error('评论审核记录创建失败');
  }
  const published = await publishXReview(prepared.review.id, {
    candidate_id: prepared.candidate.id,
    content_hash: prepared.content_hash,
    explicit_confirmation: true,
    publish_mode: 'manual_review',
  });
  return {
    ...published,
    x_post_url: published.x_post_id
      ? `https://x.com/i/web/status/${published.x_post_id}`
      : undefined,
    prepared,
  };
};

export const getXAutomationStatus = (): Promise<XAutomationStatus> =>
  request.get('/x/automation/status');

export const getXBrowserStatus = (): Promise<XBrowserStatus> =>
  request.get('/x/browser/status');

export const syncXBrowserAccount = (): Promise<{
  success: boolean;
  message?: string;
  identity?: { id?: string; username?: string; name?: string; source?: string };
  account?: XAccount;
  browser?: XBrowserStatus;
}> =>
  request.post('/x/browser/sync-account', {}, X_BROWSER_REQUEST);

export const openXBrowserLogin = (): Promise<{
  success: boolean;
  message?: string;
  browser?: { pid?: number; profile_dir?: string; browser_name?: string; url?: string };
}> =>
  request.post('/x/browser/open-login', {}, { skipRetry: true });

export const updateXAutomationControls = (
  data: Partial<XAutomationStatus>,
): Promise<{ success: boolean; message?: string; controls?: XAutomationStatus } | XAutomationStatus> =>
  request.patch('/x/automation/controls', data);

export const getXAccounts = (): Promise<XListResponse<XAccount>> =>
  request.get('/x/accounts');

export const startXOAuth = (): Promise<{ authorization_url?: string; url?: string }> =>
  request.post('/x/accounts/oauth/start', {});

export const testXAccount = (accountId: string | number): Promise<{ success: boolean; message?: string }> =>
  request.post(`/x/accounts/${accountId}/test`, {}, X_BROWSER_REQUEST);

export const updateXAccount = (
  accountId: string | number,
  data: Partial<XAccount>,
): Promise<{ success: boolean; message?: string; account?: XAccount } | XAccount> =>
  request.patch(`/x/accounts/${accountId}`, data);

export const saveXAccountApprovalEvidence = (
  accountId: string | number,
  data: { approval_reference: string; x_written_approval: boolean },
): Promise<{ success: boolean; message?: string; account?: XAccount }> =>
  request.post(`/x/accounts/${accountId}/approval-evidence`, data);

export const getXUsage = (): Promise<XUsageSummary> =>
  request.get('/x/usage');

export const getXAuditLogs = (params?: { limit?: number; offset?: number }): Promise<XListResponse<XAuditLog>> =>
  request.get('/x/audit-logs', { params });

export const refreshXInteractions = (data: {
  account_id?: string | number;
  since_id?: string;
  max_posts?: number;
}): Promise<{
  success: boolean;
  message?: string;
  items?: Array<{
    interaction?: XInteraction;
    post?: XPost;
    eligibility?: Record<string, unknown>;
  }>;
  total?: number;
  next_since_id?: string;
  auto_publish_created?: false;
}> =>
  request.post('/x/interactions/refresh', data, X_BROWSER_REQUEST);

export const getXInteractions = (params?: {
  status?: string;
  account_id?: string | number;
  limit?: number;
  offset?: number;
}): Promise<XListResponse<XInteraction>> =>
  request.get('/x/interactions', { params });

export const evaluateXInteraction = (
  interactionId: string | number,
): Promise<{
  success: boolean;
  interaction?: XInteraction;
  eligibility?: Record<string, unknown>;
  opt_out?: Record<string, unknown>;
  intent?: Record<string, unknown>;
}> =>
  request.post(`/x/interactions/${interactionId}/evaluate`, { account_post_ids: [] });

export const optOutXUser = (
  xUserId: string,
  data: {
    account_id: string | number;
    username_snapshot?: string;
    source_interaction_id?: string | number;
    source_post_id?: string;
    detected_phrase: string;
    evidence?: Record<string, unknown>;
  },
): Promise<{ success: boolean; message?: string }> =>
  request.post(`/x/users/${encodeURIComponent(xUserId)}/opt-out`, data);

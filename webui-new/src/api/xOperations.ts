import request from './request';

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

export interface XConversation {
  root_post?: XPost;
  posts?: XPost[];
  replies?: XPost[];
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
}

export interface XAutomationStatus {
  read_enabled: boolean;
  write_enabled: boolean;
  auto_reply_enabled: boolean;
  global_kill_switch: boolean;
  require_human_review: boolean;
  effective_write_allowed?: boolean;
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
  request.post('/x/topics/refresh', data || {});

export const collectXTopicPosts = (
  topicId: string | number,
  data?: { max_posts?: number; language?: string },
): Promise<{ success: boolean; message?: string; items?: XPost[]; total?: number }> =>
  request.post(`/x/topics/${topicId}/collect-posts`, data || { max_posts: 50 });

export const getXPosts = (params?: XPostQuery): Promise<XListResponse<XPost>> =>
  request.get('/x/posts', { params });

export const getXPost = (postId: string | number): Promise<XPost> =>
  request.get(`/x/posts/${postId}`);

export const collectXThread = (postId: string | number): Promise<{ success: boolean; message?: string; job_id?: string }> =>
  request.post(`/x/posts/${postId}/collect-thread`, { max_posts: 50 });

export const getXConversation = (rootPostId: string): Promise<XConversation> =>
  request.get(`/x/conversations/${rootPostId}`);

export const analyzeXConversation = (rootPostId: string): Promise<{ success?: boolean; message?: string; job_id?: string; analysis?: XThreadAnalysis } | XThreadAnalysis> =>
  request.post(`/x/conversations/${rootPostId}/analyze`, { max_samples: 25 });

export const generateXReplyCandidates = (
  postId: string | number,
  data: { account_id: string | number; tone?: string; candidate_count?: number },
): Promise<{ success?: boolean; message?: string; review_id?: string | number; candidates?: XReplyCandidate[] }> =>
  request.post(`/x/posts/${postId}/reply-candidates`, data);

export const getXReviews = (params?: XReviewQuery): Promise<XListResponse<XReviewTask>> =>
  request.get('/x/reviews', { params });

export const getXReview = (reviewId: string | number): Promise<XReviewTask> =>
  request.get(`/x/reviews/${reviewId}`);

export const regenerateXReview = (
  reviewId: string | number,
  data?: { tone?: string },
): Promise<{ success: boolean; message?: string; candidates?: XReplyCandidate[] }> =>
  request.post(`/x/reviews/${reviewId}/regenerate`, data || {});

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

export const publishXReview = (
  reviewId: string | number,
  data: {
    candidate_id: string | number;
    content_hash: string;
    explicit_confirmation: true;
    publish_mode: 'manual_review';
  },
): Promise<{ success: boolean; message?: string; status?: string; x_post_id?: string }> =>
  request.post(`/x/reviews/${reviewId}/publish`, data);

export const getXAutomationStatus = (): Promise<XAutomationStatus> =>
  request.get('/x/automation/status');

export const updateXAutomationControls = (
  data: Partial<XAutomationStatus>,
): Promise<{ success: boolean; message?: string; status?: XAutomationStatus } | XAutomationStatus> =>
  request.patch('/x/automation/controls', data);

export const getXAccounts = (): Promise<XListResponse<XAccount>> =>
  request.get('/x/accounts');

export const startXOAuth = (): Promise<{ authorization_url?: string; url?: string }> =>
  request.post('/x/accounts/oauth/start', {});

export const testXAccount = (accountId: string | number): Promise<{ success: boolean; message?: string }> =>
  request.post(`/x/accounts/${accountId}/test`);

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

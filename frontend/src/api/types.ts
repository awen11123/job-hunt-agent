export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface Application {
  id: string;
  company: string;
  role: string;
  applied_date: string | null;
  location: string | null;
  status: string;
  next_step: string | null;
  next_time: string | null;
  job_url: string | null;
  notes: string | null;
}

export interface LocalConfig {
  excel_path: string | null;
  backup_dir: string;
  interview_dir: string;
  notion_enabled: boolean;
  model_enabled: boolean;
}

export type ProviderName =
  | "deepseek"
  | "qwen"
  | "moonshot"
  | "openai-compatible"
  | "ollama";

export interface ModelSettings {
  enabled: boolean;
  provider: ProviderName;
  base_url: string;
  model: string;
  credential_configured: boolean;
  requires_api_key: boolean;
}

export interface NotionSettings {
  enabled: boolean;
  credential_configured: boolean;
  database_configured: boolean;
}

export interface IntegrationSettings {
  model: ModelSettings;
  notion: NotionSettings;
}

export interface ModelSettingsInput {
  enabled: boolean;
  provider: ProviderName;
  base_url?: string;
  model?: string;
  api_key?: string;
}

export interface NotionSettingsInput {
  enabled: boolean;
  token?: string;
  interviews_database_id?: string;
}

export interface ModelConnectionResult {
  status: "connected";
  structured_output: boolean;
}

export interface NotionConnectionResult {
  status: "connected";
}

export type InterviewSyncStatus = "local" | "pending" | "synced" | "failed";

export interface Interview {
  id: string;
  application_id: string;
  company: string;
  round_name: string;
  raw_notes: string;
  scheduled_at: string | null;
  format: string | null;
  result: string | null;
  self_score: number | null;
  markdown_path: string;
  sync_status: InterviewSyncStatus;
  notion_page_id: string | null;
  operation_id: string;
  created_at: string;
  updated_at: string;
}

export type ActionName =
  | "create_application"
  | "update_application"
  | "save_interview";

export type ActionStatus = "pending" | "confirmed" | "cancelled" | "expired";
export type DisclosureCategory = "application_metadata" | "interview_notes";

export interface ActionDraft {
  id: string;
  action: ActionName;
  payload: Record<string, JsonValue>;
  before: Record<string, JsonValue> | null;
  status: ActionStatus;
  confirmation_token: string;
  operation_id: string;
  expires_at: string;
  disclosure: DisclosureCategory[];
}

export interface AssistantMessage {
  kind: "message";
  message: string;
}

export type ActionProposal = ActionDraft | AssistantMessage;

export interface ActionReceipt {
  status: "created" | "updated" | "unchanged" | "failed";
  record_id: string | null;
  message: string;
}

export interface ActionExecution {
  draft: ActionDraft;
  receipt: ActionReceipt;
  executed_at: string;
}

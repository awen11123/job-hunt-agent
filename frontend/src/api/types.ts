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

export interface ActionDraft {
  id: string;
  action: ActionName;
  payload: Record<string, JsonValue>;
  before: Record<string, JsonValue> | null;
  status: ActionStatus;
  confirmation_token: string;
  operation_id: string;
  expires_at: string;
}

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

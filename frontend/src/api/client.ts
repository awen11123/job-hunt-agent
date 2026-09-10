import type {
  ActionDraft,
  ActionExecution,
  Application,
  Interview,
  LocalConfig,
} from "./types";

export interface JobHuntApi {
  listApplications(): Promise<Application[]>;
  listInterviews(applicationId?: string): Promise<Interview[]>;
  getConfig(): Promise<LocalConfig>;
  saveConfig(config: LocalConfig): Promise<LocalConfig>;
  proposeAction(text: string): Promise<ActionDraft>;
  modifyAction(id: string, payload: ActionDraft["payload"]): Promise<ActionDraft>;
  confirmAction(id: string, token: string): Promise<ActionExecution>;
  cancelAction(id: string): Promise<ActionDraft>;
}

interface ErrorDetail {
  code?: unknown;
  message?: unknown;
}

interface ErrorEnvelope {
  detail?: ErrorDetail | string;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let envelope: ErrorEnvelope | null = null;
  try {
    envelope = (await response.json()) as ErrorEnvelope;
  } catch {
    // Non-JSON errors receive the same stable, non-sensitive fallback.
  }

  const detail = envelope?.detail;
  if (detail && typeof detail === "object") {
    const code = typeof detail.code === "string" ? detail.code : "request_failed";
    const message =
      typeof detail.message === "string"
        ? detail.message
        : `请求失败（HTTP ${response.status}）。`;
    return new ApiError(code, response.status, message);
  }

  if (typeof detail === "string") {
    return new ApiError("request_failed", response.status, detail);
  }

  return new ApiError(
    "request_failed",
    response.status,
    `请求失败（HTTP ${response.status}）。`,
  );
}

export class HttpJobHuntApi implements JobHuntApi {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;
  private readonly sessionToken: string;

  constructor(
    sessionToken: string,
    baseUrl = "/api",
    fetcher: typeof fetch = globalThis.fetch,
  ) {
    this.sessionToken = sessionToken;
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetcher = fetcher;
  }

  listApplications(): Promise<Application[]> {
    return this.request<Application[]>("/applications");
  }

  listInterviews(applicationId?: string): Promise<Interview[]> {
    const query = applicationId
      ? `?application_id=${encodeURIComponent(applicationId)}`
      : "";
    return this.request<Interview[]>(`/interviews${query}`);
  }

  getConfig(): Promise<LocalConfig> {
    return this.request<LocalConfig>("/config");
  }

  saveConfig(config: LocalConfig): Promise<LocalConfig> {
    return this.request<LocalConfig>("/config", {
      method: "PUT",
      headers: { "X-Job-Hunt-Session": this.sessionToken },
      body: JSON.stringify(config),
    });
  }

  proposeAction(text: string): Promise<ActionDraft> {
    return this.request<ActionDraft>("/actions/propose", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  }

  modifyAction(id: string, payload: ActionDraft["payload"]): Promise<ActionDraft> {
    return this.request<ActionDraft>(`/actions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "X-Job-Hunt-Session": this.sessionToken },
      body: JSON.stringify({ payload }),
    });
  }

  confirmAction(id: string, token: string): Promise<ActionExecution> {
    return this.request<ActionExecution>(
      `/actions/${encodeURIComponent(id)}/confirm`,
      {
        method: "POST",
        headers: { "X-Job-Hunt-Session": this.sessionToken },
        body: JSON.stringify({ confirmation_token: token }),
      },
    );
  }

  cancelAction(id: string): Promise<ActionDraft> {
    return this.request<ActionDraft>(
      `/actions/${encodeURIComponent(id)}/cancel`,
      {
        method: "POST",
        headers: { "X-Job-Hunt-Session": this.sessionToken },
      },
    );
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }

    const fetcher = this.fetcher;
    const response = await fetcher(`${this.baseUrl}${path}`, {
      ...init,
      headers,
    });
    if (!response.ok) {
      throw await parseError(response);
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError(
        "invalid_response",
        response.status,
        "服务返回了无法识别的数据。",
      );
    }
  }
}

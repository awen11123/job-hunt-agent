import { describe, expect, it } from "vitest";

import { ApiError, HttpJobHuntApi } from "./client";

interface RecordedRequest {
  url: string;
  init: RequestInit;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("HttpJobHuntApi", () => {
  it("sends the injected session token on every mutation except propose", async () => {
    const requests: RecordedRequest[] = [];
    const fetcher: typeof fetch = async (input, init = {}) => {
      requests.push({ url: String(input), init });
      return jsonResponse({});
    };
    const api = new HttpJobHuntApi("private-session", "/api/", fetcher);

    await api.listApplications();
    await api.proposeAction("今天投了示例公司");
    await api.modifyAction("draft/1", { company: "新公司", role: "Agent 工程师" });
    await api.confirmAction("draft/1", "confirm-token");
    await api.cancelAction("draft/1");
    await api.saveConfig({
      excel_path: "C:/tracker.xlsx",
      backup_dir: "C:/backups",
      interview_dir: "C:/interviews",
      notion_enabled: false,
      model_enabled: false,
    });

    expect(requests.map(({ url }) => url)).toEqual([
      "/api/applications",
      "/api/actions/propose",
      "/api/actions/draft%2F1",
      "/api/actions/draft%2F1/confirm",
      "/api/actions/draft%2F1/cancel",
      "/api/config",
    ]);
    expect(new Headers(requests[0].init.headers).has("X-Job-Hunt-Session")).toBe(false);
    expect(new Headers(requests[1].init.headers).has("X-Job-Hunt-Session")).toBe(false);
    for (const request of requests.slice(2)) {
      expect(new Headers(request.init.headers).get("X-Job-Hunt-Session")).toBe(
        "private-session",
      );
    }
    expect(requests[2].init.method).toBe("PATCH");
    expect(requests[5].init.method).toBe("PUT");
  });

  it("preserves a structured API error code and message", async () => {
    const fetcher: typeof fetch = async () =>
      jsonResponse(
        { detail: { code: "excel_unavailable", message: "请关闭 WPS 后重试。" } },
        409,
      );
    const api = new HttpJobHuntApi("session", "/api", fetcher);

    await expect(api.listApplications()).rejects.toEqual(
      expect.objectContaining({
        name: "ApiError",
        code: "excel_unavailable",
        status: 409,
        message: "请关闭 WPS 后重试。",
      }),
    );
  });

  it("uses a stable fallback without exposing a non-JSON response", async () => {
    const fetcher: typeof fetch = async () =>
      new Response("private traceback and file path", { status: 500 });
    const api = new HttpJobHuntApi("session", "/api", fetcher);

    await expect(api.getConfig()).rejects.toEqual(
      new ApiError("request_failed", 500, "请求失败（HTTP 500）。"),
    );
  });

  it("encodes the optional interview application filter", async () => {
    let requestedUrl = "";
    const fetcher: typeof fetch = async (input) => {
      requestedUrl = String(input);
      return jsonResponse([]);
    };
    const api = new HttpJobHuntApi("session", "/api", fetcher);

    await api.listInterviews("app/示例");

    expect(requestedUrl).toBe("/api/interviews?application_id=app%2F%E7%A4%BA%E4%BE%8B");
  });
});

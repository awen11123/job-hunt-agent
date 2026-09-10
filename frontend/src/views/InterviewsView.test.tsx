import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { JobHuntApi } from "../api/client";
import type { Interview } from "../api/types";
import { InterviewsView } from "./InterviewsView";

const failedInterview: Interview = {
  id: "interview-1",
  application_id: "application-1",
  company: "示例科技",
  round_name: "技术一面",
  raw_notes: "重点讨论了 Agent 记忆和评测。",
  scheduled_at: "2026-09-11T10:00:00+08:00",
  format: "远程",
  result: "待反馈",
  self_score: 7,
  markdown_path: "C:/interviews/example.md",
  sync_status: "failed",
  notion_page_id: null,
  operation_id: "operation-1",
  created_at: "2026-09-11T12:00:00+08:00",
  updated_at: "2026-09-11T12:00:00+08:00",
};

function api(syncInterview: ReturnType<typeof vi.fn>): JobHuntApi {
  return {
    listApplications: vi.fn().mockResolvedValue([]),
    listInterviews: vi.fn().mockResolvedValue([failedInterview]),
    getConfig: vi.fn(),
    saveConfig: vi.fn(),
    proposeAction: vi.fn(),
    modifyAction: vi.fn(),
    confirmAction: vi.fn(),
    cancelAction: vi.fn(),
    getSettings: vi.fn(),
    saveModelSettings: vi.fn(),
    testModelSettings: vi.fn(),
    saveNotionSettings: vi.fn(),
    testNotionSettings: vi.fn(),
    syncInterview,
  } as unknown as JobHuntApi;
}

describe("InterviewsView Notion sync", () => {
  it("retries a failed sync and updates the row in place", async () => {
    const synced = {
      ...failedInterview,
      sync_status: "synced" as const,
      notion_page_id: "notion-page",
    };
    const syncInterview = vi.fn().mockResolvedValue(synced);
    const user = userEvent.setup();
    render(<InterviewsView api={api(syncInterview)} />);

    expect(await screen.findByText("同步失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试同步 示例科技" }));

    expect(syncInterview).toHaveBeenCalledWith("interview-1");
    expect(await screen.findByText("已同步")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /同步 示例科技/ })).not.toBeInTheDocument();
  });

  it("keeps the failed state and shows a retry-safe error", async () => {
    const syncInterview = vi.fn().mockRejectedValue(new Error("private upstream detail"));
    const user = userEvent.setup();
    render(<InterviewsView api={api(syncInterview)} />);

    await user.click(await screen.findByRole("button", { name: "重试同步 示例科技" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("同步失败，请稍后重试");
    expect(document.body).not.toHaveTextContent("private upstream detail");
    expect(screen.getByRole("button", { name: "重试同步 示例科技" })).toBeEnabled();
  });
});

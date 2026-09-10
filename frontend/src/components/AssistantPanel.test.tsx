import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type JobHuntApi } from "../api/client";
import type { ActionDraft, ActionExecution } from "../api/types";
import { AssistantPanel } from "./AssistantPanel";

const draft: ActionDraft = {
  id: "draft-1",
  action: "create_application",
  payload: {
    company: "示例科技",
    role: "Agent 工程师",
    applied_date: "2026-09-10",
    location: "杭州",
    status: "已投递",
    next_step: null,
    next_time: null,
    job_url: null,
    notes: null,
  },
  before: null,
  status: "pending",
  confirmation_token: "token-1",
  operation_id: "operation-1",
  expires_at: "2026-09-10T12:00:00+08:00",
};

function api(overrides: Partial<JobHuntApi> = {}): JobHuntApi {
  return {
    listApplications: vi.fn().mockResolvedValue([]),
    listInterviews: vi.fn().mockResolvedValue([]),
    getConfig: vi.fn(),
    saveConfig: vi.fn(),
    proposeAction: vi.fn().mockResolvedValue(draft),
    modifyAction: vi.fn().mockResolvedValue(draft),
    confirmAction: vi.fn(),
    cancelAction: vi.fn().mockResolvedValue({ ...draft, status: "cancelled" }),
    ...overrides,
  };
}

async function propose(user: ReturnType<typeof userEvent.setup>) {
  await user.type(
    screen.getByRole("textbox", { name: "输入投递操作" }),
    "今天投了示例科技的 Agent 工程师",
  );
  await user.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText("变更预览");
}

describe("AssistantPanel", () => {
  it("never confirms a write directly from a chat message", async () => {
    const jobApi = api();
    const user = userEvent.setup();
    render(<AssistantPanel api={jobApi} />);

    await propose(user);

    expect(jobApi.proposeAction).toHaveBeenCalledTimes(1);
    expect(jobApi.confirmAction).not.toHaveBeenCalled();
  });

  it("edits the preview, uses the rotated token, and confirms explicitly", async () => {
    const modified = {
      ...draft,
      payload: { ...draft.payload, company: "修改后科技" },
      confirmation_token: "token-2",
    };
    const execution: ActionExecution = {
      draft: { ...modified, status: "confirmed" },
      receipt: { status: "created", record_id: "app-2", message: "created" },
      executed_at: "2026-09-10T11:00:00+08:00",
    };
    const modifyAction = vi.fn().mockResolvedValue(modified);
    const confirmAction = vi.fn().mockResolvedValue(execution);
    const onApplicationsChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <AssistantPanel
        api={api({ modifyAction, confirmAction })}
        onApplicationsChanged={onApplicationsChanged}
      />,
    );
    await propose(user);

    const company = screen.getByRole("textbox", { name: "企业" });
    await user.clear(company);
    await user.type(company, "修改后科技");
    await user.click(screen.getByRole("button", { name: "保存修改" }));
    await user.click(screen.getByRole("button", { name: "确认写入" }));

    expect(modifyAction).toHaveBeenCalledWith(
      "draft-1",
      expect.objectContaining({ company: "修改后科技" }),
    );
    expect(confirmAction).toHaveBeenCalledWith("draft-1", "token-2");
    expect(onApplicationsChanged).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("已写入投递记录")).toBeInTheDocument();
  });

  it("cancels a pending preview without confirming it", async () => {
    const cancelAction = vi.fn().mockResolvedValue({ ...draft, status: "cancelled" });
    const jobApi = api({ cancelAction });
    const user = userEvent.setup();
    render(<AssistantPanel api={jobApi} />);
    await propose(user);

    await user.click(screen.getByRole("button", { name: "取消变更" }));

    expect(cancelAction).toHaveBeenCalledWith("draft-1");
    expect(jobApi.confirmAction).not.toHaveBeenCalled();
    expect(screen.queryByText("变更预览")).not.toBeInTheDocument();
  });

  it("keeps the preview when Excel is locked", async () => {
    const confirmAction = vi
      .fn()
      .mockRejectedValue(
        new ApiError("create_application_failed", 409, "请关闭 WPS 后重试。"),
      );
    const user = userEvent.setup();
    render(<AssistantPanel api={api({ confirmAction })} />);
    await propose(user);

    await user.click(screen.getByRole("button", { name: "确认写入" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("请关闭 WPS 后重试");
    expect(screen.getByText("变更预览")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认写入" })).toBeEnabled();
  });
});

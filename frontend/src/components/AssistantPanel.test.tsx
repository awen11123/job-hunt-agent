import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, type JobHuntApi } from "../api/client";
import type { ActionDraft, ActionExecution } from "../api/types";
import { ActionPreview } from "./ActionPreview";
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
  afterEach(() => vi.useRealTimers());

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

  it("answers a weekly count question locally without proposing a write", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 8, 9, 12));
    const today = new Date();
    const localDate = (value: Date) => {
      const year = value.getFullYear();
      const month = String(value.getMonth() + 1).padStart(2, "0");
      const day = String(value.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    };
    const monday = new Date(2026, 8, 7, 12);
    const sunday = new Date(2026, 8, 6, 12);
    const listApplications = vi.fn().mockResolvedValue([
      { id: "1", company: "同一公司", role: "Agent", applied_date: localDate(today) },
      { id: "2", company: "同一公司", role: "LLM", applied_date: localDate(monday) },
      { id: "3", company: "上周公司", role: "平台", applied_date: localDate(sunday) },
    ]);
    const jobApi = api({ listApplications });
    const user = userEvent.setup();
    render(<AssistantPanel api={jobApi} />);

    await user.type(screen.getByRole("textbox", { name: "输入投递操作" }), "本周投了多少家？");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText(/本周共投递 2 个岗位，涉及 1 家公司/)).toBeInTheDocument();
    expect(jobApi.proposeAction).not.toHaveBeenCalled();
    expect(listApplications).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("变更预览")).not.toBeInTheDocument();
  });

  it.each([
    "投递腾讯 Agent",
    "准备投腾讯",
    "投递腾讯 Agent https://example.com/job?id=123",
  ])("routes a supported write to the backend preview: %s", async (text) => {
    const jobApi = api();
    const user = userEvent.setup();
    render(<AssistantPanel api={jobApi} />);

    await user.type(screen.getByRole("textbox", { name: "输入投递操作" }), text);
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("变更预览")).toBeInTheDocument();
    expect(jobApi.proposeAction).toHaveBeenCalledWith(text);
    expect(jobApi.confirmAction).not.toHaveBeenCalled();
  });

  it("answers pending-interview and recent-interview questions from local data", async () => {
    const listApplications = vi.fn().mockResolvedValue([
      {
        id: "1",
        company: "候选科技",
        role: "Agent 工程师",
        applied_date: null,
        location: "杭州",
        status: "已投递",
        next_step: "技术一面",
        next_time: null,
        job_url: null,
        notes: null,
      },
    ]);
    const listInterviews = vi.fn().mockResolvedValue([
      {
        id: "i-1",
        company: "面试科技",
        round_name: "技术二面",
        result: "待反馈",
        created_at: "2026-09-10T10:00:00+08:00",
      },
    ]);
    const jobApi = api({ listApplications, listInterviews });
    const user = userEvent.setup();
    render(<AssistantPanel api={jobApi} />);

    const input = screen.getByRole("textbox", { name: "输入投递操作" });
    await user.type(input, "有哪些待面试岗位？");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText(/候选科技 · Agent 工程师/)).toBeInTheDocument();

    await user.type(input, "最近面经是什么？");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText(/面试科技 · 技术二面 · 待反馈/)).toBeInTheDocument();
    expect(jobApi.proposeAction).not.toHaveBeenCalled();
  });

  it("returns a normal local-mode response for an unsupported read question", async () => {
    const jobApi = api();
    const user = userEvent.setup();
    render(<AssistantPanel api={jobApi} />);

    await user.type(
      screen.getByRole("textbox", { name: "输入投递操作" }),
      "我应该怎么准备系统设计？",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText(/当前无模型模式暂不支持这个查询/)).toBeInTheDocument();
    expect(jobApi.proposeAction).not.toHaveBeenCalled();
  });
});

describe("ActionPreview", () => {
  it("edits a nested application patch and shows its previous values", async () => {
    const onModify = vi.fn().mockResolvedValue(undefined);
    const updateDraft: ActionDraft = {
      ...draft,
      action: "update_application",
      payload: { application_id: "app-1", patch: { status: "已投递" } },
      before: { status: "待投递" },
    };
    const user = userEvent.setup();
    render(
      <ActionPreview
        draft={updateDraft}
        onModify={onModify}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.getByText("Excel 投递表")).toBeInTheDocument();
    expect(screen.getByText("远程发送：无")).toBeInTheDocument();
    expect(screen.getByLabelText("投递记录 ID")).toHaveValue("app-1");
    expect(screen.getByLabelText("投递记录 ID")).toHaveAttribute("readonly");
    expect(screen.getByRole("region", { name: "变更前" })).toHaveTextContent("待投递");
    const status = screen.getByRole("textbox", { name: "状态" });
    await user.clear(status);
    await user.type(status, "技术一面");
    await user.click(screen.getByRole("button", { name: "保存修改" }));

    expect(onModify).toHaveBeenCalledWith({
      application_id: "app-1",
      patch: { status: "技术一面" },
    });
  });

  it("edits interview notes and keeps self score numeric", async () => {
    const onModify = vi.fn().mockResolvedValue(undefined);
    const interviewDraft: ActionDraft = {
      ...draft,
      action: "save_interview",
      payload: {
        application_id: "app-1",
        company: "面试科技",
        round_name: "技术一面",
        raw_notes: "原始记录",
        scheduled_at: null,
        format: "远程",
        result: null,
        self_score: 7,
      },
    };
    const user = userEvent.setup();
    render(
      <ActionPreview
        draft={interviewDraft}
        onModify={onModify}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.getByText("本地 Markdown")).toBeInTheDocument();
    expect(screen.getByText("远程发送：无")).toBeInTheDocument();
    const notes = screen.getByRole("textbox", { name: "面试正文" });
    await user.clear(notes);
    await user.type(notes, "补充后的面试记录");
    const score = screen.getByRole("spinbutton", { name: "自评" });
    await user.clear(score);
    await user.type(score, "8");
    await user.click(screen.getByRole("button", { name: "保存修改" }));

    expect(onModify).toHaveBeenCalledWith(
      expect.objectContaining({ raw_notes: "补充后的面试记录", self_score: 8 }),
    );
  });
});

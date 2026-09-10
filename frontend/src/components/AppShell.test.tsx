import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { JobHuntApi } from "../api/client";
import type { Application, Interview, LocalConfig } from "../api/types";
import { AppShell } from "./AppShell";

const applications: Application[] = [
  {
    id: "app-1",
    company: "进行科技",
    role: "Agent 工程师",
    applied_date: "2026-09-09",
    location: "杭州",
    status: "AI 面试",
    next_step: "等待结果",
    next_time: null,
    job_url: "https://example.com/active",
    notes: "完成 AI 面",
  },
  {
    id: "app-2",
    company: "结束科技",
    role: "算法工程师",
    applied_date: "2026-09-08",
    location: "上海",
    status: "简历未通过",
    next_step: null,
    next_time: null,
    job_url: null,
    notes: null,
  },
  {
    id: "app-3",
    company: "待筛科技",
    role: "LLM 应用开发",
    applied_date: "2026-09-10",
    location: "深圳",
    status: "已投递",
    next_step: "等待筛选",
    next_time: null,
    job_url: null,
    notes: null,
  },
];

const interviews: Interview[] = [
  {
    id: "interview-1",
    application_id: "app-1",
    company: "进行科技",
    round_name: "技术一面",
    raw_notes:
      "重点追问了 LangGraph 状态流转和异常恢复，并继续讨论了上下文治理、接口超时与幂等处理。随后讨论了评测体系和线上反馈闭环。",
    scheduled_at: "2026-09-09T10:00:00+08:00",
    format: "远程",
    result: "待后续沟通",
    self_score: 7,
    markdown_path: "C:/interviews/example.md",
    sync_status: "local",
    notion_page_id: null,
    operation_id: "op-1",
    created_at: "2026-09-09T12:00:00+08:00",
    updated_at: "2026-09-09T12:00:00+08:00",
  },
];

const config: LocalConfig = {
  excel_path: "C:/tracker.xlsx",
  backup_dir: "C:/backups",
  interview_dir: "C:/interviews",
  notion_enabled: false,
  model_enabled: false,
};

function api(overrides: Partial<JobHuntApi> = {}): JobHuntApi {
  return {
    listApplications: vi.fn().mockResolvedValue(applications),
    listInterviews: vi.fn().mockResolvedValue(interviews),
    getConfig: vi.fn().mockResolvedValue(config),
    saveConfig: vi.fn().mockResolvedValue(config),
    proposeAction: vi.fn().mockRejectedValue(new Error("not used")),
    modifyAction: vi.fn().mockRejectedValue(new Error("not used")),
    confirmAction: vi.fn().mockRejectedValue(new Error("not used")),
    cancelAction: vi.fn().mockRejectedValue(new Error("not used")),
    ...overrides,
  };
}

describe("AppShell", () => {
  beforeEach(() => vi.clearAllMocks());

  it("searches applications by company, role, and location", async () => {
    const user = userEvent.setup();
    render(<AppShell api={api()} />);
    const panel = screen.getByRole("tabpanel", { name: "投递看板" });
    expect(await within(panel).findByText("进行科技")).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "搜索投递" }), "深圳");

    expect(within(panel).getByText("待筛科技")).toBeInTheDocument();
    expect(within(panel).queryByText("进行科技")).not.toBeInTheDocument();
    expect(within(panel).queryByText("结束科技")).not.toBeInTheDocument();
  });

  it("filters statuses and separates closed processes without strike-through", async () => {
    const user = userEvent.setup();
    render(<AppShell api={api()} />);
    const panel = screen.getByRole("tabpanel", { name: "投递看板" });
    expect(await within(panel).findByText("进行科技")).toBeInTheDocument();

    const closedRegion = within(panel).getByRole("region", { name: "已结束流程" });
    expect(within(closedRegion).getByText("结束科技")).toBeInTheDocument();
    expect(within(closedRegion).getByText("结束科技")).not.toHaveStyle({
      textDecoration: "line-through",
    });

    await user.selectOptions(screen.getByRole("combobox", { name: "状态筛选" }), "已投递");
    expect(within(panel).getByText("待筛科技")).toBeInTheDocument();
    expect(within(panel).queryByText("进行科技")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("region", { name: "已结束流程" })).not.toBeInTheDocument();
  });

  it("shows honest summary values from loaded records", async () => {
    render(<AppShell api={api()} />);
    const summary = await screen.findByRole("region", { name: "投递概览" });

    expect(within(summary).getByLabelText("总投递 3")).toBeInTheDocument();
    expect(within(summary).getByLabelText("进行中 2")).toBeInTheDocument();
    expect(within(summary).getByLabelText("面试中 1")).toBeInTheDocument();
    expect(within(summary).getByLabelText("已结束 1")).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    const { rerender } = render(
      <AppShell api={api({ listApplications: vi.fn().mockResolvedValue([]) })} />,
    );
    expect(await screen.findByText("还没有投递记录")).toBeInTheDocument();

    rerender(
      <AppShell
        api={api({ listApplications: vi.fn().mockRejectedValue(new Error("offline")) })}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("投递数据加载失败");
  });

  it("renders interview details and expands the private local note", async () => {
    const user = userEvent.setup();
    render(<AppShell api={api()} />);
    await user.click(screen.getByRole("tab", { name: "面经" }));
    const panel = screen.getByRole("tabpanel", { name: "面经" });

    expect(await within(panel).findByText("进行科技")).toBeInTheDocument();
    expect(within(panel).getByText("仅本地")).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "展开面经" }));
    expect(within(panel).getByText(/随后讨论了评测体系/)).toBeInTheDocument();
  });

  it("saves settings through the API", async () => {
    const saveConfig = vi.fn().mockResolvedValue({ ...config, model_enabled: true });
    const user = userEvent.setup();
    render(<AppShell api={api({ saveConfig })} />);
    await user.click(screen.getByRole("tab", { name: "设置" }));

    const modelToggle = await screen.findByRole("checkbox", { name: "启用模型" });
    await user.click(modelToggle);
    await user.click(screen.getByRole("button", { name: "保存设置" }));

    expect(saveConfig).toHaveBeenCalledWith({ ...config, model_enabled: true });
    expect(await screen.findByText("设置已保存")).toBeInTheDocument();
  });
});

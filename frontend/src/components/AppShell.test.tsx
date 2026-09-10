import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { JobHuntApi } from "../api/client";
import type { Application, Interview, LocalConfig } from "../api/types";
import { AppShell } from "./AppShell";
import { StatusSummary } from "./StatusSummary";

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

const integrationSettings = {
  model: {
    enabled: false,
    provider: "deepseek" as const,
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
    credential_configured: false,
    requires_api_key: true,
  },
  notion: {
    enabled: false,
    credential_configured: false,
    database_configured: false,
  },
};

function api(overrides: Partial<JobHuntApi> = {}): JobHuntApi {
  return {
    listApplications: vi.fn().mockResolvedValue(applications),
    listInterviews: vi.fn().mockResolvedValue(interviews),
    getConfig: vi.fn().mockResolvedValue(config),
    saveConfig: vi.fn().mockResolvedValue(config),
    getSettings: vi.fn().mockResolvedValue(integrationSettings),
    saveModelSettings: vi.fn().mockResolvedValue(integrationSettings.model),
    testModelSettings: vi.fn().mockResolvedValue({ status: "connected", structured_output: true }),
    saveNotionSettings: vi.fn().mockResolvedValue(integrationSettings.notion),
    testNotionSettings: vi.fn().mockResolvedValue({ status: "connected" }),
    syncInterview: vi.fn().mockRejectedValue(new Error("not used")),
    proposeAction: vi.fn().mockRejectedValue(new Error("not used")),
    modifyAction: vi.fn().mockRejectedValue(new Error("not used")),
    confirmAction: vi.fn().mockRejectedValue(new Error("not used")),
    cancelAction: vi.fn().mockRejectedValue(new Error("not used")),
    ...overrides,
  };
}

describe("AppShell", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.useRealTimers());

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

  it("recognizes every closed status used by the real tracker", async () => {
    const closedApplications = ["遗憾", "简历挂", "未录用"].map((status, index) => ({
      ...applications[0],
      id: `closed-${index}`,
      company: `${status}公司`,
      status,
    }));
    render(
      <AppShell
        api={api({ listApplications: vi.fn().mockResolvedValue(closedApplications) })}
      />,
    );
    const panel = screen.getByRole("tabpanel", { name: "投递看板" });
    const closed = await within(panel).findByRole("region", { name: "已结束流程" });

    expect(within(closed).getByText("遗憾公司")).toBeInTheDocument();
    expect(within(closed).getByText("简历挂公司")).toBeInTheDocument();
    expect(within(closed).getByText("未录用公司")).toBeInTheDocument();
    expect(within(panel).queryByRole("region", { name: "进行中流程" })).not.toBeInTheDocument();
  });

  it("shows honest summary values from loaded records", async () => {
    render(<AppShell api={api()} />);
    const summary = await screen.findByRole("region", { name: "投递概览" });

    expect(within(summary).getByLabelText("总投递 3")).toBeInTheDocument();
    expect(within(summary).getByLabelText("进行中 2")).toBeInTheDocument();
    expect(within(summary).getByLabelText("待测评 0")).toBeInTheDocument();
    expect(within(summary).getByLabelText("待面试 1")).toBeInTheDocument();
    expect(within(summary).getByLabelText("已结束 1")).toBeInTheDocument();
  });

  it("counts pending assessment and interview without counting completed stages", () => {
    const records: Application[] = [
      { ...applications[0], id: "assessment", status: "已投递", next_step: "在线测评" },
      { ...applications[0], id: "assessment-done", status: "笔试完成", next_step: "等待结果" },
      { ...applications[0], id: "interview", status: "已投递", next_step: "技术一面" },
      { ...applications[0], id: "interview-done", status: "AI面试完成", next_step: "等待结果" },
      { ...applications[0], id: "after-exam", status: "笔试完成", next_step: "等待面试" },
      { ...applications[0], id: "second-round", status: "AI面试完成", next_step: "二面" },
      { ...applications[0], id: "assessment-next", status: "面试完成", next_step: "等待测评" },
      { ...applications[0], id: "initial-round", status: "已投递", next_step: "初面" },
      { ...applications[0], id: "follow-up-round", status: "已投递", next_step: "复面" },
    ];

    render(<StatusSummary applications={records} />);

    expect(screen.getByLabelText("总投递 9")).toBeInTheDocument();
    expect(screen.getByLabelText("进行中 9")).toBeInTheDocument();
    expect(screen.getByLabelText("待测评 2")).toBeInTheDocument();
    expect(screen.getByLabelText("待面试 5")).toBeInTheDocument();
    expect(screen.getByLabelText("已结束 0")).toBeInTheDocument();
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

  it("saves settings, clears stale success, and refreshes every data view", async () => {
    const saveModelSettings = vi.fn().mockResolvedValue({
      ...integrationSettings.model,
      enabled: true,
      credential_configured: true,
    });
    const listApplications = vi.fn().mockResolvedValue(applications);
    const listInterviews = vi.fn().mockResolvedValue(interviews);
    const user = userEvent.setup();
    render(<AppShell api={api({ saveModelSettings, listApplications, listInterviews })} />);
    await waitFor(() => {
      expect(listApplications).toHaveBeenCalledTimes(2);
      expect(listInterviews).toHaveBeenCalledTimes(2);
    });
    await user.click(screen.getByRole("tab", { name: "设置" }));

    const modelToggle = await screen.findByRole("checkbox", { name: "启用模型" });
    await user.click(modelToggle);
    await user.type(screen.getByLabelText("API Key"), "temporary-key");
    await user.click(screen.getByRole("button", { name: "保存模型设置" }));

    expect(saveModelSettings).toHaveBeenCalledWith(
      expect.objectContaining({ model: "deepseek-chat", enabled: true }),
    );
    expect(await screen.findByText("模型设置已保存")).toBeInTheDocument();
    await waitFor(() => {
      expect(listApplications).toHaveBeenCalledTimes(4);
      expect(listInterviews).toHaveBeenCalledTimes(4);
    });

    await user.click(modelToggle);
    expect(screen.queryByText("模型设置已保存")).not.toBeInTheDocument();
  });

  it("shows daily, natural-week, exclusive funnel, and todo review sections", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 8, 9, 12));
    const today = new Date();
    const monday = new Date(2026, 8, 7, 12);
    const sunday = new Date(2026, 8, 6, 12);
    const localDate = (value: Date) => {
      const year = value.getFullYear();
      const month = String(value.getMonth() + 1).padStart(2, "0");
      const day = String(value.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    };
    const datedApplications: Application[] = [
      { ...applications[0], id: "today", applied_date: localDate(today), status: "已投递", next_step: "等待筛选" },
      { ...applications[0], id: "monday", applied_date: localDate(monday), status: "笔试完成", next_step: "等待面试" },
      { ...applications[0], id: "sunday", applied_date: localDate(sunday), status: "笔试", next_step: "等待笔试" },
      { ...applications[0], id: "offer", applied_date: localDate(monday), status: "Offer", next_step: null },
      { ...applications[1], id: "closed", applied_date: localDate(monday) },
    ];
    const user = userEvent.setup();
    render(
      <AppShell
        api={api({ listApplications: vi.fn().mockResolvedValue(datedApplications) })}
      />,
    );
    await user.click(screen.getByRole("tab", { name: "复盘" }));
    const panel = screen.getByRole("tabpanel", { name: "复盘" });

    expect(await within(panel).findByRole("region", { name: "日复盘" })).toHaveTextContent(
      "今日新增投递1",
    );
    expect(within(panel).getByRole("region", { name: "周复盘" })).toHaveTextContent(
      "本周投递4",
    );
    const funnel = within(panel).getByRole("region", { name: "流程漏斗" });
    expect(funnel).toHaveTextContent("已投递1");
    expect(funnel).toHaveTextContent("测评1");
    expect(funnel).toHaveTextContent("面试1");
    expect(funnel).toHaveTextContent("Offer1");
    expect(funnel).toHaveTextContent("结束1");
    expect(funnel).toHaveTextContent("当前节点合计 5");
    expect(within(panel).getByRole("region", { name: "当前待办" })).toBeInTheDocument();
  });
});

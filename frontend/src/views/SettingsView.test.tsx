import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { JobHuntApi } from "../api/client";
import type { LocalConfig } from "../api/types";
import { SettingsView } from "./SettingsView";

const config: LocalConfig = {
  excel_path: "C:/tracker.xlsx",
  backup_dir: "C:/backups",
  interview_dir: "C:/interviews",
  notion_enabled: false,
  model_enabled: false,
};

const integrations = {
  model: {
    enabled: false,
    provider: "deepseek",
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

function api(overrides: Record<string, unknown> = {}): JobHuntApi {
  return {
    listApplications: vi.fn().mockResolvedValue([]),
    listInterviews: vi.fn().mockResolvedValue([]),
    getConfig: vi.fn().mockResolvedValue(config),
    saveConfig: vi.fn().mockResolvedValue(config),
    proposeAction: vi.fn(),
    modifyAction: vi.fn(),
    confirmAction: vi.fn(),
    cancelAction: vi.fn(),
    getSettings: vi.fn().mockResolvedValue(integrations),
    saveModelSettings: vi.fn().mockResolvedValue({
      ...integrations.model,
      enabled: true,
      credential_configured: true,
    }),
    testModelSettings: vi.fn().mockResolvedValue({
      status: "connected",
      structured_output: true,
    }),
    saveNotionSettings: vi.fn().mockResolvedValue({
      enabled: true,
      credential_configured: true,
      database_configured: true,
    }),
    testNotionSettings: vi.fn().mockResolvedValue({ status: "connected" }),
    syncInterview: vi.fn(),
    ...overrides,
  } as unknown as JobHuntApi;
}

describe("SettingsView integrations", () => {
  it("saves a provider key without rendering it back", async () => {
    const saveModelSettings = vi.fn().mockResolvedValue({
      ...integrations.model,
      enabled: true,
      credential_configured: true,
    });
    const jobApi = api({ saveModelSettings });
    const user = userEvent.setup();
    render(<SettingsView api={jobApi} />);

    await user.selectOptions(await screen.findByLabelText("模型供应商"), "deepseek");
    await user.click(screen.getByRole("checkbox", { name: "启用模型" }));
    await user.type(screen.getByLabelText("API Key"), "secret-value");
    await user.click(screen.getByRole("button", { name: "保存模型设置" }));

    expect(saveModelSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: true,
        provider: "deepseek",
        api_key: "secret-value",
      }),
    );
    expect(screen.queryByDisplayValue("secret-value")).not.toBeInTheDocument();
    expect(await screen.findByText("已配置")).toBeInTheDocument();
  });

  it("omits API keys for Ollama", async () => {
    const saveModelSettings = vi.fn().mockResolvedValue({
      enabled: true,
      provider: "ollama",
      base_url: "http://127.0.0.1:11434/v1",
      model: "qwen3:8b",
      credential_configured: false,
      requires_api_key: false,
    });
    const jobApi = api({ saveModelSettings });
    const user = userEvent.setup();
    render(<SettingsView api={jobApi} />);

    await user.selectOptions(await screen.findByLabelText("模型供应商"), "ollama");
    expect(screen.queryByLabelText("API Key")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "启用模型" }));
    await user.click(screen.getByRole("button", { name: "保存模型设置" }));

    expect(saveModelSettings).toHaveBeenCalledTimes(1);
    expect(saveModelSettings.mock.calls[0][0]).not.toHaveProperty("api_key");
  });

  it("shows Notion configuration and connection states without retaining the token", async () => {
    const jobApi = api();
    const user = userEvent.setup();
    render(<SettingsView api={jobApi} />);

    await screen.findByLabelText("Notion Token");
    await user.click(screen.getByRole("checkbox", { name: "启用 Notion" }));
    await user.type(screen.getByLabelText("Notion Token"), "notion-secret");
    await user.type(screen.getByLabelText("面经数据库 ID"), "database-id");
    await user.click(screen.getByRole("button", { name: "保存 Notion 设置" }));

    expect(screen.queryByDisplayValue("notion-secret")).not.toBeInTheDocument();
    expect(await screen.findByText("已配置")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "测试 Notion 连接" }));
    expect(await screen.findByText("连接成功")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("notion-secret");
  });

  it("reports a failed model connection with the stable UI state", async () => {
    const jobApi = api({
      testModelSettings: vi.fn().mockRejectedValue(new Error("provider detail")),
    });
    const user = userEvent.setup();
    render(<SettingsView api={jobApi} />);

    await user.click(await screen.findByRole("button", { name: "测试模型连接" }));

    await waitFor(() => expect(screen.getByText("连接失败")).toBeInTheDocument());
    expect(document.body).not.toHaveTextContent("provider detail");
  });
});

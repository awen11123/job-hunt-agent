import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "./App";

const fakeApi = {
  listApplications: async () => [],
  listInterviews: async () => [],
  getConfig: async () => ({
    excel_path: null,
    backup_dir: "C:/JobHuntAgent/backups",
    interview_dir: "C:/JobHuntAgent/interviews",
    notion_enabled: false,
    model_enabled: false,
  }),
  proposeAction: async () => {
    throw new Error("not used in the shell test");
  },
  confirmAction: async () => {
    throw new Error("not used in the shell test");
  },
  cancelAction: async () => {
    throw new Error("not used in the shell test");
  },
};

describe("App", () => {
  it("renders the operational navigation", () => {
    render(<App api={fakeApi} />);

    expect(screen.getByRole("tab", { name: "投递看板" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "面经" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "复盘" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "设置" })).toBeInTheDocument();
  });

  it("switches the active workspace tab", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi} />);

    await user.click(screen.getByRole("tab", { name: "面经" }));

    expect(screen.getByRole("tab", { name: "面经" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("heading", { name: "面经" })).toBeInTheDocument();
  });

  it("moves tab focus and selection with Arrow, Home, and End keys", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi} />);
    const applicationsTab = screen.getByRole("tab", { name: "投递看板" });
    const interviewsTab = screen.getByRole("tab", { name: "面经" });
    const reviewTab = screen.getByRole("tab", { name: "复盘" });
    const settingsTab = screen.getByRole("tab", { name: "设置" });

    applicationsTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(interviewsTab).toHaveFocus();
    expect(interviewsTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{End}");
    expect(settingsTab).toHaveFocus();
    expect(settingsTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowLeft}");
    expect(reviewTab).toHaveFocus();
    expect(reviewTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Home}");
    expect(applicationsTab).toHaveFocus();
    expect(applicationsTab).toHaveAttribute("aria-selected", "true");
  });

  it("keeps every controlled tab panel mounted", () => {
    render(<App api={fakeApi} />);

    expect(document.getElementById("panel-applications")).not.toHaveAttribute("hidden");
    expect(document.getElementById("panel-interviews")).toHaveAttribute("hidden");
    expect(document.getElementById("panel-review")).toHaveAttribute("hidden");
    expect(document.getElementById("panel-settings")).toHaveAttribute("hidden");
  });

  it("collapses and restores the assistant workspace", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi} />);

    await user.click(screen.getByRole("button", { name: "收起助手" }));
    expect(screen.queryByRole("complementary", { name: "求职助手" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "展开助手" }));
    expect(screen.getByRole("complementary", { name: "求职助手" })).toBeInTheDocument();
  });
});

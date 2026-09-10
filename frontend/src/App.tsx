import { useState } from "react";
import {
  BarChart3,
  Bot,
  BriefcaseBusiness,
  Database,
  NotebookText,
  PanelRightClose,
  PanelRightOpen,
  Settings,
  type LucideIcon,
} from "lucide-react";

import type { JobHuntApi } from "./api/client";

type TabId = "applications" | "interviews" | "review" | "settings";

interface TabDefinition {
  id: TabId;
  label: string;
  icon: LucideIcon;
}

const tabs: TabDefinition[] = [
  { id: "applications", label: "投递看板", icon: BriefcaseBusiness },
  { id: "interviews", label: "面经", icon: NotebookText },
  { id: "review", label: "复盘", icon: BarChart3 },
  { id: "settings", label: "设置", icon: Settings },
];

interface AppProps {
  api: JobHuntApi;
}

export default function App({ api }: AppProps) {
  const [activeTab, setActiveTab] = useState<TabId>("applications");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const active = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  void api;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <BriefcaseBusiness size={20} strokeWidth={2} />
          </span>
          <div>
            <strong>秋招工作台</strong>
            <span>Job Hunt Agent</span>
          </div>
        </div>

        <div className="topbar-actions">
          <span className="local-status">
            <Database size={15} aria-hidden="true" />
            本地数据
          </span>
          {!assistantOpen && (
            <button
              className="icon-button"
              type="button"
              aria-label="展开助手"
              title="展开助手"
              onClick={() => setAssistantOpen(true)}
            >
              <PanelRightOpen size={19} />
            </button>
          )}
        </div>
      </header>

      <nav className="tabbar" aria-label="主要功能">
        <div role="tablist" aria-label="工作区">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const selected = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={17} aria-hidden="true" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </nav>

      <div className={assistantOpen ? "work-layout" : "work-layout assistant-closed"}>
        <main
          id={`panel-${active.id}`}
          role="tabpanel"
          aria-labelledby={`tab-${active.id}`}
          className="main-workspace"
        >
          <div className="workspace-heading">
            <h1>{active.label}</h1>
          </div>
          <div className="workspace-placeholder" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </main>

        {assistantOpen && (
          <aside className="assistant" aria-label="求职助手">
            <div className="assistant-heading">
              <div>
                <Bot size={18} aria-hidden="true" />
                <h2>求职助手</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="收起助手"
                title="收起助手"
                onClick={() => setAssistantOpen(false)}
              >
                <PanelRightClose size={19} />
              </button>
            </div>
            <div className="assistant-placeholder" aria-hidden="true">
              <span />
              <span />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

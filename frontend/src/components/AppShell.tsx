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
import { useRef, useState, type KeyboardEvent } from "react";

import type { JobHuntApi } from "../api/client";
import { ApplicationsView } from "../views/ApplicationsView";
import { InterviewsView } from "../views/InterviewsView";
import { ReviewView } from "../views/ReviewView";
import { SettingsView } from "../views/SettingsView";
import { AssistantPanel } from "./AssistantPanel";

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

interface AppShellProps {
  api: JobHuntApi;
}

export function AppShell({ api }: AppShellProps) {
  const [activeTab, setActiveTab] = useState<TabId>("applications");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [applicationVersion, setApplicationVersion] = useState(0);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const moveToTab = (index: number) => {
    setActiveTab(tabs[index].id);
    tabRefs.current[index]?.focus();
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let targetIndex: number | null = null;
    if (event.key === "ArrowRight") targetIndex = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") targetIndex = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") targetIndex = 0;
    else if (event.key === "End") targetIndex = tabs.length - 1;
    if (targetIndex !== null) {
      event.preventDefault();
      moveToTab(targetIndex);
    }
  };

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
          <span className="local-status"><Database size={15} aria-hidden="true" />本地数据</span>
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
        <div role="tablist" aria-label="工作区" aria-orientation="horizontal">
          {tabs.map((tab, index) => {
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
                ref={(element) => {
                  tabRefs.current[index] = element;
                }}
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
              >
                <Icon size={17} aria-hidden="true" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </nav>

      <div className={assistantOpen ? "work-layout" : "work-layout assistant-closed"}>
        <main className="main-workspace">
          <section
            id="panel-applications"
            role="tabpanel"
            aria-labelledby="tab-applications"
            hidden={activeTab !== "applications"}
          >
            <ApplicationsView api={api} refreshVersion={applicationVersion} />
          </section>
          <section
            id="panel-interviews"
            role="tabpanel"
            aria-labelledby="tab-interviews"
            hidden={activeTab !== "interviews"}
          >
            <InterviewsView api={api} />
          </section>
          <section
            id="panel-review"
            role="tabpanel"
            aria-labelledby="tab-review"
            hidden={activeTab !== "review"}
          >
            <ReviewView api={api} refreshVersion={applicationVersion} />
          </section>
          <section
            id="panel-settings"
            role="tabpanel"
            aria-labelledby="tab-settings"
            hidden={activeTab !== "settings"}
          >
            <SettingsView api={api} />
          </section>
        </main>

        {assistantOpen && (
          <aside className="assistant" aria-label="求职助手">
            <div className="assistant-heading">
              <div><Bot size={18} aria-hidden="true" /><h2>求职助手</h2></div>
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
            <AssistantPanel
              api={api}
              onApplicationsChanged={() => setApplicationVersion((value) => value + 1)}
            />
          </aside>
        )}
      </div>
    </div>
  );
}

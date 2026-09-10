import { AlertCircle, CheckCircle2, Clock3 } from "lucide-react";
import { useEffect, useState } from "react";

import type { JobHuntApi } from "../api/client";
import type { Application, Interview } from "../api/types";
import { isClosedStatus } from "../components/ApplicationTable";
import {
  ASSESSMENT_STAGE_MARKERS,
  INTERVIEW_STAGE_MARKERS,
  isPendingStage,
} from "../components/StatusSummary";

interface ReviewViewProps {
  api: JobHuntApi;
  refreshVersion?: number;
}

function localDateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isInRange(value: string | null, start: string, end: string): boolean {
  return Boolean(value && value >= start && value <= end);
}

function interviewDate(interview: Interview): string {
  return (interview.scheduled_at || interview.created_at).slice(0, 10);
}

function stageText(application: Application): string {
  return `${application.status} ${application.next_step || ""}`;
}

type FunnelStage = "已投递" | "测评" | "面试" | "Offer" | "结束";

function currentFunnelStage(application: Application): FunnelStage {
  const stage = stageText(application);
  if (isClosedStatus(application.status)) return "结束";
  if (/offer|录用/i.test(stage)) return "Offer";
  if (isPendingStage(application, INTERVIEW_STAGE_MARKERS)) return "面试";
  if (isPendingStage(application, ASSESSMENT_STAGE_MARKERS)) return "测评";
  return "已投递";
}

export function ReviewView({ api, refreshVersion = 0 }: ReviewViewProps) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(false);
    Promise.all([api.listApplications(), api.listInterviews()])
      .then(([applicationRecords, interviewRecords]) => {
        if (!current) return;
        setApplications(applicationRecords);
        setInterviews(interviewRecords);
      })
      .catch(() => {
        if (current) setError(true);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [api, refreshVersion]);

  const today = new Date();
  const todayValue = localDateString(today);
  const mondayOffset = today.getDay() === 0 ? 6 : today.getDay() - 1;
  const weekStart = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() - mondayOffset,
  );
  const weekStartValue = localDateString(weekStart);
  const todayApplications = applications.filter(
    (item) => item.applied_date === todayValue,
  ).length;
  const weekApplications = applications.filter((item) =>
    isInRange(item.applied_date, weekStartValue, todayValue),
  ).length;
  const todayInterviews = interviews.filter(
    (item) => interviewDate(item) === todayValue,
  ).length;
  const weekInterviews = interviews.filter((item) =>
    isInRange(interviewDate(item), weekStartValue, todayValue),
  ).length;
  const active = applications.filter((item) => !isClosedStatus(item.status));
  const pendingSync = interviews.filter((item) =>
    ["pending", "failed"].includes(item.sync_status),
  );
  const nextSteps = active.filter((item) => item.next_step).slice(0, 6);
  const funnelStages: FunnelStage[] = ["已投递", "测评", "面试", "Offer", "结束"];
  const currentStages = applications.map(currentFunnelStage);
  const funnel = funnelStages.map(
    (stage) => [stage, currentStages.filter((value) => value === stage).length] as const,
  );

  return (
    <div className="view-content review-view">
      <div className="workspace-heading">
        <div>
          <h1>复盘</h1>
          <p>基于当前投递与面经记录</p>
        </div>
      </div>
      {loading ? (
        <p className="view-state" role="status">正在汇总...</p>
      ) : error ? (
        <p className="error-state" role="alert">复盘数据加载失败。</p>
      ) : (
        <div className="review-grid">
          <section className="review-section" aria-label="日复盘">
            <h2>日复盘</h2>
            <div className="review-lines">
              <p><span>今日新增投递</span><strong>{todayApplications}</strong></p>
              <p><span>今日面试</span><strong>{todayInterviews}</strong></p>
            </div>
          </section>

          <section className="review-section" aria-label="周复盘">
            <h2>周复盘</h2>
            <div className="review-lines">
              <p><span>本周投递</span><strong>{weekApplications}</strong></p>
              <p><span>本周面试</span><strong>{weekInterviews}</strong></p>
            </div>
          </section>

          <section className="review-section" aria-label="流程漏斗">
            <h2>流程漏斗</h2>
            <p className="muted-text">当前节点计数，不代表历史转化率</p>
            <p className="muted-text">当前节点合计 {currentStages.length}</p>
            <ul className="distribution-list">
              {funnel.map(([label, count]) => (
                <li key={label} aria-label={`${label} ${count}`}>
                  <span>{label}</span><strong>{count}</strong>
                </li>
              ))}
            </ul>
          </section>

          <section className="review-section review-todos" aria-label="当前待办">
            <h2>当前待办</h2>
            {nextSteps.length === 0 && pendingSync.length === 0 ? (
              <p className="todo-line"><CheckCircle2 size={17} />暂无明确待办</p>
            ) : (
              <ul>
                {nextSteps.map((item) => (
                  <li key={item.id}>
                    <Clock3 size={17} />
                    <span>{item.company}：{item.next_step}</span>
                  </li>
                ))}
                {pendingSync.length > 0 && (
                  <li><AlertCircle size={17} /><span>{pendingSync.length} 条面经等待同步</span></li>
                )}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

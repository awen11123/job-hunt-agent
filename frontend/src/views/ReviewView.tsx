import { AlertCircle, CheckCircle2, Clock3 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { JobHuntApi } from "../api/client";
import type { Application, Interview } from "../api/types";
import { isClosedStatus } from "../components/ApplicationTable";

interface ReviewViewProps {
  api: JobHuntApi;
  refreshVersion?: number;
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

  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>();
    applications.forEach((application) => {
      counts.set(application.status, (counts.get(application.status) || 0) + 1);
    });
    return Array.from(counts.entries()).sort((left, right) => right[1] - left[1]);
  }, [applications]);
  const active = applications.filter((item) => !isClosedStatus(item.status));
  const pendingSync = interviews.filter((item) =>
    ["pending", "failed"].includes(item.sync_status),
  );
  const nextSteps = active.filter((item) => item.next_step).slice(0, 6);

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
          <section className="review-section" aria-labelledby="review-overview">
            <h2 id="review-overview">流程概况</h2>
            <dl className="review-stats">
              <div><dt>有效流程</dt><dd>{active.length}</dd></div>
              <div><dt>面经记录</dt><dd>{interviews.length}</dd></div>
              <div><dt>待同步</dt><dd>{pendingSync.length}</dd></div>
            </dl>
          </section>
          <section className="review-section" aria-labelledby="review-statuses">
            <h2 id="review-statuses">状态分布</h2>
            {statusCounts.length === 0 ? (
              <p className="muted-text">暂无状态数据</p>
            ) : (
              <ul className="distribution-list">
                {statusCounts.map(([name, count]) => (
                  <li key={name}><span>{name}</span><strong>{count}</strong></li>
                ))}
              </ul>
            )}
          </section>
          <section className="review-section review-todos" aria-labelledby="review-todos">
            <h2 id="review-todos">当前待办</h2>
            {nextSteps.length === 0 && pendingSync.length === 0 ? (
              <p className="todo-line"><CheckCircle2 size={17} />暂无明确待办</p>
            ) : (
              <ul>
                {nextSteps.map((item) => (
                  <li key={item.id}><Clock3 size={17} /><span>{item.company}：{item.next_step}</span></li>
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

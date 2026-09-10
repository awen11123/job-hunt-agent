import { ChevronDown, ChevronUp, CloudUpload, NotebookText, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { JobHuntApi } from "../api/client";
import type { Interview } from "../api/types";
import { compareInstantsDescending, localDateFromInstant } from "../utils/localDate";

const syncLabels = {
  local: "仅本地",
  pending: "待同步",
  synced: "已同步",
  failed: "同步失败",
} as const;

interface InterviewsViewProps {
  api: JobHuntApi;
  refreshVersion?: number;
}

export function InterviewsView({ api, refreshVersion = 0 }: InterviewsViewProps) {
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retryVersion, setRetryVersion] = useState(0);
  const [syncing, setSyncing] = useState<Set<string>>(new Set());
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(false);
    api
      .listInterviews()
      .then((records) => {
        if (current) setInterviews(records);
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
  }, [api, refreshVersion, retryVersion]);

  const sorted = useMemo(
    () =>
      [...interviews].sort((left, right) => {
        const leftDate = left.scheduled_at || left.created_at;
        const rightDate = right.scheduled_at || right.created_at;
        return compareInstantsDescending(leftDate, rightDate);
      }),
    [interviews],
  );

  const toggle = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const sync = async (interview: Interview) => {
    setSyncError(null);
    setSyncing((current) => new Set(current).add(interview.id));
    try {
      const updated = await api.syncInterview(interview.id);
      setInterviews((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch {
      setSyncError(interview.id);
    } finally {
      setSyncing((current) => {
        const next = new Set(current);
        next.delete(interview.id);
        return next;
      });
    }
  };

  return (
    <div className="view-content interviews-view">
      <div className="workspace-heading">
        <div>
          <h1>面经</h1>
          <p>本地 Markdown 面试记录</p>
        </div>
      </div>
      {loading ? (
        <p className="view-state" role="status">正在读取面经...</p>
      ) : error ? (
        <div className="error-state" role="alert">
          <span>面经加载失败，请检查本地面经目录。</span>
          <button type="button" onClick={() => setRetryVersion((value) => value + 1)}>
            <RefreshCw size={16} aria-hidden="true" />
            重试
          </button>
        </div>
      ) : sorted.length === 0 ? (
        <div className="empty-state">
          <NotebookText size={28} aria-hidden="true" />
          <h2>还没有面经</h2>
          <p>保存后的面经会按时间显示在这里。</p>
        </div>
      ) : (
        <div className="interview-list">
          {sorted.map((interview) => {
            const isExpanded = expanded.has(interview.id);
            const preview = interview.raw_notes.slice(0, 48);
            return (
              <article className="interview-item" key={interview.id}>
                <div className="interview-meta">
                  <div>
                    <h2>{interview.company}</h2>
                    <span>{interview.round_name}</span>
                  </div>
                  <time dateTime={interview.scheduled_at || interview.created_at}>
                    {localDateFromInstant(interview.scheduled_at || interview.created_at)}
                  </time>
                </div>
                <div className="interview-tags">
                  {interview.result && <span>{interview.result}</span>}
                  {interview.format && <span>{interview.format}</span>}
                  <span className={`sync-${interview.sync_status}`}>
                    {syncLabels[interview.sync_status]}
                  </span>
                </div>
                {interview.sync_status !== "synced" && (
                  <button
                    className="text-button sync-button"
                    type="button"
                    aria-label={`${interview.sync_status === "failed" ? "重试同步" : "同步"} ${interview.company}`}
                    disabled={syncing.has(interview.id)}
                    onClick={() => void sync(interview)}
                  >
                    <CloudUpload size={16} aria-hidden="true" />
                    {syncing.has(interview.id)
                      ? "同步中..."
                      : interview.sync_status === "failed"
                        ? "重试同步"
                        : "同步到 Notion"}
                  </button>
                )}
                {syncError === interview.id && (
                  <p className="inline-error interview-sync-error" role="alert">
                    同步失败，请稍后重试。
                  </p>
                )}
                <p className="interview-notes">
                  {isExpanded ? interview.raw_notes : `${preview}${interview.raw_notes.length > 48 ? "..." : ""}`}
                </p>
                {interview.raw_notes.length > 48 && (
                  <button
                    className="text-button"
                    type="button"
                    aria-label={isExpanded ? "收起面经" : "展开面经"}
                    onClick={() => toggle(interview.id)}
                  >
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    {isExpanded ? "收起" : "展开"}
                  </button>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

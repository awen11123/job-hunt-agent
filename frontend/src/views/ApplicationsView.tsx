import { RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { JobHuntApi } from "../api/client";
import type { Application } from "../api/types";
import { ApplicationTable, isClosedStatus } from "../components/ApplicationTable";
import { StatusSummary } from "../components/StatusSummary";

interface ApplicationsViewProps {
  api: JobHuntApi;
  refreshVersion?: number;
}

export function ApplicationsView({ api, refreshVersion = 0 }: ApplicationsViewProps) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("全部状态");
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    api
      .listApplications()
      .then((records) => {
        if (current) setApplications(records);
      })
      .catch(() => {
        if (current) setError("投递数据加载失败，请检查 Excel 文件是否可用。");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [api, refreshVersion, retryVersion]);

  const statuses = useMemo(
    () => Array.from(new Set(applications.map((item) => item.status))).sort(),
    [applications],
  );
  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("zh-CN");
    return applications.filter((item) => {
      const matchesStatus = status === "全部状态" || item.status === status;
      const matchesSearch =
        query.length === 0 ||
        [item.company, item.role, item.location || ""].some((value) =>
          value.toLocaleLowerCase("zh-CN").includes(query),
        );
      return matchesStatus && matchesSearch;
    });
  }, [applications, search, status]);
  const active = filtered.filter((item) => !isClosedStatus(item.status));
  const closed = filtered.filter((item) => isClosedStatus(item.status));

  return (
    <div className="view-content applications-view">
      <div className="workspace-heading">
        <div>
          <h1>投递看板</h1>
          <p>Excel 中的最新流程</p>
        </div>
      </div>

      {loading ? (
        <p className="view-state" role="status">正在读取投递记录...</p>
      ) : error ? (
        <div className="error-state" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRetryVersion((value) => value + 1)}>
            <RefreshCw size={16} aria-hidden="true" />
            重试
          </button>
        </div>
      ) : applications.length === 0 ? (
        <div className="empty-state">
          <BriefcaseEmptyIcon />
          <h2>还没有投递记录</h2>
          <p>请先在设置中选择投递 Excel 文件。</p>
        </div>
      ) : (
        <>
          <StatusSummary applications={applications} />
          <div className="filterbar">
            <label className="search-field">
              <span className="visually-hidden">搜索投递</span>
              <Search size={17} aria-hidden="true" />
              <input
                type="search"
                aria-label="搜索投递"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索企业、岗位或地点"
              />
            </label>
            <label>
              <span className="visually-hidden">状态筛选</span>
              <select
                aria-label="状态筛选"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option>全部状态</option>
                {statuses.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          </div>

          {filtered.length === 0 ? (
            <p className="view-state">没有符合条件的投递。</p>
          ) : (
            <div className="application-groups">
              <ApplicationTable applications={active} label="进行中流程" />
              <ApplicationTable applications={closed} label="已结束流程" closed />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function BriefcaseEmptyIcon() {
  return <span className="empty-mark" aria-hidden="true">0</span>;
}

import { ExternalLink } from "lucide-react";

import type { Application } from "../api/types";

export const CLOSED_STATUS_MARKERS = [
  "未通过",
  "结束",
  "拒绝",
  "放弃",
  "终止",
  "淘汰",
] as const;

export function isClosedStatus(status: string): boolean {
  return CLOSED_STATUS_MARKERS.some((marker) => status.includes(marker));
}

function displayDate(value: string | null): string {
  return value || "-";
}

function statusTone(status: string): string {
  if (isClosedStatus(status)) return "status-ended";
  if (status.includes("面试")) return "status-interview";
  if (status.includes("测评") || status.includes("笔试")) return "status-assessment";
  return "status-active";
}

interface ApplicationTableProps {
  applications: Application[];
  label: string;
  closed?: boolean;
}

export function ApplicationTable({
  applications,
  label,
  closed = false,
}: ApplicationTableProps) {
  if (applications.length === 0) return null;

  return (
    <section
      className={closed ? "application-section closed-section" : "application-section"}
      aria-label={label}
    >
      <div className="section-title-row">
        <h2>{label}</h2>
        <span>{applications.length} 条</span>
      </div>
      <div className="table-scroll">
        <table className="application-table">
          <colgroup>
            <col className="column-company" />
            <col className="column-role" />
            <col className="column-date" />
            <col className="column-location" />
            <col className="column-status" />
            <col className="column-next" />
            <col className="column-note" />
            <col className="column-link" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">企业</th>
              <th scope="col">岗位</th>
              <th scope="col">投递日期</th>
              <th scope="col">地点</th>
              <th scope="col">状态</th>
              <th scope="col">下一节点</th>
              <th scope="col">备注</th>
              <th scope="col"><span className="visually-hidden">链接</span></th>
            </tr>
          </thead>
          <tbody>
            {applications.map((application) => (
              <tr key={application.id}>
                <td className="company-cell">{application.company}</td>
                <td title={application.role}>{application.role}</td>
                <td>{displayDate(application.applied_date)}</td>
                <td>{application.location || "-"}</td>
                <td>
                  <span className={`status-chip ${statusTone(application.status)}`}>
                    {application.status}
                  </span>
                </td>
                <td>{application.next_step || "-"}</td>
                <td title={application.notes || undefined}>{application.notes || "-"}</td>
                <td className="link-cell">
                  {application.job_url ? (
                    <a
                      href={application.job_url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`打开 ${application.company} 岗位链接`}
                      title="打开岗位链接"
                    >
                      <ExternalLink size={17} aria-hidden="true" />
                    </a>
                  ) : (
                    <span aria-hidden="true">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

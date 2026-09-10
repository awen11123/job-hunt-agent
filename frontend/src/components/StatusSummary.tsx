import { BriefcaseBusiness, CircleCheck, MessagesSquare, Timer } from "lucide-react";

import type { Application } from "../api/types";
import { isClosedStatus } from "./ApplicationTable";

interface StatusSummaryProps {
  applications: Application[];
}

export function StatusSummary({ applications }: StatusSummaryProps) {
  const closed = applications.filter((item) => isClosedStatus(item.status)).length;
  const active = applications.length - closed;
  const interviewing = applications.filter(
    (item) => !isClosedStatus(item.status) && item.status.includes("面试"),
  ).length;

  const metrics = [
    { label: "总投递", value: applications.length, Icon: BriefcaseBusiness },
    { label: "进行中", value: active, Icon: Timer },
    { label: "面试中", value: interviewing, Icon: MessagesSquare },
    { label: "已结束", value: closed, Icon: CircleCheck },
  ];

  return (
    <section className="status-summary" aria-label="投递概览">
      {metrics.map(({ label, value, Icon }) => (
        <div className="summary-metric" key={label} aria-label={`${label} ${value}`}>
          <Icon size={18} aria-hidden="true" />
          <div>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        </div>
      ))}
    </section>
  );
}

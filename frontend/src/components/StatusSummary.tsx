import {
  BriefcaseBusiness,
  CircleCheck,
  ClipboardCheck,
  MessagesSquare,
  Timer,
} from "lucide-react";

import type { Application } from "../api/types";
import { isClosedStatus } from "./ApplicationTable";

interface StatusSummaryProps {
  applications: Application[];
}

export function StatusSummary({ applications }: StatusSummaryProps) {
  const closed = applications.filter((item) => isClosedStatus(item.status)).length;
  const active = applications.length - closed;
  const pendingAssessment = applications.filter((item) =>
    isPendingStage(item, ["测评", "笔试"]),
  ).length;
  const pendingInterview = applications.filter((item) =>
    isPendingStage(item, ["面试", "一面", "二面", "三面", "终面", "HR面", "AI面"]),
  ).length;

  const metrics = [
    { label: "总投递", value: applications.length, Icon: BriefcaseBusiness },
    { label: "进行中", value: active, Icon: Timer },
    { label: "待测评", value: pendingAssessment, Icon: ClipboardCheck },
    { label: "待面试", value: pendingInterview, Icon: MessagesSquare },
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

export function isPendingStage(application: Application, markers: string[]): boolean {
  if (isClosedStatus(application.status)) return false;
  const status = application.status || "";
  const nextStep = application.next_step || "";
  if (`${status}${nextStep}`.includes("完成")) return false;
  if (nextStep) return markers.some((marker) => nextStep.includes(marker));
  return markers.some((marker) => status.includes(marker));
}

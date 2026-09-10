import { Send } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ApiError, type JobHuntApi } from "../api/client";
import type { ActionDraft, Application, Interview } from "../api/types";
import { compareInstantsDescending } from "../utils/localDate";
import { ActionPreview } from "./ActionPreview";
import { isClosedStatus } from "./ApplicationTable";
import { INTERVIEW_STAGE_MARKERS, isPendingStage } from "./StatusSummary";

interface AssistantPanelProps {
  api: JobHuntApi;
  onApplicationsChanged?: () => void;
}

const urlPattern = /https?:\/\/[^\s，。；！？]+/gi;
const questionPattern = /[?？]|多少|几个|几家|哪些|什么|是否|吗|怎么|如何|为何|为什么/;
const localReadPattern = /本周|近\s*7\s*日|总投递|待面试|等待面试|最近.*面经|面经.*最近/;
const readCommandPattern = /^(?:查|查看|查询|统计|显示|列出|告诉我|帮我查|帮我看|看看)/;

function isReadRequest(text: string): boolean {
  const questionText = text.replace(urlPattern, "");
  return (
    questionPattern.test(questionText) ||
    localReadPattern.test(questionText) ||
    readCommandPattern.test(questionText)
  );
}

function localDateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function inLastSevenLocalDays(value: string | null): boolean {
  if (!value) return false;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6);
  const end = localDateString(today);
  const startValue = localDateString(start);
  return value >= startValue && value <= end;
}

function inCurrentLocalWeek(value: string | null): boolean {
  if (!value) return false;
  const today = new Date();
  const mondayOffset = today.getDay() === 0 ? 6 : today.getDay() - 1;
  const monday = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() - mondayOffset,
  );
  return value >= localDateString(monday) && value <= localDateString(today);
}

function pendingInterviews(applications: Application[]): Application[] {
  return applications.filter(
    (item) =>
      !isClosedStatus(item.status) && isPendingStage(item, INTERVIEW_STAGE_MARKERS),
  );
}

function latestInterview(interviews: Interview[]): Interview | null {
  return (
    [...interviews].sort((left, right) => {
      const leftDate = left.scheduled_at || left.created_at;
      const rightDate = right.scheduled_at || right.created_at;
      return compareInstantsDescending(leftDate, rightDate);
    })[0] || null
  );
}

export function AssistantPanel({ api, onApplicationsChanged }: AssistantPanelProps) {
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState<ActionDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);

  const answerRead = async (text: string): Promise<string> => {
    if (/投递|投了/.test(text) && /本周|近\s*7\s*日|多少|总数|几家|几个/.test(text)) {
      const all = await api.listApplications();
      const records = /本周/.test(text)
        ? all.filter((item) => inCurrentLocalWeek(item.applied_date))
        : /近\s*7\s*日/.test(text)
          ? all.filter((item) => inLastSevenLocalDays(item.applied_date))
          : all;
      const companies = new Set(
        records.map((item) => item.company.trim()).filter((company) => company.length > 0),
      );
      const range = /本周/.test(text)
        ? "本周"
        : /近\s*7\s*日/.test(text)
          ? "近 7 日"
          : "当前";
      return `${range}共投递 ${records.length} 个岗位，涉及 ${companies.size} 家公司。`;
    }
    if (/待面试|等待面试/.test(text)) {
      const records = pendingInterviews(await api.listApplications());
      if (records.length === 0) return "当前没有明确标记为待面试的岗位。";
      return `待面试岗位：${records
        .map((item) => `${item.company} · ${item.role}`)
        .join("；")}。`;
    }
    if (/最近.*面经|面经.*最近/.test(text)) {
      const latest = latestInterview(await api.listInterviews());
      if (!latest) return "当前还没有面经记录。";
      return `最近面经：${latest.company} · ${latest.round_name}${
        latest.result ? ` · ${latest.result}` : ""
      }。`;
    }
    return "当前无模型模式暂不支持这个查询，可以在看板、面经或复盘页直接查看本地数据。";
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || draft) return;
    setBusy(true);
    setError(null);
    setReceipt(null);
    try {
      if (isReadRequest(text)) {
        setReceipt(await answerRead(text));
      } else {
        const proposed = await api.proposeAction(text);
        setDraft(proposed);
      }
      setInput("");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "无法生成安全的变更预览，请检查输入后重试。",
      );
    } finally {
      setBusy(false);
    }
  };

  const modify = async (payload: ActionDraft["payload"]) => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await api.modifyAction(draft.id, payload));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "草稿修改失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      await api.cancelAction(draft.id);
      setDraft(null);
      setReceipt("已取消变更");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "取消失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmAction(draft.id, draft.confirmation_token);
      setDraft(null);
      setReceipt("已写入投递记录");
      onApplicationsChanged?.();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "写入失败，草稿已保留，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="assistant-content">
      <div className="assistant-stream" aria-live="polite">
        {receipt && <p className="assistant-receipt">{receipt}</p>}
        {error && <p className="assistant-error" role="alert">{error}</p>}
        {draft ? (
          <ActionPreview
            draft={draft}
            busy={busy}
            onModify={modify}
            onCancel={cancel}
            onConfirm={confirm}
          />
        ) : (
          !receipt && !error && <p className="assistant-empty">暂无待处理变更</p>
        )}
      </div>
      <form className="assistant-composer" onSubmit={submit}>
        <label>
          <span className="visually-hidden">输入投递操作</span>
          <textarea
            aria-label="输入投递操作"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="记录一条投递..."
            rows={3}
            disabled={Boolean(draft)}
          />
        </label>
        <button
          className="send-button"
          type="submit"
          aria-label="发送"
          title="生成变更预览"
          disabled={busy || Boolean(draft) || input.trim().length === 0}
        >
          <Send size={17} aria-hidden="true" />
          <span>发送</span>
        </button>
      </form>
    </div>
  );
}

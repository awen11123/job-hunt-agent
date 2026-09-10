import { Send } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ApiError, type JobHuntApi } from "../api/client";
import type { ActionDraft } from "../api/types";
import { ActionPreview } from "./ActionPreview";

interface AssistantPanelProps {
  api: JobHuntApi;
  onApplicationsChanged?: () => void;
}

export function AssistantPanel({ api, onApplicationsChanged }: AssistantPanelProps) {
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState<ActionDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || draft) return;
    setBusy(true);
    setError(null);
    setReceipt(null);
    try {
      const proposed = await api.proposeAction(text);
      setDraft(proposed);
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

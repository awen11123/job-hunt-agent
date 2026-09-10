import { Check, Pencil, X } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import type { ActionDraft, JsonValue } from "../api/types";

interface ActionPreviewProps {
  draft: ActionDraft;
  busy?: boolean;
  onModify(payload: ActionDraft["payload"]): Promise<void>;
  onCancel(): Promise<void>;
  onConfirm(): Promise<void>;
}

const applicationFields = [
  ["company", "企业", true],
  ["role", "岗位", true],
  ["applied_date", "投递日期", false],
  ["location", "地点", false],
  ["status", "状态", false],
  ["next_step", "下一节点", false],
  ["next_time", "节点时间", false],
  ["job_url", "岗位链接", false],
  ["notes", "备注", false],
] as const;

function stringValue(value: JsonValue | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

export function ActionPreview({
  draft,
  busy = false,
  onModify,
  onCancel,
  onConfirm,
}: ActionPreviewProps) {
  const [payload, setPayload] = useState(draft.payload);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setPayload(draft.payload);
    setDirty(false);
  }, [draft]);

  const update = (field: string, value: string) => {
    setDirty(true);
    setPayload((current) => ({ ...current, [field]: value || null }));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    await onModify(payload);
  };

  const fields = draft.action === "create_application" ? applicationFields : [];

  return (
    <section className="action-preview" aria-labelledby="action-preview-heading">
      <div className="preview-heading">
        <div>
          <span>待确认</span>
          <h3 id="action-preview-heading">变更预览</h3>
        </div>
        <span className="data-target">Excel 投递表</span>
      </div>

      <form onSubmit={save}>
        {fields.length > 0 ? (
          <div className="preview-fields">
            {fields.map(([field, label, required]) => (
              <label key={field} className={field === "notes" ? "field-wide" : undefined}>
                <span>{label}</span>
                <input
                  aria-label={label}
                  required={required}
                  value={stringValue(payload[field])}
                  onChange={(event) => update(field, event.target.value)}
                />
              </label>
            ))}
          </div>
        ) : (
          <pre className="payload-preview">{JSON.stringify(payload, null, 2)}</pre>
        )}

        <div className="preview-actions">
          <button
            className="secondary-button"
            type="submit"
            disabled={busy || !dirty}
          >
            <Pencil size={15} aria-hidden="true" />
            保存修改
          </button>
          <button
            className="secondary-button danger-button"
            type="button"
            disabled={busy}
            onClick={() => void onCancel()}
          >
            <X size={16} aria-hidden="true" />
            取消变更
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={busy || dirty}
            onClick={() => void onConfirm()}
            title={dirty ? "请先保存修改" : "确认写入 Excel"}
          >
            <Check size={16} aria-hidden="true" />
            确认写入
          </button>
        </div>
      </form>
    </section>
  );
}

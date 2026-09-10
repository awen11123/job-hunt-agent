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

interface FieldDefinition {
  key: string;
  label: string;
  required?: boolean;
  multiline?: boolean;
  numeric?: boolean;
}

const applicationFields: FieldDefinition[] = [
  { key: "company", label: "企业", required: true },
  { key: "role", label: "岗位", required: true },
  { key: "applied_date", label: "投递日期" },
  { key: "location", label: "地点" },
  { key: "status", label: "状态" },
  { key: "next_step", label: "下一节点" },
  { key: "next_time", label: "节点时间" },
  { key: "job_url", label: "岗位链接" },
  { key: "notes", label: "备注", multiline: true },
];

const interviewFields: FieldDefinition[] = [
  { key: "application_id", label: "投递记录 ID", required: true },
  { key: "company", label: "企业", required: true },
  { key: "round_name", label: "面试轮次", required: true },
  { key: "scheduled_at", label: "面试时间" },
  { key: "format", label: "面试形式" },
  { key: "result", label: "结果" },
  { key: "self_score", label: "自评", numeric: true },
  { key: "raw_notes", label: "面试正文", required: true, multiline: true },
];

const patchLabels: Record<string, FieldDefinition> = Object.fromEntries(
  applicationFields.map((field) => [field.key, field]),
);

function objectValue(value: JsonValue | undefined): Record<string, JsonValue> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value;
  return {};
}

function stringValue(value: JsonValue | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function beforeValue(value: JsonValue): string {
  if (value === null) return "空";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function editorState(draft: ActionDraft): Record<string, JsonValue> {
  return draft.action === "update_application"
    ? objectValue(draft.payload.patch)
    : draft.payload;
}

function fieldsForDraft(draft: ActionDraft): FieldDefinition[] {
  if (draft.action === "create_application") return applicationFields;
  if (draft.action === "save_interview") return interviewFields;
  return Object.keys(objectValue(draft.payload.patch)).map(
    (key) => patchLabels[key] || { key, label: key },
  );
}

export function ActionPreview({
  draft,
  busy = false,
  onModify,
  onCancel,
  onConfirm,
}: ActionPreviewProps) {
  const [editable, setEditable] = useState(() => editorState(draft));
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setEditable(editorState(draft));
    setDirty(false);
  }, [draft]);

  const update = (field: FieldDefinition, value: string) => {
    const normalized: JsonValue = field.numeric
      ? value === ""
        ? null
        : Number(value)
      : value || null;
    setDirty(true);
    setEditable((current) => ({ ...current, [field.key]: normalized }));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const payload =
      draft.action === "update_application"
        ? {
            application_id: draft.payload.application_id,
            patch: editable,
          }
        : editable;
    await onModify(payload);
  };

  const fields = fieldsForDraft(draft);
  const target = draft.action === "save_interview" ? "本地 Markdown" : "Excel 投递表";

  return (
    <section className="action-preview" aria-labelledby="action-preview-heading">
      <div className="preview-heading">
        <div>
          <span>待确认</span>
          <h3 id="action-preview-heading">变更预览</h3>
        </div>
        <span className="data-target">{target}</span>
      </div>
      <p className="remote-disclosure">远程发送：无</p>

      {draft.before && (
        <section className="before-preview" aria-label="变更前">
          <h4>变更前</h4>
          <dl>
            {Object.entries(draft.before).map(([key, value]) => (
              <div key={key}>
                <dt>{patchLabels[key]?.label || key}</dt>
                <dd>{beforeValue(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <form onSubmit={save}>
        {draft.action === "update_application" && (
          <label className="readonly-field">
            <span>投递记录 ID</span>
            <input
              aria-label="投递记录 ID"
              value={stringValue(draft.payload.application_id)}
              readOnly
            />
          </label>
        )}
        <div className="preview-fields">
          {fields.map((field) => (
            <label key={field.key} className={field.multiline ? "field-wide" : undefined}>
              <span>{field.label}</span>
              {field.multiline ? (
                <textarea
                  aria-label={field.label}
                  required={field.required}
                  rows={field.key === "raw_notes" ? 6 : 3}
                  value={stringValue(editable[field.key])}
                  onChange={(event) => update(field, event.target.value)}
                />
              ) : (
                <input
                  aria-label={field.label}
                  required={field.required}
                  type={field.numeric ? "number" : "text"}
                  value={stringValue(editable[field.key])}
                  onChange={(event) => update(field, event.target.value)}
                />
              )}
            </label>
          ))}
        </div>

        <div className="preview-actions">
          <button className="secondary-button" type="submit" disabled={busy || !dirty}>
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
            title={dirty ? "请先保存修改" : `确认写入${target}`}
          >
            <Check size={16} aria-hidden="true" />
            确认写入
          </button>
        </div>
      </form>
    </section>
  );
}

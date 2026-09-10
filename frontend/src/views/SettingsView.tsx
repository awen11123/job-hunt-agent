import { Save } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import type { JobHuntApi } from "../api/client";
import type { LocalConfig } from "../api/types";

interface SettingsViewProps {
  api: JobHuntApi;
}

export function SettingsView({ api }: SettingsViewProps) {
  const [config, setConfig] = useState<LocalConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api
      .getConfig()
      .then((loaded) => {
        if (current) setConfig(loaded);
      })
      .catch(() => {
        if (current) setError("设置加载失败。");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [api]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!config) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await api.saveConfig(config);
      setConfig(saved);
      setMessage("设置已保存");
    } catch {
      setError("设置保存失败，请检查路径后重试。");
    } finally {
      setSaving(false);
    }
  };

  const setPath = (field: "excel_path" | "backup_dir" | "interview_dir", value: string) => {
    if (!config) return;
    setMessage(null);
    setConfig({ ...config, [field]: field === "excel_path" && !value ? null : value });
  };

  return (
    <div className="view-content settings-view">
      <div className="workspace-heading">
        <div>
          <h1>设置</h1>
          <p>本地文件与可选服务</p>
        </div>
      </div>
      {loading ? (
        <p className="view-state" role="status">正在读取设置...</p>
      ) : error && !config ? (
        <p className="error-state" role="alert">{error}</p>
      ) : config ? (
        <form className="settings-form" onSubmit={submit}>
          <section aria-labelledby="local-paths-heading">
            <h2 id="local-paths-heading">本地路径</h2>
            <label>
              <span>投递 Excel</span>
              <input
                value={config.excel_path || ""}
                onChange={(event) => setPath("excel_path", event.target.value)}
                placeholder="请选择投递文件"
              />
            </label>
            <label>
              <span>备份目录</span>
              <input
                value={config.backup_dir}
                onChange={(event) => setPath("backup_dir", event.target.value)}
              />
            </label>
            <label>
              <span>面经目录</span>
              <input
                value={config.interview_dir}
                onChange={(event) => setPath("interview_dir", event.target.value)}
              />
            </label>
          </section>
          <section aria-labelledby="optional-services-heading">
            <h2 id="optional-services-heading">可选服务</h2>
            <label className="toggle-row">
              <span><strong>启用 Notion</strong><small>同步面经页面</small></span>
              <input
                type="checkbox"
                aria-label="启用 Notion"
                checked={config.notion_enabled}
                onChange={(event) =>
                  setConfig({ ...config, notion_enabled: event.target.checked })
                }
              />
            </label>
            <label className="toggle-row">
              <span><strong>启用模型</strong><small>使用已配置的模型服务</small></span>
              <input
                type="checkbox"
                aria-label="启用模型"
                checked={config.model_enabled}
                onChange={(event) =>
                  setConfig({ ...config, model_enabled: event.target.checked })
                }
              />
            </label>
          </section>
          <div className="settings-actions">
            <button className="primary-button" type="submit" disabled={saving}>
              <Save size={16} aria-hidden="true" />
              {saving ? "保存中..." : "保存设置"}
            </button>
            {message && <span className="success-message" role="status">{message}</span>}
            {error && <span className="inline-error" role="alert">{error}</span>}
          </div>
        </form>
      ) : null}
    </div>
  );
}

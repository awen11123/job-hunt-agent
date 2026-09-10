import { PlugZap, Save } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import type { JobHuntApi } from "../api/client";
import type {
  IntegrationSettings,
  LocalConfig,
  ModelSettingsInput,
  NotionSettingsInput,
  ProviderName,
} from "../api/types";

interface SettingsViewProps {
  api: JobHuntApi;
  onSaved?: () => void;
}

type ConnectionState = "connected" | "failed" | null;

const providerDefaults: Record<
  ProviderName,
  { base_url: string; model: string; label: string; requires_api_key: boolean }
> = {
  deepseek: {
    label: "DeepSeek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat",
    requires_api_key: true,
  },
  qwen: {
    label: "通义千问",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    requires_api_key: true,
  },
  moonshot: {
    label: "Moonshot",
    base_url: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k",
    requires_api_key: true,
  },
  "openai-compatible": {
    label: "OpenAI 兼容接口",
    base_url: "http://127.0.0.1:8000/v1",
    model: "default",
    requires_api_key: true,
  },
  ollama: {
    label: "Ollama（本地）",
    base_url: "http://127.0.0.1:11434/v1",
    model: "qwen3:8b",
    requires_api_key: false,
  },
};

function statusText(configured: boolean, connection: ConnectionState): string {
  if (connection === "connected") return "连接成功";
  if (connection === "failed") return "连接失败";
  return configured ? "已配置" : "未配置";
}

function statusClass(configured: boolean, connection: ConnectionState): string {
  if (connection === "connected") return "integration-connected";
  if (connection === "failed") return "integration-failed";
  return configured ? "integration-configured" : "integration-empty";
}

export function SettingsView({ api, onSaved }: SettingsViewProps) {
  const [config, setConfig] = useState<LocalConfig | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationSettings | null>(null);
  const [modelForm, setModelForm] = useState<ModelSettingsInput | null>(null);
  const [notionForm, setNotionForm] = useState<NotionSettingsInput>({ enabled: false });
  const [modelKey, setModelKey] = useState("");
  const [notionToken, setNotionToken] = useState("");
  const [notionDatabaseId, setNotionDatabaseId] = useState("");
  const [modelConnection, setModelConnection] = useState<ConnectionState>(null);
  const [notionConnection, setNotionConnection] = useState<ConnectionState>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    Promise.all([api.getConfig(), api.getSettings()])
      .then(([loadedConfig, loadedIntegrations]) => {
        if (!current) return;
        setConfig(loadedConfig);
        setIntegrations(loadedIntegrations);
        setModelForm({
          enabled: loadedIntegrations.model.enabled,
          provider: loadedIntegrations.model.provider,
          base_url: loadedIntegrations.model.base_url,
          model: loadedIntegrations.model.model,
        });
        setNotionForm({ enabled: loadedIntegrations.notion.enabled });
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

  const beginRequest = (name: string) => {
    setSaving(name);
    setMessage(null);
    setError(null);
  };

  const submitLocal = async (event: FormEvent) => {
    event.preventDefault();
    if (!config) return;
    beginRequest("local");
    try {
      const saved = await api.saveConfig(config);
      setConfig(saved);
      setMessage("本地设置已保存");
      onSaved?.();
    } catch {
      setError("设置保存失败，请检查路径后重试。");
    } finally {
      setSaving(null);
    }
  };

  const submitModel = async (event: FormEvent) => {
    event.preventDefault();
    if (!modelForm || !integrations) return;
    beginRequest("model");
    setModelConnection(null);
    const request: ModelSettingsInput = {
      enabled: modelForm.enabled,
      provider: modelForm.provider,
    };
    if (modelForm.base_url?.trim()) request.base_url = modelForm.base_url.trim();
    if (modelForm.model?.trim()) request.model = modelForm.model.trim();
    if (providerDefaults[modelForm.provider].requires_api_key && modelKey.trim()) {
      request.api_key = modelKey.trim();
    }
    try {
      const saved = await api.saveModelSettings(request);
      setIntegrations({ ...integrations, model: saved });
      setModelForm({
        enabled: saved.enabled,
        provider: saved.provider,
        base_url: saved.base_url,
        model: saved.model,
      });
      setConfig((current) => current && { ...current, model_enabled: saved.enabled });
      setModelKey("");
      setMessage("模型设置已保存");
      onSaved?.();
    } catch {
      setError("模型设置保存失败，请检查配置后重试。");
    } finally {
      setSaving(null);
    }
  };

  const submitNotion = async (event: FormEvent) => {
    event.preventDefault();
    if (!integrations) return;
    beginRequest("notion");
    setNotionConnection(null);
    const request: NotionSettingsInput = { enabled: notionForm.enabled };
    if (notionToken.trim()) request.token = notionToken.trim();
    if (notionDatabaseId.trim()) request.interviews_database_id = notionDatabaseId.trim();
    try {
      const saved = await api.saveNotionSettings(request);
      setIntegrations({ ...integrations, notion: saved });
      setNotionForm({ enabled: saved.enabled });
      setConfig((current) => current && { ...current, notion_enabled: saved.enabled });
      setNotionToken("");
      setNotionDatabaseId("");
      setMessage("Notion 设置已保存");
      onSaved?.();
    } catch {
      setError("Notion 设置保存失败，请检查配置后重试。");
    } finally {
      setSaving(null);
    }
  };

  const testModel = async () => {
    beginRequest("model-test");
    try {
      await api.testModelSettings();
      setModelConnection("connected");
    } catch {
      setModelConnection("failed");
    } finally {
      setSaving(null);
    }
  };

  const testNotion = async () => {
    beginRequest("notion-test");
    try {
      await api.testNotionSettings();
      setNotionConnection("connected");
    } catch {
      setNotionConnection("failed");
    } finally {
      setSaving(null);
    }
  };

  const setPath = (field: "excel_path" | "backup_dir" | "interview_dir", value: string) => {
    if (!config) return;
    setMessage(null);
    setError(null);
    setConfig({ ...config, [field]: field === "excel_path" && !value ? null : value });
  };

  const changeProvider = (provider: ProviderName) => {
    if (!modelForm) return;
    const defaults = providerDefaults[provider];
    setModelForm({ ...modelForm, provider, base_url: defaults.base_url, model: defaults.model });
    setModelKey("");
    setModelConnection(null);
  };

  if (loading) return <p className="view-state" role="status">正在读取设置...</p>;
  if (!config || !integrations || !modelForm) {
    return <p className="error-state" role="alert">{error || "设置加载失败。"}</p>;
  }

  const selectedProvider = providerDefaults[modelForm.provider];
  const modelConfigured =
    modelForm.provider === integrations.model.provider &&
    (!selectedProvider.requires_api_key || integrations.model.credential_configured);
  const notionConfigured = integrations.notion.credential_configured && integrations.notion.database_configured;

  return (
    <div className="view-content settings-view">
      <div className="workspace-heading">
        <div><h1>设置</h1><p>本地文件与可选集成</p></div>
      </div>

      <div className="settings-form">
        <form onSubmit={submitLocal}>
          <section aria-labelledby="local-paths-heading">
            <div className="settings-section-heading">
              <div><h2 id="local-paths-heading">本地路径</h2><p>投递表和面经始终保存在你的电脑上</p></div>
            </div>
            <label><span>投递 Excel</span><input value={config.excel_path || ""} onChange={(event) => setPath("excel_path", event.target.value)} placeholder="请选择投递文件" /></label>
            <label><span>备份目录</span><input value={config.backup_dir} onChange={(event) => setPath("backup_dir", event.target.value)} /></label>
            <label><span>面经目录</span><input value={config.interview_dir} onChange={(event) => setPath("interview_dir", event.target.value)} /></label>
            <div className="settings-actions">
              <button className="secondary-button" type="submit" disabled={saving !== null}><Save size={16} aria-hidden="true" />{saving === "local" ? "保存中..." : "保存本地设置"}</button>
            </div>
          </section>
        </form>

        <form onSubmit={submitModel}>
          <section aria-labelledby="model-settings-heading">
            <div className="settings-section-heading">
              <div><h2 id="model-settings-heading">模型服务</h2><p>可选；普通兼容接口或本地 Ollama</p></div>
              <span className={`integration-status ${statusClass(modelConfigured, modelConnection)}`}>{statusText(modelConfigured, modelConnection)}</span>
            </div>
            <label className="toggle-field">
              <span><strong>启用模型</strong><small>用于理解自由文本和回答开放问题</small></span>
              <input type="checkbox" aria-label="启用模型" checked={modelForm.enabled} onChange={(event) => { setModelForm({ ...modelForm, enabled: event.target.checked }); setModelConnection(null); setMessage(null); }} />
            </label>
            <label>
              <span>模型供应商</span>
              <select aria-label="模型供应商" value={modelForm.provider} onChange={(event) => changeProvider(event.target.value as ProviderName)}>
                {Object.entries(providerDefaults).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
              </select>
            </label>
            <label><span>接口地址</span><input aria-label="接口地址" value={modelForm.base_url || ""} onChange={(event) => setModelForm({ ...modelForm, base_url: event.target.value })} /></label>
            <label><span>模型名称</span><input aria-label="模型名称" value={modelForm.model || ""} onChange={(event) => setModelForm({ ...modelForm, model: event.target.value })} /></label>
            {selectedProvider.requires_api_key && (
              <label>
                <span>API Key</span>
                <input aria-label="API Key" type="password" autoComplete="new-password" value={modelKey} placeholder={integrations.model.credential_configured ? "已安全保存；留空则不修改" : "输入 API Key"} onChange={(event) => setModelKey(event.target.value)} />
              </label>
            )}
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={saving !== null}><Save size={16} aria-hidden="true" />保存模型设置</button>
              <button className="secondary-button" type="button" disabled={saving !== null} onClick={() => void testModel()}><PlugZap size={16} aria-hidden="true" />测试模型连接</button>
            </div>
          </section>
        </form>

        <form onSubmit={submitNotion}>
          <section aria-labelledby="notion-settings-heading">
            <div className="settings-section-heading">
              <div><h2 id="notion-settings-heading">Notion 面经</h2><p>可选；只在手动同步时发送面经内容</p></div>
              <span className={`integration-status ${statusClass(notionConfigured, notionConnection)}`}>{statusText(notionConfigured, notionConnection)}</span>
            </div>
            <label className="toggle-field">
              <span><strong>启用 Notion</strong><small>保留本地 Markdown，同时可同步到 Notion</small></span>
              <input type="checkbox" aria-label="启用 Notion" checked={notionForm.enabled} onChange={(event) => { setNotionForm({ enabled: event.target.checked }); setNotionConnection(null); setMessage(null); }} />
            </label>
            <label><span>Notion Token</span><input aria-label="Notion Token" type="password" autoComplete="new-password" value={notionToken} placeholder={integrations.notion.credential_configured ? "已安全保存；留空则不修改" : "输入 Integration Token"} onChange={(event) => setNotionToken(event.target.value)} /></label>
            <label><span>面经数据库 ID</span><input aria-label="面经数据库 ID" value={notionDatabaseId} placeholder={integrations.notion.database_configured ? "已保存；留空则不修改" : "输入数据库 ID"} onChange={(event) => setNotionDatabaseId(event.target.value)} /></label>
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={saving !== null}><Save size={16} aria-hidden="true" />保存 Notion 设置</button>
              <button className="secondary-button" type="button" disabled={saving !== null} onClick={() => void testNotion()}><PlugZap size={16} aria-hidden="true" />测试 Notion 连接</button>
            </div>
          </section>
        </form>

        {message && <p className="success-text" role="status">{message}</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
      </div>
    </div>
  );
}

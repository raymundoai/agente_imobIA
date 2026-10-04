import { History, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { request } from "../api/client";
import { Card } from "../components/Card";

type PromptVersion = {
  id: string;
  base_prompt: string | null;
  chat_model: string | null;
  reasoning_effort: string | null;
  max_output_tokens: number | null;
  note: string | null;
  created_by_email: string | null;
  created_at: string;
};

type AgentPrompt = {
  default_prompt: string;
  default_chat_model: string;
  default_reasoning_effort: string;
  default_max_output_tokens: number;
  reasoning_efforts: string[];
  active: PromptVersion | null;
  versions: PromptVersion[];
};

type Form = { base_prompt: string; chat_model: string; reasoning_effort: string; max_output_tokens: string; note: string };

const EFFORT_LABELS: Record<string, string> = {
  none: "Nenhum",
  minimal: "Mínimo",
  low: "Baixo",
  medium: "Médio",
  high: "Alto",
  xhigh: "Muito alto",
  max: "Máximo",
};

function formFrom(data: AgentPrompt, version: PromptVersion | null): Form {
  return {
    base_prompt: version?.base_prompt ?? data.default_prompt,
    chat_model: version?.chat_model ?? "",
    reasoning_effort: version?.reasoning_effort ?? "",
    max_output_tokens: version?.max_output_tokens ? String(version.max_output_tokens) : "",
    note: "",
  };
}

/** Platform-wide agent prompt and model, saved as versions so any change can be undone. */
export function AgentPromptSettings({ token }: { token: string }) {
  const [data, setData] = useState<AgentPrompt | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    request<AgentPrompt>("/platform/agent", {}, token)
      .then((value) => {
        setData(value);
        setForm(formFrom(value, value.active));
      })
      .catch((reason) => setFeedback({ kind: "error", text: reason instanceof Error ? reason.message : "Falha ao carregar o agente." }));
  }, [token]);

  if (!data || !form) {
    return (
      <Card className="settings-panel-card">
        {feedback ? <div className="error-box">{feedback.text}</div> : <div className="empty-state"><Loader2 className="spin" size={16} /> Carregando agente...</div>}
      </Card>
    );
  }

  const active = formFrom(data, data.active);
  const dirty = (["base_prompt", "chat_model", "reasoning_effort", "max_output_tokens"] as const).some((key) => form[key].trim() !== active[key].trim());
  const usingDefaultPrompt = form.base_prompt.trim() === data.default_prompt;

  async function save() {
    if (!form) return;
    if (!window.confirm("Salvar esta versão? O agente de todos os clientes passa a usá-la imediatamente.")) return;
    setSaving(true);
    setFeedback(null);
    try {
      const next = await request<AgentPrompt>(
        "/platform/agent/versions",
        {
          method: "POST",
          body: JSON.stringify({
            base_prompt: form.base_prompt,
            chat_model: form.chat_model.trim() || null,
            reasoning_effort: form.reasoning_effort || null,
            max_output_tokens: form.max_output_tokens ? Number(form.max_output_tokens) : null,
            note: form.note.trim() || null,
          }),
        },
        token,
      );
      setData(next);
      setForm(formFrom(next, next.active));
      setFeedback({ kind: "success", text: "Nova versão em uso." });
    } catch (reason) {
      setFeedback({ kind: "error", text: reason instanceof Error ? reason.message : "Não foi possível salvar." });
    } finally {
      setSaving(false);
    }
  }

  const update = (patch: Partial<Form>) => setForm((current) => (current ? { ...current, ...patch } : current));

  return (
    <div className="page-stack">
      <Card className="settings-panel-card">
        <div className="settings-panel-header">
          <div>
            <h2>Agente de IA</h2>
            <p>Prompt base e modelo usados no atendimento de leads de todos os clientes.</p>
          </div>
        </div>

        <div className="form-grid agent-model-grid">
          <label>
            Modelo
            <input
              list="agent-model-suggestions"
              onChange={(event) => update({ chat_model: event.target.value })}
              placeholder={`Padrão do servidor: ${data.default_chat_model}`}
              value={form.chat_model}
            />
            <datalist id="agent-model-suggestions">
              <option value={data.default_chat_model} />
            </datalist>
          </label>
          <label>
            Esforço de raciocínio
            <select onChange={(event) => update({ reasoning_effort: event.target.value })} value={form.reasoning_effort}>
              <option value="">Padrão do servidor ({EFFORT_LABELS[data.default_reasoning_effort] ?? data.default_reasoning_effort})</option>
              {data.reasoning_efforts.map((effort) => <option key={effort} value={effort}>{EFFORT_LABELS[effort] ?? effort}</option>)}
            </select>
          </label>
          <label>
            Limite de tokens na resposta
            <input
              inputMode="numeric"
              max={128000}
              min={512}
              onChange={(event) => update({ max_output_tokens: event.target.value.replace(/\D/g, "") })}
              placeholder={`Padrão: ${data.default_max_output_tokens.toLocaleString("pt-BR")}`}
              value={form.max_output_tokens}
            />
          </label>
        </div>

        <label className="agent-prompt-field">
          <span className="agent-prompt-label">
            Prompt base
            <span className={usingDefaultPrompt ? "connection-state state-soon" : "connection-state state-pending"}>
              {usingDefaultPrompt ? "Padrão" : "Personalizado"}
            </span>
          </span>
          <textarea onChange={(event) => update({ base_prompt: event.target.value })} rows={16} spellCheck={false} value={form.base_prompt} />
          <small className="field-hint">
            Antes deste texto entra a apresentação do agente (nome e empresa). Depois entram, automaticamente, as
            instruções extras do cliente, o perfil da empresa, a configuração do agente, os dados do lead e os trechos
            da base de conhecimento.
          </small>
        </label>

        <div className="agent-prompt-actions">
          {!usingDefaultPrompt ? (
            <button className="secondary-button" onClick={() => update({ base_prompt: data.default_prompt })} type="button">
              <RotateCcw size={15} /> Restaurar texto padrão
            </button>
          ) : <span />}
          <input
            aria-label="O que mudou"
            className="agent-note-input"
            maxLength={300}
            onChange={(event) => update({ note: event.target.value })}
            placeholder="O que mudou? (aparece no histórico)"
            value={form.note}
          />
          <button className="primary-button" disabled={!dirty || saving || form.base_prompt.trim().length < 20} onClick={() => void save()} type="button">
            {saving ? "Salvando..." : "Salvar nova versão"}
          </button>
        </div>
        {dirty ? <span className="unsaved-indicator">Alterações não salvas</span> : null}
        {feedback ? <div className={feedback.kind === "error" ? "error-box" : "settings-feedback success"} role="status">{feedback.text}</div> : null}
      </Card>

      <Card className="settings-panel-card">
        <div className="settings-panel-header">
          <div>
            <h2><History size={18} /> Histórico</h2>
            <p>Cada salvamento vira uma versão. Para voltar a uma delas, carregue-a e salve de novo.</p>
          </div>
        </div>
        {data.versions.length === 0 ? (
          <div className="empty-state">Nenhuma alteração ainda: o agente usa o prompt e o modelo padrão.</div>
        ) : (
          <ol className="agent-versions">
            {data.versions.map((version, index) => (
              <li key={version.id}>
                <div>
                  <strong>
                    {new Date(version.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                    {index === 0 ? <span className="connection-state state-connected">Em uso</span> : null}
                  </strong>
                  <small>
                    {[
                      version.note,
                      version.base_prompt ? "prompt personalizado" : "prompt padrão",
                      version.chat_model,
                      version.reasoning_effort ? `raciocínio ${EFFORT_LABELS[version.reasoning_effort] ?? version.reasoning_effort}` : null,
                      version.created_by_email,
                    ].filter(Boolean).join(" · ")}
                  </small>
                </div>
                {index > 0 ? (
                  <button className="secondary-button" onClick={() => { setForm({ ...formFrom(data, version), note: "Retorno a uma versão anterior" }); window.scrollTo({ top: 0, behavior: "smooth" }); }} type="button">
                    Carregar
                  </button>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}

type TenantAgent = { extra_instructions: string; updated_by_email: string | null; updated_at: string | null; preview: string };

/** Instructions that only this client's agent receives, plus the full prompt as it is sent. */
export function TenantAgentInstructions({ tenantId, token }: { tenantId: string; token: string }) {
  const [data, setData] = useState<TenantAgent | null>(null);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setFeedback(null);
    request<TenantAgent>(`/platform/tenants/${tenantId}/agent`, {}, token)
      .then((value) => {
        setData(value);
        setText(value.extra_instructions);
      })
      .catch((reason) => setFeedback(reason instanceof Error ? reason.message : "Falha ao carregar."));
  }, [tenantId, token]);

  async function save() {
    setSaving(true);
    setFeedback(null);
    try {
      const value = await request<TenantAgent>(
        `/platform/tenants/${tenantId}/agent`,
        { method: "PUT", body: JSON.stringify({ extra_instructions: text }) },
        token,
      );
      setData(value);
      setText(value.extra_instructions);
      setFeedback("Instruções salvas.");
    } catch (reason) {
      setFeedback(reason instanceof Error ? reason.message : "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="settings-subsection">
      <h3>Agente de IA deste cliente</h3>
      <label>
        <span>Instruções extras <span className="optional">(só este cliente; ele não vê este campo)</span></span>
        <textarea
          maxLength={4000}
          onChange={(event) => setText(event.target.value)}
          placeholder="Ex.: Esta imobiliária só trabalha com locação. Nunca ofereça imóveis à venda."
          rows={4}
          value={text}
        />
      </label>
      <div className="agent-prompt-actions">
        <small className="field-hint">
          {data?.updated_at ? `Última alteração em ${new Date(data.updated_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })} por ${data.updated_by_email}` : ""}
          {feedback ? ` ${feedback}` : ""}
        </small>
        <button className="primary-button" disabled={saving || !data || text.trim() === data.extra_instructions} onClick={() => void save()} type="button">
          {saving ? "Salvando..." : "Salvar instruções"}
        </button>
      </div>
      {data ? (
        <details className="agent-preview-full">
          <summary>Ver o prompt completo deste cliente</summary>
          <pre>{data.preview}</pre>
          <small className="field-hint">Numa conversa real, entram também os dados do lead e os trechos da base de conhecimento.</small>
        </details>
      ) : null}
    </div>
  );
}

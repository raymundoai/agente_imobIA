import { useEffect, useRef, useState } from "react";
import { request } from "../../api/client";
import type { KnowledgeDocument } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable";
import { KNOWLEDGE_ACCEPT, validateKnowledgeFile } from "../../lib/settingsValidation";

export function KnowledgeSettingsPanel({ canManage }: { canManage: boolean }) {
  const { token } = useAuth();
  const [items, setItems] = useState<KnowledgeDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadDocuments() {
    setListLoading(true);
    try {
      setItems(await request<KnowledgeDocument[]>("/knowledge/documents", {}, token));
      setListError(null);
    } catch (error) {
      setListError(error instanceof Error ? error.message : "Falha ao carregar arquivos.");
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    if (canManage) void loadDocuments();
    else setListLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, canManage]);

  function selectFile(nextFile: File | null) {
    if (!nextFile) {
      setFile(null);
      return;
    }
    const error = validateKnowledgeFile(nextFile);
    if (error) {
      setFile(null);
      setMessage(error);
      setMessageKind("error");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    setFile(nextFile);
    setMessage(null);
  }

  async function uploadDocument() {
    if (!file) {
      setMessage("Selecione um arquivo.");
      setMessageKind("error");
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const contentBase64 = await fileToBase64(file);
      await request<KnowledgeDocument>(
        "/knowledge/documents",
        {
          method: "POST",
          body: JSON.stringify({
            filename: file.name,
            file_type: file.name.split(".").pop() || file.type || "txt",
            content_base64: contentBase64,
          }),
        },
        token,
      );
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setMessage("Arquivo processado e adicionado à base de conhecimento.");
      setMessageKind("success");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao enviar arquivo.");
      setMessageKind("error");
      await loadDocuments();
    } finally {
      setLoading(false);
    }
  }

  async function deleteDocument(id: string) {
    if (!window.confirm("Remover este arquivo da base de conhecimento?")) return;
    setMessage(null);
    try {
      await request<void>(`/knowledge/documents/${id}`, { method: "DELETE" }, token);
      setMessage("Arquivo removido.");
      setMessageKind("success");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao remover arquivo.");
      setMessageKind("error");
    }
  }

  async function reindexDocument(id: string) {
    if (!file) {
      setMessage("Selecione novamente o arquivo que deseja reprocessar.");
      setMessageKind("error");
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const contentBase64 = await fileToBase64(file);
      await request<KnowledgeDocument>(
        `/knowledge/documents/${id}/reindex`,
        { method: "POST", body: JSON.stringify({ content_base64: contentBase64 }) },
        token,
      );
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setMessage("Arquivo reprocessado com sucesso.");
      setMessageKind("success");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao reprocessar arquivo.");
      setMessageKind("error");
      await loadDocuments();
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="settings-panel-card">
      <div className="settings-panel-header">
        <div>
          <h2>Base de conhecimento</h2>
          <p>Arquivos que ajudam a IA a responder sobre regras, bairros, imóveis e processos.</p>
        </div>
        <Badge variant="muted">IA</Badge>
      </div>

      {!canManage ? (
        <div className="settings-readonly-note">Somente administradores podem gerenciar a base de conhecimento da IA.</div>
      ) : <>

      <div className="form-grid">
        <label className="form-span-2">
          Arquivo
          <input accept={KNOWLEDGE_ACCEPT} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} ref={fileInputRef} type="file" />
          <small>TXT, Markdown, PDF ou DOCX, com até 10 MB.</small>
        </label>
      </div>

      <div className="settings-actions">
        {message ? <span className={`settings-feedback ${messageKind}`} role={messageKind === "error" ? "alert" : "status"} aria-live="polite">{message}</span> : null}
        <button disabled={loading || !file} onClick={uploadDocument} type="button">
          {loading ? "Enviando..." : "Enviar arquivo"}
        </button>
      </div>

      {listLoading ? <div className="empty-state" aria-live="polite">Carregando arquivos...</div> : null}
      {listError ? <div className="error-box" role="alert">{listError}</div> : null}
      {!listLoading && !listError ? <DataTable
        data={items}
        empty="Nenhum arquivo enviado."
        columns={[
          { key: "filename", label: "Arquivo", render: (item) => item.filename },
          { key: "type", label: "Tipo", render: (item) => item.file_type },
          {
            key: "status",
            label: "Status",
            render: (item) => (
              <Badge variant={item.status === "indexed" ? "success" : "muted"}>
                {statusLabels[item.status] ?? item.status}
              </Badge>
            ),
          },
          { key: "error", label: "Observação", render: (item) => item.error ?? "-" },
          {
            key: "actions",
            label: "",
            render: (item) => (
              <div className="table-actions">
              <button className="link-button" onClick={() => void deleteDocument(item.id)} type="button">
                Remover
              </button>
              {item.status === "error" ? (
                <button className="link-button" disabled={loading} onClick={() => void reindexDocument(item.id)} type="button">
                  Tentar novamente
                </button>
              ) : null}
              </div>
            ),
          },
        ]}
      /> : null}
      </>}
    </Card>
  );
}

const statusLabels: Record<string, string> = {
  pending: "Na fila",
  indexing: "Processando",
  indexed: "Pronto",
  error: "Erro",
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

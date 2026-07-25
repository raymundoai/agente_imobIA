import { useEffect, useState } from "react";
import { request } from "../api/client";
import type { KnowledgeDocument } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { DataTable } from "../components/DataTable";

export function KnowledgePage() {
  const { token } = useAuth();
  const [items, setItems] = useState<KnowledgeDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadDocuments() {
    setItems(await request<KnowledgeDocument[]>("/knowledge/documents", {}, token));
  }

  useEffect(() => {
    void loadDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function uploadDocument() {
    if (!file) {
      setMessage("Selecione um arquivo.");
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
      setMessage("Documento enviado para indexação.");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao enviar documento.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteDocument(id: string) {
    setMessage(null);
    try {
      await request<void>(`/knowledge/documents/${id}`, { method: "DELETE" }, token);
      setMessage("Documento removido.");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao remover documento.");
    }
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <span className="eyebrow">RAG</span>
        <h1>Base de conhecimento</h1>
        <p>Documentos indexados e usados pelo agente IA com filtro por tenant.</p>
      </header>
      <article className="card settings-panel-card">
        <div className="settings-panel-header">
          <div>
            <h2>Enviar documento</h2>
            <p>Upload MVP em base64; backend executa ingestão via job in-process.</p>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span-2">
            Arquivo
            <input
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              type="file"
            />
          </label>
        </div>
        <div className="settings-actions">
          {message ? <span>{message}</span> : null}
          <button disabled={loading || !file} onClick={uploadDocument} type="button">
            {loading ? "Enviando..." : "Enviar documento"}
          </button>
        </div>
      </article>
      <DataTable
        data={items}
        empty="Nenhum documento indexado."
        columns={[
          { key: "filename", label: "Arquivo", render: (item) => item.filename },
          { key: "type", label: "Tipo", render: (item) => item.file_type },
          {
            key: "status",
            label: "Status",
            render: (item) => (
              <Badge variant={item.status === "indexed" ? "success" : "muted"}>{item.status}</Badge>
            ),
          },
          { key: "error", label: "Erro", render: (item) => item.error ?? "—" },
          {
            key: "actions",
            label: "",
            render: (item) => (
              <button className="link-button" onClick={() => void deleteDocument(item.id)} type="button">
                Remover
              </button>
            ),
          },
        ]}
      />
    </section>
  );
}

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

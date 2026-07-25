import { useEffect, useState } from "react";
import { request } from "../../api/client";
import type { KnowledgeDocument } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable";

export function KnowledgeSettingsPanel() {
  const { token } = useAuth();
  const [items, setItems] = useState<KnowledgeDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadDocuments() {
    setItems(await request<KnowledgeDocument[]>("/knowledge/documents", {}, token));
  }

  useEffect(() => {
    void loadDocuments().catch(() => setItems([]));
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
      setMessage("Arquivo enviado para a base de conhecimento.");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao enviar arquivo.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteDocument(id: string) {
    setMessage(null);
    try {
      await request<void>(`/knowledge/documents/${id}`, { method: "DELETE" }, token);
      setMessage("Arquivo removido.");
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao remover arquivo.");
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

      <div className="form-grid">
        <label className="form-span-2">
          Arquivo
          <input onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" />
        </label>
      </div>

      <div className="settings-actions">
        {message ? <span>{message}</span> : null}
        <button disabled={loading || !file} onClick={uploadDocument} type="button">
          {loading ? "Enviando..." : "Enviar arquivo"}
        </button>
      </div>

      <DataTable
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
              <button className="link-button" onClick={() => void deleteDocument(item.id)} type="button">
                Remover
              </button>
            ),
          },
        ]}
      />
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

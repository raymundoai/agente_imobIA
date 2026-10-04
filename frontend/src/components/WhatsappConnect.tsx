import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { request } from "../api/client";
import type { EvolutionWhatsappConnection } from "../api/types";
import { formatPhone } from "../lib/format";
import { Modal } from "./Modal";

/** Connection state of the agency's WhatsApp, shared by Settings and the setup wizard. */
export function useWhatsappConnection(token: string | null) {
  const [connection, setConnection] = useState<EvolutionWhatsappConnection | null>(null);
  const [checking, setChecking] = useState(true);
  const [statusError, setStatusError] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      setConnection(await request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/status", {}, token));
      setStatusError(false);
    } catch {
      setStatusError(true);
    } finally {
      setChecking(false);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // While the QR code is on screen, check every few seconds so the dialog confirms on its own.
  useEffect(() => {
    if (!modalOpen || connection?.status === "connected") return undefined;
    const handle = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(handle);
  }, [modalOpen, connection?.status, refresh]);

  async function connect() {
    if (!token) return;
    setModalOpen(true);
    if (connection?.status === "connected") return;
    setGenerating(true);
    setError(null);
    try {
      setConnection(await request<EvolutionWhatsappConnection>("/integrations/evolution/whatsapp/connect", { method: "POST" }, token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível gerar o QR Code.");
    } finally {
      setGenerating(false);
    }
  }

  return {
    connection,
    connected: connection?.status === "connected",
    checking,
    statusError,
    modalOpen,
    generating,
    error,
    connect,
    close: () => setModalOpen(false),
    refresh,
  };
}

export function WhatsappConnectModal({ whatsapp }: { whatsapp: ReturnType<typeof useWhatsappConnection> }) {
  const { connection, connected, generating, error } = whatsapp;
  return (
    <Modal
      description={connected ? undefined : "Use o celular com o número da imobiliária."}
      footer={
        connected ? (
          <button className="primary-button" onClick={whatsapp.close} type="button">Concluir</button>
        ) : (
          <button className="secondary-button" onClick={whatsapp.close} type="button">Fechar</button>
        )
      }
      onClose={whatsapp.close}
      title={connected ? "WhatsApp conectado" : "Conectar WhatsApp"}
    >
      {connected ? (
        <div className="qr-state qr-success">
          <CheckCircle2 size={40} />
          <strong>{connection?.connected_phone ? formatPhone(connection.connected_phone) : connection?.connected_name || "Número conectado"}</strong>
          <span>As mensagens desse número já chegam em Conversas e o agente de IA começa a responder.</span>
        </div>
      ) : (
        <div className="qr-layout">
          <ol className="qr-steps">
            <li>Abra o WhatsApp no celular.</li>
            <li>Toque em <strong>Aparelhos conectados</strong> e depois em <strong>Conectar aparelho</strong>.</li>
            <li>Aponte a câmera para o código ao lado.</li>
          </ol>
          <div className="qr-frame">
            {generating ? (
              <div className="qr-state"><Loader2 className="spin" size={26} /><span>Gerando código…</span></div>
            ) : error ? (
              <div className="qr-state">
                <strong>Não foi possível gerar o código.</strong>
                <span>{error}</span>
                <button className="secondary-button" onClick={() => void whatsapp.connect()} type="button">Tentar de novo</button>
              </div>
            ) : connection?.qrcode?.startsWith("data:image") ? (
              <img alt="QR Code para conectar o WhatsApp" src={connection.qrcode} />
            ) : connection?.qrcode ? (
              <div className="qr-state"><strong>Código de pareamento</strong><code>{connection.qrcode}</code></div>
            ) : (
              <div className="qr-state"><Loader2 className="spin" size={26} /><span>Aguardando o código…</span></div>
            )}
          </div>
          {connection?.pairing_code ? (
            <p className="qr-pairing">Prefere digitar? Use o código <code>{connection.pairing_code}</code></p>
          ) : null}
          <p className="qr-waiting" aria-live="polite">
            <Loader2 className="spin" size={14} /> Assim que você ler o código, esta janela confirma a conexão.
          </p>
        </div>
      )}
    </Modal>
  );
}

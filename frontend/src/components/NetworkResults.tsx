import { useEffect, useState } from "react";
import { Check, Handshake, Home, LoaderCircle, Send, Share2 } from "lucide-react";
import { ApiError, request, requestBlob } from "../api/client";
import type { NetworkListing, Partnership } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { formatCurrency } from "../lib/format";

function openSettingsTab(tab: string) {
  window.history.pushState({}, "", `/configuracoes?aba=${tab}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/** Shared listings of other ImmobIA agencies that fit the selected demand. */
export function NetworkResults({ demandId, canRequest }: { demandId: string; canRequest: boolean }) {
  const { token } = useAuth();
  const [items, setItems] = useState<NetworkListing[] | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "upsell" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setItems(null);
    request<NetworkListing[]>(`/network/search?demand_id=${demandId}`, {}, token)
      .then((result) => {
        if (cancelled) return;
        setItems(result);
        setState("ready");
      })
      .catch((reason) => {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 402) {
          setState("upsell");
          return;
        }
        setError(reason instanceof Error ? reason.message : "Não foi possível consultar a rede.");
        setState("error");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demandId]);

  function updatePartnership(listingId: string, partnership: NetworkListing["partnership"]) {
    setItems((current) => current?.map((item) => (item.id === listingId ? { ...item, partnership } : item)) ?? null);
  }

  return (
    <section className="search-stage network-stage">
      <div className="section-heading">
        <div>
          <span className="eyebrow"><Share2 size={13} /> Rede ImmobIA</span>
        </div>
        <p>Imóveis compartilhados por outras imobiliárias para fazer parceria.</p>
      </div>
      {state === "loading" ? <div className="panel-card empty-state"><LoaderCircle className="spin" size={20} /> Consultando a rede…</div> : null}
      {state === "error" ? <div className="error-box">{error}</div> : null}
      {state === "upsell" ? (
        <div className="panel-card network-upsell-card">
          <Handshake size={22} />
          <div>
            <strong>Encontre imóveis de outras imobiliárias para seus clientes</strong>
            <span>A Rede ImmobIA faz parte dos planos pagos.</span>
          </div>
          <button className="secondary-button" onClick={() => openSettingsTab("billing")} type="button">Ver planos</button>
        </div>
      ) : null}
      {state === "ready" && items && items.length === 0 ? (
        <div className="panel-card empty-state">Nenhum imóvel da rede atende a esta demanda no momento.</div>
      ) : null}
      {state === "ready" && items && items.length ? (
        <div className="external-result-grid">
          {items.map((item) => (
            <NetworkResultCard
              canRequest={canRequest}
              demandId={demandId}
              item={item}
              key={item.id}
              onRequested={(partnership) => updatePartnership(item.id, partnership)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function NetworkResultCard({
  item,
  demandId,
  canRequest,
  onRequested,
}: {
  item: NetworkListing;
  demandId: string;
  canRequest: boolean;
  onRequested: (partnership: NetworkListing["partnership"]) => void;
}) {
  const { token } = useAuth();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const imageId = item.image_ids[0];
    if (!imageId) return;
    let objectUrl: string | null = null;
    requestBlob(`/network/properties/${item.id}/images/${imageId}/content`, token)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch(() => setImageUrl(null));
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id]);

  async function send() {
    setSending(true);
    setError(null);
    try {
      const created = await request<Partnership>(
        "/network/partnerships",
        { method: "POST", body: JSON.stringify({ property_id: item.id, demand_id: demandId, message: message.trim() || null }) },
        token,
      );
      onRequested({ id: created.id, status: created.status });
      setComposing(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível enviar o pedido.");
    } finally {
      setSending(false);
    }
  }

  const status = item.partnership?.status;

  return (
    <article className="panel-card external-result-card network-result-card">
      {imageUrl ? <img alt={item.title} loading="lazy" src={imageUrl} /> : <div className="external-result-placeholder"><Home size={24} /></div>}
      <div className="external-result-content">
        <div className="external-result-source">
          <span>{item.agency_name}</span>
          <small>{item.partner_commission_percent}% da comissão para o parceiro</small>
        </div>
        <h3>{item.title}</h3>
        <strong className="network-result-price">{formatCurrency(item.price)}</strong>
        <p>{[item.neighborhood, item.city].filter(Boolean).join(" · ")}</p>
        <div className="external-result-features">
          {item.area ? <span>{item.area} m²</span> : null}
          {item.bedrooms != null ? <span>{item.bedrooms} quartos</span> : null}
          {item.suites ? <span>{item.suites} suítes</span> : null}
          {item.parking_spaces != null ? <span>{item.parking_spaces} vagas</span> : null}
        </div>
        <div className="external-result-scores">
          <span>{item.fit_score}% compatível</span>
        </div>
        {item.matched.length || item.tradeoffs.length ? (
          <div className="external-result-explanation">
            {item.matched.length ? <small>Atende: {item.matched.slice(0, 3).join(", ")}</small> : null}
            {item.tradeoffs.length ? <small className="has-tradeoffs">Pontos de atenção: {item.tradeoffs.slice(0, 3).join(", ")}</small> : null}
          </div>
        ) : null}

        {status === "accepted" ? (
          <button className="network-status accepted" onClick={() => openSettingsTab("network")} type="button">
            <Check size={14} /> Parceria aceita · ver contato
          </button>
        ) : status === "pending" ? (
          <span className="network-status">Pedido enviado · aguardando resposta</span>
        ) : composing ? (
          <div className="network-request">
            <textarea
              maxLength={1000}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Opcional: conte sobre o cliente (ex.: aprovado no financiamento, quer visitar esta semana)."
              rows={3}
              value={message}
            />
            {error ? (
              <div className="error-box">
                {error}
                {error.includes("termo") ? (
                  <button className="link-button" onClick={() => openSettingsTab("network")} type="button">Abrir Rede ImmobIA</button>
                ) : null}
              </div>
            ) : null}
            <div className="network-request-actions">
              <button className="link-button" disabled={sending} onClick={() => setComposing(false)} type="button">Cancelar</button>
              <button className="primary-button" disabled={sending} onClick={() => void send()} type="button">
                {sending ? <LoaderCircle className="spin" size={14} /> : <Send size={14} />}
                Enviar pedido
              </button>
            </div>
          </div>
        ) : (
          <div className="external-result-actions">
            <button className="primary-button" disabled={!canRequest} onClick={() => setComposing(true)} type="button">
              <Handshake size={15} /> Solicitar parceria
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

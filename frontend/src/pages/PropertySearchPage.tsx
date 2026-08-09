import { ExternalLink, Plus, RefreshCw, Search, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { request } from "../api/client";
import type { CaptureMission, FederatedSearchRun, LeadDemand, Property } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { DemandModal } from "../components/DemandModal";
import { searchPricePresentation } from "../lib/propertySearchPrice";

const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function money(value: string | null) {
  return value == null ? "Preço não informado" : currency.format(Number(value));
}

function purposeLabel(value: string | null) {
  return value === "rent" ? "Aluguel" : "Compra";
}

const terminalSearchStatuses = new Set(["partial", "completed", "failed", "cancelled"]);

function sourceStatusLabel(status: string) {
  return {
    queued: "Na fila",
    running: "Pesquisando",
    completed: "Concluído",
    failed: "Falhou",
    blocked: "Bloqueado",
  }[status] ?? status;
}

function ExternalResultPrice({
  item,
  purpose,
}: {
  item: FederatedSearchRun["results"][number];
  purpose: string | null;
}) {
  const prices = searchPricePresentation(purpose, item);
  return (
    <div className="external-result-price">
      <small>{prices.primaryLabel}</small>
      <strong>{prices.primary ? money(prices.primary) : "Valor não informado"}</strong>
      {prices.alternative ? (
        <span>
          {prices.alternativeLabel} {money(prices.alternative)}
        </span>
      ) : null}
    </div>
  );
}

export function PropertySearchPage() {
  const { token } = useAuth();
  const [demands, setDemands] = useState<LeadDemand[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mission, setMission] = useState<CaptureMission | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [savingCapture, setSavingCapture] = useState(false);
  const [searchRun, setSearchRun] = useState<FederatedSearchRun | null>(null);
  const [startingSearch, setStartingSearch] = useState(false);
  const [captureForm, setCaptureForm] = useState({ source: "olx", source_url: "", title: "", price: "", neighborhood: "" });

  const loadMission = useCallback(async (demandId: string) => {
    setMessage(null);
    setMission(await request<CaptureMission>(`/capture/missions/${demandId}`, {}, token));
  }, [token]);

  const loadDemands = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<LeadDemand[]>("/leads/demands?limit=100", {}, token);
      setDemands(data);
      const initial = selectedId ?? data[0]?.id ?? null;
      setSelectedId(initial);
      if (initial) await loadMission(initial);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível carregar o buscador.");
    } finally {
      setLoading(false);
    }
  }, [loadMission, selectedId, token]);

  useEffect(() => { void loadDemands(); }, []); // load only on entry

  async function selectDemand(id: string) {
    setSelectedId(id);
    setSearchRun(null);
    setLoading(true);
    try { await loadMission(id); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Falha ao abrir a busca."); }
    finally { setLoading(false); }
  }

  const pollSearchRun = useCallback(async (runId: string) => {
    try {
      setSearchRun(await request<FederatedSearchRun>(`/capture/search-runs/${runId}`, {}, token));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível atualizar a busca.");
    }
  }, [token]);

  useEffect(() => {
    if (!searchRun || terminalSearchStatuses.has(searchRun.status)) return;
    const timeout = window.setTimeout(() => void pollSearchRun(searchRun.id), 1500);
    return () => window.clearTimeout(timeout);
  }, [pollSearchRun, searchRun]);

  async function startFederatedSearch() {
    if (!selectedId) return;
    setStartingSearch(true);
    setMessage(null);
    try {
      const run = await request<FederatedSearchRun>("/capture/search-runs", {
        method: "POST",
        body: JSON.stringify({ demand_id: selectedId }),
      }, token);
      setSearchRun(run);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível iniciar a busca.");
    } finally {
      setStartingSearch(false);
    }
  }

  async function saveCapturedProperty() {
    if (!selectedId || !mission) return;
    setSavingCapture(true);
    setMessage(null);
    try {
      await request<Property>("/capture/properties", {
        method: "POST",
        body: JSON.stringify({
          demand_id: selectedId,
          source: captureForm.source,
          source_url: captureForm.source_url,
          title: captureForm.title,
          city: mission.demand.city,
          neighborhood: captureForm.neighborhood || null,
          price: captureForm.price || null,
          purpose: mission.demand.purpose,
          property_type: mission.demand.property_type,
          sale_price: mission.demand.purpose === "buy" ? captureForm.price || null : null,
          rent_price: mission.demand.purpose === "rent" ? captureForm.price || null : null,
        }),
      }, token);
      setCaptureOpen(false);
      setCaptureForm({ source: "olx", source_url: "", title: "", price: "", neighborhood: "" });
      setMessage("Anúncio salvo e vinculado à demanda.");
      await loadMission(selectedId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível salvar o anúncio.");
    } finally { setSavingCapture(false); }
  }

  return (
    <section className="property-search-page">
      <header className="page-header property-search-header">
        <div>
          <span className="eyebrow">Captação externa</span>
          <h1>Buscador de imóveis</h1>
          <p>Pesquise imóveis para uma demanda e mantenha a origem do anúncio sempre visível.</p>
        </div>
        <button className="primary-button" onClick={() => setModalOpen(true)} type="button"><Plus size={17} /> Nova demanda</button>
      </header>

      <div className="capture-notice"><Sparkles size={18} /><span>Imóveis captados ficam disponíveis ao corretor. A IA continua oferecendo somente imóveis da carteira própria.</span></div>
      {message ? <div className="inline-feedback">{message}</div> : null}

      <div className="property-search-layout">
        <aside className="demand-list panel-card">
          <div className="panel-title"><div><span className="eyebrow">Demandas</span><h2>Clientes em busca</h2></div><button aria-label="Atualizar" className="icon-button" onClick={() => void loadDemands()} type="button"><RefreshCw size={16} /></button></div>
          {demands.length === 0 && !loading ? <div className="empty-state"><Search size={24} /><p>Cadastre uma demanda para começar.</p></div> : null}
          {demands.map((demand) => (
            <button className={`demand-list-item${selectedId === demand.id ? " active" : ""}`} key={demand.id} onClick={() => void selectDemand(demand.id)} type="button">
              <strong>{demand.lead_name}</strong><span>{purposeLabel(demand.purpose)} · {demand.property_type || "Imóvel"}</span><small>{demand.city || "Cidade não informada"}{demand.neighborhoods.length ? ` · ${demand.neighborhoods.join(", ")}` : ""}</small>
            </button>
          ))}
        </aside>

        <main className="capture-workspace">
          {loading ? <div className="panel-card empty-state large"><RefreshCw className="spin" size={26} /><p>Preparando a busca…</p></div> : null}
          {!loading && mission ? <>
            <section className="panel-card mission-summary"><div><span className="eyebrow">Busca ativa</span><h2>{mission.demand.lead_name}</h2><p>{purposeLabel(mission.demand.purpose)} de {mission.demand.property_type || "imóvel"} em {mission.demand.city || "cidade não informada"}</p></div><div className="mission-search-actions"><div className="mission-chips">{mission.demand.neighborhoods.map((item) => <span key={item}>{item}</span>)}{mission.demand.price_max ? <span>até {money(mission.demand.price_max)}</span> : null}{mission.demand.bedrooms ? <span>{mission.demand.bedrooms}+ quartos</span> : null}</div><button className="primary-button" disabled={startingSearch || Boolean(searchRun && !terminalSearchStatuses.has(searchRun.status))} onClick={() => void startFederatedSearch()} type="button"><Search size={16} />{startingSearch ? "Iniciando…" : searchRun ? "Buscar novamente" : "Buscar imóveis"}</button></div></section>
            <section><div className="section-heading"><div><span className="eyebrow">Busca federada</span><h2>Resultados dos portais</h2></div><p>Os anúncios são pesquisados e comparados dentro do ImobIA.</p></div>{searchRun ? <><div className="federated-progress panel-card"><div><strong>{searchRun.completed_source_count} de {searchRun.source_count} fontes concluídas</strong><span>{searchRun.result_count} imóveis compatíveis</span></div><div className="federated-source-statuses">{searchRun.sources.map((source) => <span className={`source-status ${source.status}`} key={source.source_id}><i />{source.source_name}: {sourceStatusLabel(source.status)}{source.discovered_count ? ` · ${source.discovered_count}` : ""}</span>)}</div></div>{searchRun.results.length ? <div className="external-result-grid">{searchRun.results.map((item) => <article className="panel-card external-result-card" key={item.id}>{item.primary_image_url ? <img alt={item.title} loading="lazy" src={item.primary_image_url} /> : <div className="external-result-placeholder"><Search size={24} /></div>}<div className="external-result-content"><div className="external-result-source"><span>{item.source_name}</span><small>Atualizado agora</small></div><h3>{item.title}</h3><ExternalResultPrice item={item} purpose={mission.demand.purpose} /><p>{[item.neighborhood, item.city, item.state].filter(Boolean).join(" · ")}</p><div className="external-result-features">{item.area ? <span>{item.area} m²</span> : null}{item.bedrooms != null ? <span>{item.bedrooms} quartos</span> : null}{item.parking_spaces != null ? <span>{item.parking_spaces} vagas</span> : null}</div><div className="external-result-scores"><span>{item.fit_score}% compatível</span><small>Confiança {item.confidence_score}%</small></div><a href={item.canonical_url} rel="noreferrer" target="_blank">Ver anúncio original <ExternalLink size={14} /></a></div></article>)}</div> : <div className="panel-card empty-state">{terminalSearchStatuses.has(searchRun.status) ? <Search size={24} /> : <RefreshCw className="spin" size={24} />}<p>{terminalSearchStatuses.has(searchRun.status) ? "Nenhum resultado compatível nesta execução." : "Pesquisando nos portais e preparando os primeiros resultados…"}</p></div>}</> : <div className="panel-card empty-state"><Search size={24} /><p>Revise os critérios e inicie a busca para consultar os portais.</p></div>}</section>
            <section><div className="section-heading"><div><span className="eyebrow">Resultados salvos</span><h2>Imóveis captados</h2></div><div className="section-actions"><p>{mission.existing_matches.length} vinculados a esta demanda</p><button className="secondary-button" onClick={() => setCaptureOpen(true)} type="button"><Plus size={15} /> Salvar anúncio</button></div></div>{mission.existing_matches.length ? <div className="captured-results">{mission.existing_matches.map((item) => <article className="panel-card captured-result" key={item.id}><div><strong>{item.title}</strong><span>{money(item.price)}</span></div><div className="match-score">{Math.round(item.score)}% compatível</div>{item.tradeoffs.length ? <small>Pontos de atenção: {item.tradeoffs.join(", ")}</small> : <small className="all-filters">Compatível com os filtros principais</small>}{item.source_url ? <a href={item.source_url} rel="noreferrer" target="_blank">Ver anúncio original <ExternalLink size={14} /></a> : null}</article>)}</div> : <div className="panel-card empty-state"><Search size={24} /><p>Nenhum imóvel externo captado para esta demanda.</p></div>}</section>
          </> : null}
        </main>
      </div>
      <DemandModal isOpen={modalOpen} onClose={() => setModalOpen(false)} onCreated={(demand) => { setDemands((current) => [demand, ...current]); setSelectedId(demand.id); void loadMission(demand.id); }} />
      {captureOpen && mission ? <div className="modal-backdrop" role="presentation"><section aria-modal="true" className="demand-modal capture-modal" role="dialog"><header className="modal-header"><div><span className="eyebrow">Captação manual</span><h2>Salvar anúncio externo</h2><p>Cole o anúncio encontrado para vinculá-lo a {mission.demand.lead_name}.</p></div><button aria-label="Fechar" className="icon-button" onClick={() => setCaptureOpen(false)} type="button"><X size={18} /></button></header><div className="form-grid"><label>Portal *<select value={captureForm.source} onChange={(event) => setCaptureForm((current) => ({ ...current, source: event.target.value }))}><option value="olx">OLX</option><option value="zap">ZAP Imóveis</option><option value="vivareal">Viva Real</option><option value="lello">Lello</option><option value="outro">Outro</option></select></label><label>URL do anúncio *<input required type="url" value={captureForm.source_url} onChange={(event) => setCaptureForm((current) => ({ ...current, source_url: event.target.value }))} /></label><label className="form-span-2">Título *<input required value={captureForm.title} onChange={(event) => setCaptureForm((current) => ({ ...current, title: event.target.value }))} /></label><label>Bairro<input value={captureForm.neighborhood} onChange={(event) => setCaptureForm((current) => ({ ...current, neighborhood: event.target.value }))} /></label><label>Preço<input min="0" step="0.01" type="number" value={captureForm.price} onChange={(event) => setCaptureForm((current) => ({ ...current, price: event.target.value }))} /></label></div><footer className="modal-actions"><button className="secondary-button" onClick={() => setCaptureOpen(false)} type="button">Cancelar</button><button className="primary-button" disabled={savingCapture || !captureForm.source_url.trim() || !captureForm.title.trim()} onClick={() => void saveCapturedProperty()} type="button">{savingCapture ? "Salvando…" : "Salvar anúncio"}</button></footer></section></div> : null}
    </section>
  );
}

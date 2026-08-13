import {
  Bookmark,
  Check,
  ExternalLink,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  StopCircle,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type {
  CaptureMission,
  FederatedSearchHistory,
  FederatedSearchRun,
  FederatedSourceDescriptor,
  LeadDemand,
  Property,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { getTokenClaims } from "../auth/tokenClaims";
import { DemandModal } from "../components/DemandModal";
import {
  compatibilityCounts,
  matchesCompatibilityFilter,
  type CompatibilityFilter,
} from "../lib/propertySearchFit";
import { searchPricePresentation } from "../lib/propertySearchPrice";

const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function money(value: string | null) {
  return value == null ? "Preço não informado" : currency.format(Number(value));
}

function purposeLabel(value: string | null) {
  return value === "rent" ? "Aluguel" : "Compra";
}

function updatedLabel(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Atualização não informada";
  return `Atualizado em ${parsed.toLocaleDateString("pt-BR")} às ${parsed.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

function searchRunTimestamp(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "data não informada";
  return parsed.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const terminalSearchStatuses = new Set(["partial", "completed", "failed", "cancelled"]);
const resultPageSize = 24;

function sourceStatusLabel(status: string) {
  return {
    queued: "Na fila",
    running: "Pesquisando",
    completed: "Concluído",
    failed: "Falhou",
    blocked: "Bloqueado",
    cancelled: "Cancelado",
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

function ExternalResultImage({ src, title }: { src: string | null; title: string }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [src]);

  if (!src || failed) {
    return <div className="external-result-placeholder"><Search size={24} /></div>;
  }
  return <img alt={title} loading="lazy" onError={() => setFailed(true)} src={src} />;
}

export function PropertySearchPage() {
  const { token } = useAuth();
  const claims = getTokenClaims(token);
  const canSearch = claims?.role !== "atendente";
  const initialLoadStarted = useRef(false);
  const [demands, setDemands] = useState<LeadDemand[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mission, setMission] = useState<CaptureMission | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingDemand, setEditingDemand] = useState<LeadDemand | null>(null);
  const [refreshKind, setRefreshKind] = useState<"standard" | "ai" | null>(null);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [savingCapture, setSavingCapture] = useState(false);
  const [standardSearchRun, setStandardSearchRun] = useState<FederatedSearchRun | null>(null);
  const [aiSearchRun, setAiSearchRun] = useState<FederatedSearchRun | null>(null);
  const [startingSearch, setStartingSearch] = useState(false);
  const [startingAiSearch, setStartingAiSearch] = useState(false);
  const [aiDiscoveryAvailable, setAiDiscoveryAvailable] = useState(false);
  const [savingResultIds, setSavingResultIds] = useState<Set<string>>(() => new Set());
  const [removingSavedIds, setRemovingSavedIds] = useState<Set<string>>(() => new Set());
  const [demandToDelete, setDemandToDelete] = useState<LeadDemand | null>(null);
  const [deletingDemand, setDeletingDemand] = useState(false);
  const [compatibilityFilter, setCompatibilityFilter] = useState<CompatibilityFilter>("all");
  const [resultDisplayLimit, setResultDisplayLimit] = useState(resultPageSize);
  const [captureForm, setCaptureForm] = useState({ source: "olx", source_url: "", title: "", price: "", neighborhood: "" });

  const hydrateRunResults = useCallback(async (run: FederatedSearchRun) => {
    if (run.result_count <= run.results.length && !run.results_has_more) return run;
    const results: FederatedSearchRun["results"] = [];
    for (let offset = 0; offset < run.result_count; offset += 100) {
      const page = await request<FederatedSearchRun["results"]>(
        `/capture/search-runs/${run.id}/results?limit=100&offset=${offset}`,
        {},
        token,
      );
      results.push(...page);
      if (page.length < 100) break;
    }
    return { ...run, results, results_has_more: false };
  }, [token]);

  const loadMission = useCallback(async (demandId: string, restoreSearches = true) => {
    setMessage(null);
    if (!restoreSearches) {
      setMission(await request<CaptureMission>(`/capture/missions/${demandId}`, {}, token));
      return;
    }
    const [missionData, history] = await Promise.all([
      request<CaptureMission>(`/capture/missions/${demandId}`, {}, token),
      request<FederatedSearchHistory>(
        `/capture/demands/${demandId}/search-history`,
        {},
        token,
      ),
    ]);
    setMission(missionData);
    const [standard, ai] = await Promise.all([
      history.standard ? hydrateRunResults(history.standard) : null,
      history.ai ? hydrateRunResults(history.ai) : null,
    ]);
    setStandardSearchRun(standard);
    setAiSearchRun(ai);
    setCompatibilityFilter("all");
    setResultDisplayLimit(resultPageSize);
  }, [hydrateRunResults, token]);

  const loadDemands = useCallback(async () => {
    setLoading(true);
    try {
      const [data, sources] = await Promise.all([
        request<LeadDemand[]>("/leads/demands?limit=100", {}, token),
        request<FederatedSourceDescriptor[]>("/capture/sources", {}, token),
      ]);
      const searchableDemands = data.filter((demand) => demand.status !== "closed");
      setDemands(searchableDemands);
      setAiDiscoveryAvailable(sources.some((source) => source.id === "web_discovery"));
      const initial = selectedId && searchableDemands.some((item) => item.id === selectedId)
        ? selectedId
        : searchableDemands[0]?.id ?? null;
      setSelectedId(initial);
      if (initial) await loadMission(initial);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível carregar o buscador.");
    } finally {
      setLoading(false);
    }
  }, [loadMission, selectedId, token]);

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void loadDemands();
  }, []); // load only on entry, including development Strict Mode

  async function selectDemand(id: string) {
    setSelectedId(id);
    setStandardSearchRun(null);
    setAiSearchRun(null);
    setLoading(true);
    try { await loadMission(id); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Falha ao abrir a busca."); }
    finally { setLoading(false); }
  }

  const pollSearchRun = useCallback(async (
    current: FederatedSearchRun,
    kind: "standard" | "ai",
  ) => {
    try {
      const statusRun = await request<FederatedSearchRun>(
        `/capture/search-runs/${current.id}?include_results=false`, {}, token,
      );
      const run = statusRun.result_count === current.result_count
        ? { ...statusRun, results: current.results, results_has_more: false }
        : await hydrateRunResults(statusRun);
      if (kind === "ai") setAiSearchRun(run);
      else setStandardSearchRun(run);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível atualizar a busca.");
    }
  }, [hydrateRunResults, token]);

  useEffect(() => {
    if (!standardSearchRun || terminalSearchStatuses.has(standardSearchRun.status)) return;
    const timeout = window.setTimeout(
      () => void pollSearchRun(standardSearchRun, "standard"),
      1500,
    );
    return () => window.clearTimeout(timeout);
  }, [pollSearchRun, standardSearchRun]);

  useEffect(() => {
    if (!aiSearchRun || terminalSearchStatuses.has(aiSearchRun.status)) return;
    const timeout = window.setTimeout(
      () => void pollSearchRun(aiSearchRun, "ai"),
      1500,
    );
    return () => window.clearTimeout(timeout);
  }, [aiSearchRun, pollSearchRun]);

  async function startFederatedSearch(forceRefresh = false) {
    if (!selectedId) return;
    setStartingSearch(true);
    setMessage(null);
    try {
      const run = await request<FederatedSearchRun>("/capture/search-runs", {
        method: "POST",
        body: JSON.stringify({ demand_id: selectedId, force_refresh: forceRefresh }),
      }, token);
      setStandardSearchRun(await hydrateRunResults(run));
      setCompatibilityFilter("all");
      setResultDisplayLimit(resultPageSize);
      if (run.cache_hit) {
        setMessage("Esta busca já havia sido realizada. Exibindo os resultados armazenados, sem uma nova consulta aos portais.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível iniciar a busca.");
    } finally {
      setStartingSearch(false);
    }
  }

  async function startAiSearch(forceRefresh = false) {
    if (!selectedId || !aiDiscoveryAvailable) return;
    setStartingAiSearch(true);
    setMessage(null);
    try {
      const run = await request<FederatedSearchRun>("/capture/search-runs", {
        method: "POST",
        body: JSON.stringify({
          demand_id: selectedId,
          source_ids: ["web_discovery"],
          force_refresh: forceRefresh,
        }),
      }, token);
      setAiSearchRun(await hydrateRunResults(run));
      setCompatibilityFilter("all");
      setResultDisplayLimit(resultPageSize);
      if (run.cache_hit) {
        setMessage("A descoberta com IA já havia sido realizada para estes critérios. Exibindo o resultado armazenado.");
      }
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Não foi possível ampliar a busca com IA.",
      );
    } finally {
      setStartingAiSearch(false);
    }
  }

  async function saveFederatedResult(
    runId: string,
    item: FederatedSearchRun["results"][number],
  ) {
    if (item.review_status === "saved" || savingResultIds.has(item.id)) return;
    setSavingResultIds((current) => new Set(current).add(item.id));
    setMessage(null);
    try {
      await request<Property>(
        `/capture/search-runs/${runId}/results/${item.id}/save`,
        { method: "POST" },
        token,
      );
      const markSaved = (current: FederatedSearchRun | null) => current ? {
        ...current,
        results: current.results.map((result) => (
          result.id === item.id ? { ...result, review_status: "saved" as const } : result
        )),
      } : current;
      setStandardSearchRun(markSaved);
      setAiSearchRun(markSaved);
      if (selectedId) await loadMission(selectedId, false);
      setMessage("Imóvel salvo nos resultados desta demanda.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível salvar o imóvel.");
    } finally {
      setSavingResultIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
  }

  async function unsaveFederatedResult(
    runId: string,
    item: FederatedSearchRun["results"][number],
  ) {
    if (savingResultIds.has(item.id)) return;
    setSavingResultIds((current) => new Set(current).add(item.id));
    setMessage(null);
    try {
      await request<void>(
        `/capture/search-runs/${runId}/results/${item.id}/save`,
        { method: "DELETE" },
        token,
      );
      const markNew = (current: FederatedSearchRun | null) => current ? {
        ...current,
        results: current.results.map((result) => (
          result.id === item.id ? { ...result, review_status: "new" as const } : result
        )),
      } : current;
      setStandardSearchRun(markNew);
      setAiSearchRun(markNew);
      if (selectedId) await loadMission(selectedId, false);
      setMessage("Imóvel removido dos salvos.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível remover o imóvel.");
    } finally {
      setSavingResultIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
  }

  async function cancelRun(run: FederatedSearchRun) {
    try {
      const cancelled = await request<FederatedSearchRun>(
        `/capture/search-runs/${run.id}/cancel`,
        { method: "POST" },
        token,
      );
      if (run.sources.some((source) => source.source_id === "web_discovery")) {
        setAiSearchRun(cancelled);
      } else {
        setStandardSearchRun(cancelled);
      }
      setMessage("Busca cancelada. Operações que ainda não haviam começado não serão cobradas.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível cancelar a busca.");
    }
  }

  async function retrySource(runId: string, sourceId: string) {
    try {
      const run = await request<FederatedSearchRun>(
        `/capture/search-runs/${runId}/sources/${sourceId}/retry`,
        { method: "POST" },
        token,
      );
      if (run.sources.some((source) => source.source_id === "web_discovery")) {
        setAiSearchRun(run);
      } else {
        setStandardSearchRun(run);
      }
      setMessage("Fonte recolocada na fila.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível repetir a fonte.");
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

  async function removeSavedProperty(propertyId: string) {
    if (!selectedId || removingSavedIds.has(propertyId)) return;
    setRemovingSavedIds((current) => new Set(current).add(propertyId));
    try {
      await request<void>(
        `/capture/demands/${selectedId}/properties/${propertyId}`,
        { method: "DELETE" },
        token,
      );
      await loadMission(selectedId, false);
      setMessage("Imóvel removido dos salvos.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível remover o imóvel.");
    } finally {
      setRemovingSavedIds((current) => {
        const next = new Set(current);
        next.delete(propertyId);
        return next;
      });
    }
  }

  async function deleteDemand() {
    if (!demandToDelete || deletingDemand) return;
    const deletedId = demandToDelete.id;
    setDeletingDemand(true);
    setMessage(null);
    try {
      await request<void>(`/leads/demands/${deletedId}`, { method: "DELETE" }, token);
      const remaining = demands.filter((demand) => demand.id !== deletedId);
      setDemands(remaining);
      setDemandToDelete(null);
      if (selectedId === deletedId) {
        const nextDemand = remaining[0] ?? null;
        setSelectedId(nextDemand?.id ?? null);
        setMission(null);
        setStandardSearchRun(null);
        setAiSearchRun(null);
        if (nextDemand) {
          setLoading(true);
          try {
            await loadMission(nextDemand.id);
          } catch (error) {
            setMessage(error instanceof Error ? `Demanda excluída. ${error.message}` : "Demanda excluída, mas não foi possível abrir a próxima.");
            return;
          } finally {
            setLoading(false);
          }
        }
      }
      setMessage("Demanda excluída.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível excluir a demanda.");
    } finally {
      setDeletingDemand(false);
    }
  }

  const visibleSearchRuns = [standardSearchRun, aiSearchRun].filter(
    (run): run is FederatedSearchRun => run !== null,
  );
  const visibleSources = visibleSearchRuns.flatMap((run) => (
    run.sources.map((source) => ({ runId: run.id, source }))
  ));
  const visibleResults: Array<{
    runId: string;
    item: FederatedSearchRun["results"][number];
  }> = [];
  const resultUrls = new Set<string>();
  for (const run of visibleSearchRuns) {
    for (const item of run.results) {
      const resultKey = item.canonical_url.replace(/[?#].*$/, "").replace(/\/$/, "");
      if (resultUrls.has(resultKey)) continue;
      resultUrls.add(resultKey);
      visibleResults.push({ runId: run.id, item });
    }
  }
  const completedSourceCount = visibleSearchRuns.reduce(
    (total, run) => total + run.completed_source_count,
    0,
  );
  const totalSourceCount = visibleSearchRuns.reduce(
    (total, run) => total + run.source_count,
    0,
  );
  const searchInProgress = visibleSearchRuns.some(
    (run) => !terminalSearchStatuses.has(run.status),
  );
  const standardSearchFinished = Boolean(
    standardSearchRun && ["partial", "completed"].includes(standardSearchRun.status),
  );
  const ranking = compatibilityCounts(visibleResults.map(({ item }) => item.fit_score));
  const filteredResults = visibleResults.filter(({ item }) => (
    matchesCompatibilityFilter(item.fit_score, compatibilityFilter)
  ));
  const displayedResults = filteredResults.slice(0, resultDisplayLimit);
  const compatibilityOptions: Array<{
    id: Exclude<CompatibilityFilter, "all">;
    label: string;
    detail: string;
    count: number;
  }> = [
    { id: "perfect", label: "100%", detail: "Compatibilidade total", count: ranking.perfect },
    { id: "high", label: "80–99%", detail: "Alta compatibilidade", count: ranking.high },
    { id: "lower", label: "Abaixo de 80%", detail: "Com pontos de atenção", count: ranking.lower },
  ];

  return (
    <section className="property-search-page">
      <header className="page-header property-search-header">
        <div>
          <span className="eyebrow">Captação externa</span>
          <h1>Buscador de imóveis</h1>
          <p>Pesquise imóveis para uma demanda e mantenha a origem do anúncio sempre visível.</p>
        </div>
        <button className="primary-button property-search-cta" disabled={!canSearch} onClick={() => setModalOpen(true)} type="button">
          <Plus size={17} />
          Nova demanda
        </button>
      </header>

      <div className="capture-notice"><Sparkles size={18} /><span>Imóveis captados ficam disponíveis ao corretor. A IA continua oferecendo somente imóveis da carteira própria.</span></div>
      {message ? <div className="inline-feedback">{message}</div> : null}

      <div className="property-search-layout">
        <aside className="property-search-sidebar">
          <section className="demand-list panel-card">
            <div className="panel-title"><div><span className="eyebrow">Demandas</span><h2>Clientes em busca</h2></div><button aria-label="Atualizar" className="icon-button" onClick={() => void loadDemands()} type="button"><RefreshCw size={16} /></button></div>
            {demands.length === 0 && !loading ? <div className="empty-state"><Search size={24} /><p>Cadastre uma demanda para começar.</p></div> : null}
            {demands.map((demand) => (
              <div className={`demand-list-item${selectedId === demand.id ? " active" : ""}`} key={demand.id}>
                <button className="demand-select-button" onClick={() => void selectDemand(demand.id)} type="button">
                  <strong>{demand.lead_name}</strong><span>{purposeLabel(demand.purpose)} · {demand.property_type || "Imóvel"}</span><small>{demand.city || "Cidade não informada"}{demand.neighborhoods.length ? ` · ${demand.neighborhoods.join(", ")}` : ""}</small>
                </button>
                {canSearch ? <button
                  aria-label={`Excluir demanda de ${demand.lead_name}`}
                  className="demand-delete-button"
                  onClick={() => setDemandToDelete(demand)}
                  title="Excluir demanda"
                  type="button"
                >
                  <X size={14} />
                </button> : null}
              </div>
            ))}
          </section>

          <section className="source-sidebar panel-card">
            <div className="panel-title">
              <div><span className="eyebrow">Fontes</span><h2>Portais consultados</h2></div>
              {totalSourceCount ? <small>{completedSourceCount}/{totalSourceCount}</small> : null}
            </div>
            {visibleSources.length ? (
              <div className="source-sidebar-list">
                {visibleSources.map(({ runId, source }) => (
                  <div
                    className={`source-sidebar-item ${source.status}`}
                    key={`${runId}-${source.source_id}`}
                    title={source.error ?? undefined}
                  >
                    <i />
                    <span>
                      <strong>{source.source_name}</strong>
                      <small>
                        {sourceStatusLabel(source.status)}
                        {source.status === "completed" ? ` · ${source.discovered_count} imóveis` : ""}
                      </small>
                      {source.error ? <small className="source-error">{source.error}</small> : null}
                    </span>
                    {canSearch && source.source_id !== "web_discovery" && ["failed", "blocked"].includes(source.status) ? (
                      <button
                        aria-label={`Tentar ${source.source_name} novamente`}
                        className="source-retry-button"
                        onClick={() => void retrySource(runId, source.source_id)}
                        type="button"
                      >
                        <RefreshCw size={13} />
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="source-sidebar-empty">As fontes utilizadas aparecerão aqui após iniciar uma busca.</p>
            )}
          </section>
        </aside>

        <main className="capture-workspace">
          {loading ? <div className="panel-card empty-state large"><RefreshCw className="spin" size={26} /><p>Preparando a busca…</p></div> : null}
          {!loading && mission ? (
            <>
              <section className="panel-card mission-summary search-stage search-stage-active">
                <div>
                  <span className="eyebrow">Demanda selecionada</span>
                  <h2>{mission.demand.lead_name}</h2>
                  <p>
                    {purposeLabel(mission.demand.purpose)} de {mission.demand.property_type || "imóvel"} em {mission.demand.city || "cidade não informada"}{mission.demand.state ? `/${mission.demand.state}` : ""}
                  </p>
                  {canSearch ? (
                    <button
                      className="edit-demand-button"
                      onClick={() => setEditingDemand(
                        demands.find((item) => item.id === selectedId) ?? null
                      )}
                      type="button"
                    >
                      <Pencil size={14} /> Editar critérios
                    </button>
                  ) : null}
                </div>
                <div className="mission-search-actions">
                  <div className="mission-chips">
                    {mission.demand.neighborhoods.map((item) => <span key={item}>{item}</span>)}
                    {mission.demand.price_max ? <span>até {money(mission.demand.price_max)}</span> : null}
                    {mission.demand.bedrooms ? <span>{mission.demand.bedrooms}+ quartos</span> : null}
                  </div>
                  <div className="mission-search-buttons">
                    <button
                      className="primary-button property-search-cta"
                      disabled={!canSearch || startingSearch || startingAiSearch || searchInProgress}
                      onClick={() => standardSearchRun
                        ? setRefreshKind("standard")
                        : void startFederatedSearch()}
                      type="button"
                    >
                      {startingSearch ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />}
                      {startingSearch ? "Iniciando…" : standardSearchRun ? "Atualizar busca" : "Buscar imóveis"}
                    </button>
                    <button
                      className="secondary-button ai-web-search-button"
                      disabled={
                        startingAiSearch
                        || searchInProgress
                        || !standardSearchFinished
                        || !aiDiscoveryAvailable
                      }
                      onClick={() => aiSearchRun ? setRefreshKind("ai") : void startAiSearch()}
                      title={
                        !aiDiscoveryAvailable
                          ? "Descoberta web indisponível neste ambiente"
                          : !standardSearchFinished
                            ? "Execute a busca convencional antes de ampliar com IA."
                            : "Recurso premium com consumo de créditos. Resultados em cache não são cobrados novamente."
                      }
                      type="button"
                    >
                      {startingAiSearch ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
                      {startingAiSearch
                        ? "Ampliando…"
                        : aiSearchRun
                          ? "Atualizar descoberta com IA"
                          : "Ampliar busca com IA"}
                      <span>Premium</span>
                    </button>
                    {searchInProgress && canSearch ? (
                      <button
                        className="secondary-button cancel-search-button"
                        onClick={() => {
                          const running = visibleSearchRuns.find(
                            (run) => !terminalSearchStatuses.has(run.status),
                          );
                          if (running) void cancelRun(running);
                        }}
                        type="button"
                      >
                        <StopCircle size={15} /> Cancelar busca
                      </button>
                    ) : null}
                  </div>
                </div>
              </section>

              <section className="search-stage">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">Imóveis encontrados</span>
                  </div>
                  <p>Compare os anúncios e salve apenas os imóveis interessantes.</p>
                </div>
                {visibleSearchRuns.length ? (
                  <>
                    <div className="search-run-history" aria-label="Histórico das buscas exibidas">
                      {visibleSearchRuns.map((run) => {
                        const isAi = run.sources.some((source) => source.source_id === "web_discovery");
                        return (
                          <div key={run.id}>
                            <span>{isAi ? "Descoberta com IA" : "Busca nos portais"}</span>
                            <small>
                              {run.cache_hit ? "Resultado armazenado" : "Consulta atual"}
                              {` · ${searchRunTimestamp(run.created_at)}`}
                            </small>
                          </div>
                        );
                      })}
                    </div>
                    <div className="compatibility-ranking panel-card">
                      <div className="compatibility-ranking-header">
                        <div>
                          <strong>Ranking de compatibilidade</strong>
                          <span>
                            {compatibilityFilter === "all"
                              ? `${visibleResults.length} imóveis encontrados`
                              : `${filteredResults.length} de ${visibleResults.length} imóveis`}
                          </span>
                        </div>
                        {compatibilityFilter !== "all" ? (
                          <button
                            onClick={() => {
                              setCompatibilityFilter("all");
                              setResultDisplayLimit(resultPageSize);
                            }}
                            type="button"
                          >
                            Limpar filtro
                          </button>
                        ) : null}
                      </div>
                      <div className="compatibility-filter-grid">
                        {compatibilityOptions.map((option) => (
                          <button
                            aria-pressed={compatibilityFilter === option.id}
                            className={compatibilityFilter === option.id ? "active" : ""}
                            key={option.id}
                            onClick={() => {
                              setCompatibilityFilter((current) => (
                                current === option.id ? "all" : option.id
                              ));
                              setResultDisplayLimit(resultPageSize);
                            }}
                            type="button"
                          >
                            <span>{option.label}</span>
                            <strong>{option.count}</strong>
                            <small>{option.detail}</small>
                          </button>
                        ))}
                      </div>
                    </div>
                    {filteredResults.length ? (
                      <>
                        <div className="external-result-grid">
                        {displayedResults.map(({ runId, item }) => {
                          const saving = savingResultIds.has(item.id);
                          const saved = item.review_status === "saved";
                          return (
                            <article className="panel-card external-result-card" key={`${runId}-${item.id}`}>
                              <ExternalResultImage src={item.primary_image_url} title={item.title} />
                              <div className="external-result-content">
                                <div className="external-result-source">
                                  <span>{item.source_id === "web_discovery" ? item.source_domain : item.source_name}</span>
                                  <small>{item.advertiser_name ? `Anunciante: ${item.advertiser_name} · ` : ""}{updatedLabel(item.last_seen_at)}</small>
                                </div>
                                <h3>{item.title}</h3>
                                <ExternalResultPrice item={item} purpose={mission.demand.purpose} />
                                <p>{[item.neighborhood, item.city, item.state].filter(Boolean).join(" · ")}</p>
                                <div className="external-result-features">
                                  {item.area ? <span>{item.area} m²</span> : null}
                                  {item.bedrooms != null ? <span>{item.bedrooms} quartos</span> : null}
                                  {item.parking_spaces != null ? <span>{item.parking_spaces} vagas</span> : null}
                                </div>
                                <div className="external-result-scores">
                                  <span>{item.fit_score}% compatível</span>
                                  <small>Confiança {item.confidence_score}%</small>
                                </div>
                                {item.matched.length || item.tradeoffs.length ? (
                                  <div className="external-result-explanation">
                                    {item.matched.length ? (
                                      <small title={item.matched.join(", ")}>
                                        Atende: {item.matched.slice(0, 3).join(", ")}
                                      </small>
                                    ) : null}
                                    {item.tradeoffs.length ? (
                                      <small className="has-tradeoffs" title={item.tradeoffs.join(", ")}>
                                        Pontos de atenção: {item.tradeoffs.slice(0, 3).join(", ")}
                                      </small>
                                    ) : null}
                                  </div>
                                ) : null}
                                <div className="external-result-actions">
                                  <a href={item.canonical_url} rel="noreferrer" target="_blank">
                                    Ver anúncio <ExternalLink size={14} />
                                  </a>
                                  <button
                                    className={`save-result-button${saved ? " saved" : ""}`}
                                    disabled={saving || !canSearch}
                                    onClick={() => saved
                                      ? void unsaveFederatedResult(runId, item)
                                      : void saveFederatedResult(runId, item)}
                                    type="button"
                                  >
                                    {saving ? <LoaderCircle className="spin" size={15} /> : saved ? <Check size={15} /> : <Bookmark size={15} />}
                                    {saving ? "Salvando…" : saved ? "Remover dos salvos" : "Salvar imóvel"}
                                  </button>
                                </div>
                              </div>
                            </article>
                          );
                        })}
                        </div>
                        {displayedResults.length < filteredResults.length ? (
                          <button
                            className="secondary-button load-more-results-button"
                            onClick={() => setResultDisplayLimit((current) => (
                              current + resultPageSize
                            ))}
                            type="button"
                          >
                            Mostrar mais {Math.min(
                              resultPageSize,
                              filteredResults.length - displayedResults.length,
                            )} imóveis
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <div className="panel-card empty-state">
                        {!searchInProgress ? <Search size={24} /> : <RefreshCw className="spin" size={24} />}
                        <p>
                          {searchInProgress
                            ? "Pesquisando nos portais e preparando os primeiros resultados…"
                            : visibleResults.length
                              ? "Nenhum imóvel está nesta faixa de compatibilidade."
                              : "Nenhum resultado compatível nesta execução."}
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="panel-card empty-state">
                    <Search size={24} />
                    <p>Revise os critérios e inicie a busca para consultar os portais.</p>
                  </div>
                )}
              </section>

              <section className="search-stage saved-results-stage">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">Imóveis salvos</span>
                  </div>
                  <div className="section-actions">
                    <p>{mission.existing_matches.length} {mission.existing_matches.length === 1 ? "imóvel salvo" : "imóveis salvos"}</p>
                    <button className="secondary-button" disabled={!canSearch} onClick={() => setCaptureOpen(true)} type="button">
                      <Plus size={15} /> Salvar por URL
                    </button>
                  </div>
                </div>
                {mission.existing_matches.length ? (
                  <div className="captured-results">
                    {mission.existing_matches.map((item) => (
                      <article className="panel-card captured-result" key={item.id}>
                        <div><strong>{item.title}</strong><span>{money(item.price)}</span></div>
                        <div className="match-score">{Math.round(item.score)}% compatível</div>
                        {item.tradeoffs.length ? (
                          <small>Pontos de atenção: {item.tradeoffs.join(", ")}</small>
                        ) : (
                          <small className="all-filters">Compatível com os filtros principais</small>
                        )}
                        {item.source_url ? (
                          <a href={item.source_url} rel="noreferrer" target="_blank">
                            Ver anúncio original <ExternalLink size={14} />
                          </a>
                        ) : null}
                        {canSearch ? (
                          <button
                            className="remove-saved-property-button"
                            disabled={removingSavedIds.has(item.id)}
                            onClick={() => void removeSavedProperty(item.id)}
                            type="button"
                          >
                            <X size={14} />
                            {removingSavedIds.has(item.id) ? "Removendo…" : "Remover dos salvos"}
                          </button>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="panel-card empty-state saved-results-empty">
                    <Bookmark size={24} />
                    <p>Você ainda não salvou nenhum resultado para esta demanda.</p>
                    <small>Use “Salvar imóvel” nos cards da busca federada.</small>
                  </div>
                )}
              </section>
            </>
          ) : null}
        </main>
      </div>
      <DemandModal isOpen={modalOpen} onClose={() => setModalOpen(false)} onCreated={(demand) => { setDemands((current) => [demand, ...current]); setSelectedId(demand.id); void loadMission(demand.id); }} />
      <DemandModal
        demand={editingDemand}
        isOpen={editingDemand !== null}
        onClose={() => setEditingDemand(null)}
        onCreated={(updated) => {
          setDemands((current) => current.map((item) => item.id === updated.id ? updated : item));
          setEditingDemand(null);
          setStandardSearchRun(null);
          setAiSearchRun(null);
          void loadMission(updated.id);
        }}
      />
      {refreshKind ? (
        <div className="modal-backdrop" role="presentation">
          <section aria-modal="true" className="demand-modal demand-delete-modal" role="dialog">
            <header className="modal-header">
              <div>
                <span className="eyebrow">Atualizar resultados</span>
                <h2>Executar uma nova consulta?</h2>
                <p>
                  O histórico atual será preservado. A atualização ignora o cache e pode consumir
                  {refreshKind === "ai" ? " créditos da descoberta com IA." : " créditos da busca convencional."}
                </p>
              </div>
              <button aria-label="Fechar" className="icon-button" onClick={() => setRefreshKind(null)} type="button"><X size={18} /></button>
            </header>
            <footer className="modal-actions">
              <button className="secondary-button" onClick={() => setRefreshKind(null)} type="button">Manter resultados atuais</button>
              <button
                className="primary-button"
                onClick={() => {
                  const kind = refreshKind;
                  setRefreshKind(null);
                  if (kind === "ai") void startAiSearch(true);
                  else void startFederatedSearch(true);
                }}
                type="button"
              >
                Atualizar e consumir créditos
              </button>
            </footer>
          </section>
        </div>
      ) : null}
      {demandToDelete ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !deletingDemand) setDemandToDelete(null); }}>
          <section aria-labelledby="delete-demand-title" aria-modal="true" className="demand-modal demand-delete-modal" role="dialog">
            <header className="modal-header">
              <div>
                <span className="eyebrow">Excluir demanda</span>
                <h2 id="delete-demand-title">Deseja excluir a demanda de {demandToDelete.lead_name}?</h2>
                <p>A demanda, as buscas realizadas e os vínculos com imóveis salvos serão removidos. Esta ação não poderá ser desfeita.</p>
              </div>
              <button aria-label="Fechar" className="icon-button" disabled={deletingDemand} onClick={() => setDemandToDelete(null)} type="button"><X size={18} /></button>
            </header>
            <footer className="modal-actions">
              <button className="secondary-button" disabled={deletingDemand} onClick={() => setDemandToDelete(null)} type="button">Cancelar</button>
              <button className="button-danger" disabled={deletingDemand} onClick={() => void deleteDemand()} type="button">
                {deletingDemand ? <LoaderCircle className="spin" size={16} /> : null}
                {deletingDemand ? "Excluindo…" : "Excluir demanda"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
      {captureOpen && mission ? <div className="modal-backdrop" role="presentation"><section aria-modal="true" className="demand-modal capture-modal" role="dialog"><header className="modal-header"><div><span className="eyebrow">Captação manual</span><h2>Salvar anúncio externo</h2><p>Cole o anúncio encontrado para vinculá-lo a {mission.demand.lead_name}.</p></div><button aria-label="Fechar" className="icon-button" onClick={() => setCaptureOpen(false)} type="button"><X size={18} /></button></header><div className="form-grid"><label>Portal *<select value={captureForm.source} onChange={(event) => setCaptureForm((current) => ({ ...current, source: event.target.value }))}><option value="olx">OLX</option><option value="zap">ZAP Imóveis</option><option value="vivareal">Viva Real</option><option value="lello">Lello</option><option value="outro">Outro</option></select></label><label>URL do anúncio *<input required type="url" value={captureForm.source_url} onChange={(event) => setCaptureForm((current) => ({ ...current, source_url: event.target.value }))} /></label><label className="form-span-2">Título *<input required value={captureForm.title} onChange={(event) => setCaptureForm((current) => ({ ...current, title: event.target.value }))} /></label><label>Bairro<input value={captureForm.neighborhood} onChange={(event) => setCaptureForm((current) => ({ ...current, neighborhood: event.target.value }))} /></label><label>Preço<input min="0" step="0.01" type="number" value={captureForm.price} onChange={(event) => setCaptureForm((current) => ({ ...current, price: event.target.value }))} /></label></div><footer className="modal-actions"><button className="secondary-button" onClick={() => setCaptureOpen(false)} type="button">Cancelar</button><button className="primary-button" disabled={savingCapture || !captureForm.source_url.trim() || !captureForm.title.trim()} onClick={() => void saveCapturedProperty()} type="button">{savingCapture ? "Salvando…" : "Salvar anúncio"}</button></footer></section></div> : null}
    </section>
  );
}

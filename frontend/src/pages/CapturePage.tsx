import { BellPlus, CheckCircle2, ExternalLink, Plus, Puzzle, Search, Sparkles, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../api/client";
import type { CaptureMission, DiscoverMissionResult, LeadDemand, Property } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import { DemandModal } from "../components/DemandModal";
import { PropertyCard } from "../components/PropertyCard";
import { formatCurrency, labelOrDash } from "../lib/format";

export function CapturePage() {
  const { token } = useAuth();
  const [demands, setDemands] = useState<LeadDemand[]>([]);
  const [selectedDemandId, setSelectedDemandId] = useState("");
  const [mission, setMission] = useState<CaptureMission | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [loadingMission, setLoadingMission] = useState(false);
  const [demandModalOpen, setDemandModalOpen] = useState(false);
  const [discoveringPortal, setDiscoveringPortal] = useState<string | null>(null);
  const [discoveryMessage, setDiscoveryMessage] = useState<string | null>(null);

  async function loadDemands(selectDemandId?: string) {
    const items = await request<LeadDemand[]>("/leads/demands", {}, token);
    setDemands(items);
    setSelectedDemandId((current) => selectDemandId || current || items[0]?.id || "");
  }

  useEffect(() => {
    void loadDemands();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  function handleDemandCreated(demand: LeadDemand) {
    setDemands((current) => [demand, ...current.filter((item) => item.id !== demand.id)]);
    setSelectedDemandId(demand.id);
    void loadDemands(demand.id);
  }

  useEffect(() => {
    if (!selectedDemandId) {
      setMission(null);
      setProperties([]);
      return;
    }
    setLoadingMission(true);
    void Promise.all([
      request<CaptureMission>(`/capture/missions/${selectedDemandId}`, {}, token),
      request<Property[]>(`/properties?demand_id=${selectedDemandId}`, {}, token),
    ])
      .then(([nextMission, nextProperties]) => {
        setMission(nextMission);
        setProperties(nextProperties);
      })
      .finally(() => setLoadingMission(false));
  }, [selectedDemandId, token]);

  const selectedDemand = useMemo(
    () => demands.find((item) => item.id === selectedDemandId) ?? null,
    [demands, selectedDemandId],
  );

  async function discoverProperties(portal: string) {
    if (!selectedDemandId) return;
    setDiscoveringPortal(portal);
    setDiscoveryMessage(null);
    try {
      const result = await request<DiscoverMissionResult>(
        `/capture/missions/${selectedDemandId}/discover`,
        { method: "POST", body: JSON.stringify({ portal, limit: 20 }) },
        token,
      );
      setDiscoveryMessage(
        result.imported > 0
          ? `${result.imported} referências encontradas no ${portal.toUpperCase()} e vinculadas à demanda.`
          : `Nenhum anúncio público novo foi identificado no ${portal.toUpperCase()}.`,
      );
      const [nextMission, nextProperties] = await Promise.all([
        request<CaptureMission>(`/capture/missions/${selectedDemandId}`, {}, token),
        request<Property[]>(`/properties?demand_id=${selectedDemandId}`, {}, token),
      ]);
      setMission(nextMission);
      setProperties(nextProperties);
    } catch (error) {
      setDiscoveryMessage(error instanceof Error ? error.message : "Falha ao consultar o portal.");
    } finally {
      setDiscoveringPortal(null);
    }
  }

  return (
    <section className="capture-layout">
      <aside className="capture-sidebar">
        <div className="section-kicker">
          <Puzzle size={16} />
          Captação
        </div>
        <h2>Missão de busca</h2>
        <p>
          Escolha uma demanda. O sistema monta os filtros e lista imóveis já encontrados para
          essa busca.
        </p>
        <button className="button-outline" onClick={() => setDemandModalOpen(true)} type="button">
          <Plus size={15} />
          Cadastrar demanda
        </button>

        <label>
          Demanda
          <select value={selectedDemandId} onChange={(event) => setSelectedDemandId(event.target.value)}>
            {demands.length === 0 ? <option value="">Nenhuma demanda disponível</option> : null}
            {demands.map((demand) => (
              <option key={demand.id} value={demand.id}>
                {demand.lead_name} · {labelOrDash(demand.city)}
              </option>
            ))}
          </select>
        </label>

        <div className="demand-card">
          <strong>{selectedDemand?.lead_name ?? "Sem demanda selecionada"}</strong>
          <span>{selectedDemand?.phone ?? "Crie uma demanda para iniciar a captação"}</span>
          <dl>
            <div>
              <dt>Finalidade</dt>
              <dd>{labelOrDash(selectedDemand?.purpose)}</dd>
            </div>
            <div>
              <dt>Tipo</dt>
              <dd>{labelOrDash(selectedDemand?.property_type)}</dd>
            </div>
            <div>
              <dt>Cidade</dt>
              <dd>{labelOrDash(selectedDemand?.city)}</dd>
            </div>
            <div>
              <dt>Orçamento</dt>
              <dd>
                {formatCurrency(selectedDemand?.price_min)} a {formatCurrency(selectedDemand?.price_max)}
              </dd>
            </div>
          </dl>
        </div>
      </aside>

      <div className="capture-main">
        <div className="capture-tabs">
          <span className="active">Resultados</span>
          <span>Demandas salvas</span>
          <span>Extensão</span>
        </div>

        {selectedDemand ? (
          <div className="capture-content">
            <Card className="mission-banner">
              <div className="mission-icon">
                <Target size={18} />
              </div>
              <div>
                <h3>{loadingMission ? "Carregando missão..." : "Missão de captura pronta"}</h3>
                <p>
                  {labelOrDash(selectedDemand.property_type)} em {labelOrDash(selectedDemand.city)}
                  {selectedDemand.neighborhoods.length > 0
                    ? `, ${selectedDemand.neighborhoods.join(", ")}`
                    : ""}
                  .
                </p>
              </div>
              <Badge variant="success">
                <CheckCircle2 size={13} />
                pronto
              </Badge>
            </Card>

            <Card className="extension-panel">
              <div className="panel-title">
                <Puzzle size={17} />
                <strong>Captura via extensão do corretor</strong>
              </div>
              <p>Abra cada portal com os filtros que ele aceita já aplicados. Os filtros restantes aparecem em cada cartão.</p>
              <div className="portal-grid">
                {(mission?.portal_searches ?? []).map((portal) => (
                  <div className="portal-card" key={portal.id}>
                    <div>
                      <strong>{portal.name}</strong>
                      <span>{portal.applied_filters.length} filtros aplicados</span>
                      {portal.pending_filters.length > 0 ? <small>Completar no portal: {portal.pending_filters.join(", ")}</small> : <small>Busca pronta</small>}
                    </div>
                    <div className="portal-actions">
                      {(portal.id === "lello" || portal.id === "olx") ? (
                        <button disabled={discoveringPortal !== null} onClick={() => void discoverProperties(portal.id)} type="button">
                          <Search size={14} />
                          {discoveringPortal === portal.id ? "Buscando..." : "Buscar agora"}
                        </button>
                      ) : null}
                      <a aria-label={`Abrir ${portal.name}`} href={portal.url} rel="noreferrer" target="_blank"><ExternalLink size={15} /></a>
                    </div>
                  </div>
                ))}
              </div>
              {discoveryMessage ? <p className="discovery-message">{discoveryMessage}</p> : null}
            </Card>

            <Card className="alert-panel">
              <Sparkles size={18} />
              <span>
                {mission?.existing_matches.length ?? 0} matches existentes na missão;{" "}
                {properties.length} imóveis vinculados.
              </span>
              <button className="button-outline" type="button">
                <BellPlus size={15} />
                Alerta recorrente
              </button>
            </Card>

            {properties.length > 0 ? (
              <div className="property-grid">
                {properties.map((property) => {
                  const match = mission?.existing_matches.find((item) => item.id === property.id);
                  return <div className="property-match" key={property.id}>
                    {match ? <div className="match-summary"><strong>{match.score}% compatível</strong><span>{match.matched.join(" · ")}</span>{match.tradeoffs.length > 0 ? <small>Atenção: {match.tradeoffs.join(", ")}</small> : null}</div> : null}
                    <PropertyCard property={property} />
                  </div>;
                })}
              </div>
            ) : (
              <div className="empty-state large">
                <Search size={26} />
                <strong>Nenhum imóvel vinculado ainda.</strong>
                <span>Capture via extensão/API para alimentar esta demanda.</span>
              </div>
            )}
          </div>
        ) : (
          <div className="empty-state large">
            <Search size={26} />
            <strong>Nenhuma demanda cadastrada.</strong>
            <span>Cadastre uma demanda para iniciar a busca de imóveis.</span>
            <button className="button-outline" onClick={() => setDemandModalOpen(true)} type="button">
              <Plus size={15} />
              Cadastrar demanda
            </button>
          </div>
        )}
      </div>
      <DemandModal
        isOpen={demandModalOpen}
        onClose={() => setDemandModalOpen(false)}
        onCreated={handleDemandCreated}
      />
    </section>
  );
}

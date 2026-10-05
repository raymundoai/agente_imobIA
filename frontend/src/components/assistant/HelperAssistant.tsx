import { ArrowLeft, BookOpen, Search, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { ARTICLES, type Article, type HelpContext, SCREENS, type TourStep } from "../../help/content";
import { openAppLink, pageFromPath, ROUTE_CHANGED_EVENT } from "../../lib/appNavigation";
import { Modal } from "../Modal";
import { Mascot } from "./Mascot";

const SEEN_KEY = "immobia.assistant.seen";
const AUTO_KEY = "immobia.assistant.autotips";

function readSeen(): string[] {
  try {
    return JSON.parse(window.localStorage.getItem(SEEN_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

function writeSeen(seen: string[]) {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify(seen));
  } catch {
    /* tips still work, they just show again next time */
  }
}

function readAuto() {
  try {
    return window.localStorage.getItem(AUTO_KEY) !== "off";
  } catch {
    return true;
  }
}

function currentContext(): HelpContext {
  const page = pageFromPath(window.location.pathname);
  if (page !== "settings") return page;
  const tab = new URLSearchParams(window.location.search).get("aba") ?? "company";
  const known = ["company", "channels", "integrations", "agents", "users", "network", "billing", "history"];
  return `settings:${known.includes(tab) ? tab : "company"}` as HelpContext;
}

/** The little house in the corner: a tip per screen, guided tours and the help centre. */
export function HelperAssistant() {
  const [context, setContext] = useState<HelpContext>(() => currentContext());
  const [bubble, setBubble] = useState(false);
  const [panel, setPanel] = useState(false);
  const [autoTips, setAutoTips] = useState(readAuto);
  const [tour, setTour] = useState<TourStep[] | null>(null);
  const [helpOpen, setHelpOpen] = useState<{ article?: string } | null>(null);
  const screen = SCREENS[context];

  useEffect(() => {
    const sync = () => setContext(currentContext());
    window.addEventListener("popstate", sync);
    window.addEventListener(ROUTE_CHANGED_EVENT, sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(ROUTE_CHANGED_EVENT, sync);
    };
  }, []);

  // Speak up once per screen, a moment after it opens, unless the person turned tips off.
  useEffect(() => {
    setBubble(false);
    if (!autoTips || readSeen().includes(context)) return undefined;
    const handle = window.setTimeout(() => {
      setBubble(true);
      writeSeen([...readSeen(), context]);
    }, 1400);
    return () => window.clearTimeout(handle);
  }, [context, autoTips]);

  function toggleAuto(next: boolean) {
    setAutoTips(next);
    try {
      window.localStorage.setItem(AUTO_KEY, next ? "on" : "off");
    } catch {
      /* preference lasts for this visit only */
    }
  }

  function startTour() {
    setPanel(false);
    setBubble(false);
    const steps = screen.tour.filter((step) => document.querySelector(step.target));
    if (steps.length) setTour(steps);
  }

  const related = screen.articles.map((id) => ARTICLES.find((article) => article.id === id)).filter(Boolean) as Article[];

  return (
    <>
      <div className="assistant">
        {bubble && !panel ? (
          <div className="assistant-bubble" role="status">
            <button aria-label="Fechar dica" className="assistant-bubble-close" onClick={() => setBubble(false)} type="button">
              <X size={14} />
            </button>
            <p>{screen.tip}</p>
            <div className="assistant-bubble-actions">
              {screen.tour.length ? <button className="link-button" onClick={startTour} type="button">Me mostre como</button> : null}
              <button className="link-button" onClick={() => setBubble(false)} type="button">Entendi</button>
            </div>
          </div>
        ) : null}

        {panel ? (
          <section aria-label="Ajuda" className="assistant-panel">
            <header>
              <Mascot size={36} />
              <div>
                <strong>Posso ajudar?</strong>
                <small>Dicas desta tela e a central de ajuda.</small>
              </div>
              <button aria-label="Fechar ajuda" className="icon-button" onClick={() => setPanel(false)} type="button">
                <X size={16} />
              </button>
            </header>
            <p className="assistant-tip">{screen.tip}</p>
            <div className="assistant-actions">
              {screen.tour.length ? <button className="primary-button" onClick={startTour} type="button">Me mostre como</button> : null}
              <button className="secondary-button" onClick={() => { setPanel(false); setHelpOpen({}); }} type="button">
                <BookOpen size={15} /> Central de ajuda
              </button>
            </div>
            {related.length ? (
              <div className="assistant-related">
                <small>Sobre esta tela</small>
                {related.map((article) => (
                  <button key={article.id} onClick={() => { setPanel(false); setHelpOpen({ article: article.id }); }} type="button">
                    {article.title}
                  </button>
                ))}
              </div>
            ) : null}
            <label className="assistant-auto">
              <input checked={autoTips} onChange={(event) => toggleAuto(event.target.checked)} type="checkbox" />
              Mostrar uma dica ao abrir cada tela pela primeira vez
            </label>
          </section>
        ) : null}

        <button
          aria-expanded={panel}
          aria-label="Abrir ajuda"
          className="assistant-button"
          onClick={() => { setPanel((open) => !open); setBubble(false); }}
          type="button"
        >
          <Mascot alert={bubble} />
        </button>
      </div>

      {tour ? <Tour onClose={() => setTour(null)} steps={tour} /> : null}
      {helpOpen ? <HelpCenter initialArticle={helpOpen.article} onClose={() => setHelpOpen(null)} /> : null}
    </>
  );
}

function Tour({ steps, onClose }: { steps: TourStep[]; onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = steps[index];

  const measure = useCallback(() => {
    const element = document.querySelector(step.target);
    setRect(element ? element.getBoundingClientRect() : null);
  }, [step.target]);

  useLayoutEffect(() => {
    const element = document.querySelector(step.target);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
    const handle = window.setTimeout(measure, 320);
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(handle);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure, step.target]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") setIndex((current) => Math.min(current + 1, steps.length - 1));
      if (event.key === "ArrowLeft") setIndex((current) => Math.max(current - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, steps.length]);

  const pad = 8;
  const box = rect
    ? { top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }
    : null;
  // Card below the highlight when there is room, otherwise above it.
  const cardTop = box ? (box.top + box.height + 220 < window.innerHeight ? box.top + box.height + 12 : Math.max(12, box.top - 200)) : window.innerHeight / 2 - 90;
  const cardLeft = box ? Math.min(Math.max(12, box.left), window.innerWidth - 332) : window.innerWidth / 2 - 160;
  const last = index === steps.length - 1;

  return (
    <div aria-label="Tour guiado" aria-modal="true" className="tour" role="dialog">
      {box ? <div className="tour-highlight" style={box} /> : <div className="tour-dim" />}
      <div className="tour-card" style={{ top: cardTop, left: cardLeft }}>
        <div className="tour-card-head">
          <Mascot size={30} />
          <small>{index + 1} de {steps.length}</small>
          <button aria-label="Fechar tour" className="icon-button" onClick={onClose} type="button"><X size={16} /></button>
        </div>
        <strong>{step.title}</strong>
        <p>{step.text}</p>
        <div className="tour-card-actions">
          {index > 0 ? <button className="secondary-button" onClick={() => setIndex(index - 1)} type="button">Voltar</button> : <span />}
          <button className="primary-button" onClick={() => (last ? onClose() : setIndex(index + 1))} type="button">
            {last ? "Concluir" : "Próximo"}
          </button>
        </div>
      </div>
    </div>
  );
}

function HelpCenter({ initialArticle, onClose }: { initialArticle?: string; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [articleId, setArticleId] = useState<string | undefined>(initialArticle);
  const article = ARTICLES.find((item) => item.id === articleId);
  const results = useMemo(() => {
    const terms = query.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    if (!terms) return ARTICLES;
    return ARTICLES.filter((item) => {
      const haystack = [item.title, item.summary, ...item.body.flatMap((part) => [part.heading, part.text, ...(part.steps ?? [])])]
        .join(" ")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "");
      return terms.split(/\s+/).every((term) => haystack.includes(term));
    });
  }, [query]);

  return (
    <Modal onClose={onClose} size="wide" title={article ? article.title : "Central de ajuda"}>
      {article ? (
        <article className="help-article">
          <button className="link-button help-back" onClick={() => setArticleId(undefined)} type="button">
            <ArrowLeft size={15} /> Todos os artigos
          </button>
          <p className="help-summary">{article.summary}</p>
          {article.body.map((part, index) => (
            <section key={index}>
              {part.heading ? <h3>{part.heading}</h3> : null}
              {part.text ? <p>{part.text}</p> : null}
              {part.steps ? <ol>{part.steps.map((item) => <li key={item}>{item}</li>)}</ol> : null}
            </section>
          ))}
          {article.link ? (
            <button className="primary-button" onClick={() => { onClose(); openAppLink(article.link!.href); }} type="button">
              {article.link.label}
            </button>
          ) : null}
        </article>
      ) : (
        <div className="help-center">
          <label className="help-search">
            <Search size={16} />
            <span className="sr-only">Buscar na ajuda</span>
            <input autoFocus onChange={(event) => setQuery(event.target.value)} placeholder="Buscar: WhatsApp, pacote, equipe…" value={query} />
          </label>
          {results.length ? (
            <ul className="help-list">
              {results.map((item) => (
                <li key={item.id}>
                  <button onClick={() => setArticleId(item.id)} type="button">
                    <strong>{item.title}</strong>
                    <small>{item.summary}</small>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="help-empty">Nada encontrado para “{query}”. Tente outra palavra.</p>
          )}
        </div>
      )}
    </Modal>
  );
}

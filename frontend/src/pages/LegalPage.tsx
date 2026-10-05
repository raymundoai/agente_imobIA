import { BrandMark } from "../components/BrandMark";
import { type LegalDocument, PRIVACY, TERMS, TERMS_VERSION } from "../legal/content";

/** Public page for the terms of use (/termos) and the privacy policy (/privacidade). */
export function LegalPage({ kind }: { kind: "terms" | "privacy" }) {
  const doc: LegalDocument = kind === "terms" ? TERMS : PRIVACY;
  const updated = new Date(`${TERMS_VERSION}T12:00:00`).toLocaleDateString("pt-BR", { dateStyle: "long" });
  return (
    <main className="legal-page">
      <header className="legal-header">
        <a className="legal-brand" href="/">
          <span className="brand-icon"><BrandMark /></span>
          <strong>ImmobIA</strong>
        </a>
        <nav>
          <a aria-current={kind === "terms" ? "page" : undefined} href="/termos">Termos de uso</a>
          <a aria-current={kind === "privacy" ? "page" : undefined} href="/privacidade">Privacidade</a>
        </nav>
      </header>
      <article className="legal-body">
        <h1>{doc.title}</h1>
        <p className="legal-updated">Atualizado em {updated}</p>
        <p className="legal-intro">{doc.intro}</p>
        {doc.sections.map((section) => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            {section.paragraphs?.map((text) => <p key={text}>{text}</p>)}
            {section.items ? <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul> : null}
          </section>
        ))}
      </article>
    </main>
  );
}

import type { ReactNode } from "react";
import { BrandMark } from "./BrandMark";

/**
 * Entry screens (login, signup, invitation, admin login). The brand panel shows the symbol and
 * the name large on the petróleo field, with the product promise underneath.
 */
export function AuthLayout({ children, badge, tagline = "Atende seus leads no WhatsApp, 24 horas." }: {
  children: ReactNode;
  badge?: string;
  tagline?: string;
}) {
  return (
    <main className="auth-page">
      <aside className="auth-brand">
        <div className="auth-brand-center">
          <BrandMark className="auth-brand-symbol" />
          <strong className="auth-brand-name">ImmobIA</strong>
          {badge ? <span className="auth-brand-badge">{badge}</span> : null}
          <p className="auth-brand-tagline">{tagline}</p>
        </div>
        <p className="auth-brand-note">Atendimento com IA, carteira de imóveis e parcerias entre imobiliárias, em um só lugar.</p>
      </aside>
      <section className="auth-content">
        {children}
        <nav aria-label="Documentos" className="auth-legal">
          <a href="/termos">Termos de uso</a>
          <a href="/privacidade">Privacidade</a>
        </nav>
      </section>
    </main>
  );
}

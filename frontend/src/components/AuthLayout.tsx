import type { ReactNode } from "react";
import { BrandMark } from "./BrandMark";

/**
 * Entry screens (login, signup, invitation, admin login). The brand panel carries the
 * one loud element of the identity: a Brazilian real estate sign that reads "ATENDE"
 * instead of "VENDE", because answering leads is what the product does.
 */
export function AuthLayout({ children, signWord = "ATENDE", signLine = "seus leads no WhatsApp, 24 horas" }: {
  children: ReactNode;
  signWord?: string;
  signLine?: string;
}) {
  return (
    <main className="auth-page">
      <aside className="auth-brand">
        <div className="auth-brand-mark">
          <span className="brand-icon"><BrandMark /></span>
          <strong>ImmobIA</strong>
        </div>
        <figure className="auth-sign-wrap">
          <div aria-label={`Placa: ${signWord} ${signLine}`} className="auth-sign" role="img">
            <span className="auth-sign-word">{signWord}</span>
            <span className="auth-sign-line">{signLine}</span>
            <span className="auth-sign-foot">ImmobIA</span>
          </div>
          <span aria-hidden="true" className="auth-sign-post" />
        </figure>
        <p className="auth-brand-note">Atendimento com IA, carteira de imóveis e parcerias entre imobiliárias, em um só lugar.</p>
      </aside>
      <section className="auth-content">{children}</section>
    </main>
  );
}

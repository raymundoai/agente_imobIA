import { useEffect, useState } from "react";
import { QUOTA_EXHAUSTED_EVENT, request } from "../api/client";
import type { BillingOverview } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { openAppLink } from "../lib/appNavigation";
import { Modal } from "./Modal";

/** Shown whenever an action is refused because the month's allowance ran out. */
export function QuotaExhaustedModal() {
  const { token } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [status, setStatus] = useState<BillingOverview["status"] | null>(null);
  const [canBuyPacks, setCanBuyPacks] = useState(false);

  useEffect(() => {
    const onExhausted = (event: Event) => {
      setMessage((event as CustomEvent<{ message: string }>).detail.message);
      request<BillingOverview>("/billing", {}, token)
        .then((overview) => {
          setStatus(overview.status);
          setCanBuyPacks(overview.packs.length > 0);
        })
        .catch(() => setStatus(null));
    };
    window.addEventListener(QUOTA_EXHAUSTED_EVENT, onExhausted);
    return () => window.removeEventListener(QUOTA_EXHAUSTED_EVENT, onExhausted);
  }, [token]);

  if (!message) return null;
  const close = () => setMessage(null);
  const go = (href: string) => {
    close();
    openAppLink(href);
  };
  const noPlan = status === "pending" || status === "cancelled";

  return (
    <Modal
      description={noPlan ? "Escolha um plano para liberar o atendimento com IA, as buscas e a otimização de fotos." : message}
      footer={
        noPlan ? (
          <>
            <button className="secondary-button" onClick={close} type="button">Agora não</button>
            <button className="primary-button" onClick={() => go("/configuracoes?aba=billing")} type="button">Escolher plano</button>
          </>
        ) : (
          <>
            <button className="secondary-button" onClick={() => go("/configuracoes?aba=billing")} type="button">Ver planos maiores</button>
            {canBuyPacks ? (
              <button className="primary-button" onClick={() => go("/configuracoes?aba=billing#pacotes")} type="button">Comprar pacote</button>
            ) : null}
          </>
        )
      }
      onClose={close}
      title={noPlan ? "Plano necessário" : "Franquia do mês esgotada"}
    >
      <p className="modal-text">
        {noPlan
          ? "Sua conta ainda não tem um plano ativo."
          : "Você pode comprar um pacote avulso agora, com créditos liberados assim que o pagamento é confirmado, ou mudar para um plano com franquia maior."}
      </p>
    </Modal>
  );
}

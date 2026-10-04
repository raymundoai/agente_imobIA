import type { ReactNode } from "react";
import { Building2, UserRound } from "lucide-react";
import { type BusinessIdentity, type BusinessType } from "../lib/businessIdentity";
import { formatDocument } from "../lib/format";

export { type BusinessIdentity, identityFromProfile, identityToProfile, validateIdentity } from "../lib/businessIdentity";

export function BusinessIdentityFields({
  value,
  onChange,
}: {
  value: BusinessIdentity;
  onChange: (value: BusinessIdentity) => void;
}) {
  const isCnpj = value.document_type === "cnpj";

  function chooseBusiness(business_type: BusinessType) {
    // Follow the choice with the matching document while nothing has been typed yet.
    const untouched = !value.cpf_number && !value.cnpj_number;
    onChange({
      ...value,
      business_type,
      document_type: untouched ? (business_type === "agency" ? "cnpj" : "cpf") : value.document_type,
    });
  }

  return (
    <div className="identity-fields">
      <div className="choice-cards" role="radiogroup" aria-label="Como você trabalha">
        <ChoiceCard
          checked={value.business_type === "broker"}
          icon={<UserRound size={20} />}
          onSelect={() => chooseBusiness("broker")}
          text="Trabalho por conta própria"
          title="Corretor autônomo"
        />
        <ChoiceCard
          checked={value.business_type === "agency"}
          icon={<Building2 size={20} />}
          onSelect={() => chooseBusiness("agency")}
          text="Tenho uma equipe ou empresa"
          title="Imobiliária"
        />
      </div>

      <div className="document-fields">
        <div className="segmented" role="radiogroup" aria-label="Documento">
          {(["cpf", "cnpj"] as const).map((type) => (
            <button
              aria-checked={value.document_type === type}
              className={value.document_type === type ? "active" : undefined}
              key={type}
              onClick={() => onChange({ ...value, document_type: type })}
              role="radio"
              type="button"
            >
              {type.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="form-grid">
          <label key={`${value.document_type}-name`}>
            {isCnpj ? "Razão social" : "Nome completo"}
            <input
              autoComplete={isCnpj ? "organization" : "name"}
              onChange={(event) => onChange({ ...value, [isCnpj ? "cnpj_name" : "cpf_name"]: event.target.value })}
              placeholder={isCnpj ? "Ex.: Eugênia Imóveis Ltda." : "Seu nome completo"}
              value={isCnpj ? value.cnpj_name : value.cpf_name}
            />
          </label>
          <label key={`${value.document_type}-number`}>
            <span>{isCnpj ? "CNPJ" : "CPF"} <span className="optional">(pode ficar para depois)</span></span>
            <input
              inputMode="numeric"
              onChange={(event) =>
                onChange({ ...value, [isCnpj ? "cnpj_number" : "cpf_number"]: formatDocument(event.target.value, value.document_type) })
              }
              placeholder={isCnpj ? "00.000.000/0000-00" : "000.000.000-00"}
              value={isCnpj ? value.cnpj_number : value.cpf_number}
            />
          </label>
        </div>
      </div>
    </div>
  );
}

function ChoiceCard({
  checked,
  icon,
  title,
  text,
  onSelect,
}: {
  checked: boolean;
  icon: ReactNode;
  title: string;
  text: string;
  onSelect: () => void;
}) {
  return (
    <button aria-checked={checked} className={checked ? "choice-card active" : "choice-card"} onClick={onSelect} role="radio" type="button">
      <span className="choice-card-icon">{icon}</span>
      <span>
        <strong>{title}</strong>
        <small>{text}</small>
      </span>
    </button>
  );
}

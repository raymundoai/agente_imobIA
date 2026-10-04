import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

/** Password field with a show/hide toggle, so a single entry is enough to get it right. */
export function PasswordInput({
  value,
  onChange,
  autoComplete,
  minLength,
}: {
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  minLength?: number;
}) {
  const [visible, setVisible] = useState(false);
  const enough = minLength ? value.length >= minLength : false;
  return (
    <>
      <span className="password-field">
        <input autoComplete={autoComplete} onChange={(event) => onChange(event.target.value)} type={visible ? "text" : "password"} value={value} />
        <button
          aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
          aria-pressed={visible}
          className="password-toggle"
          onClick={() => setVisible((current) => !current)}
          type="button"
        >
          {visible ? <Eye size={17} /> : <EyeOff size={17} />}
        </button>
      </span>
      {minLength ? (
        <small className={enough ? "field-hint password-ok" : "field-hint"} aria-live="polite">
          {enough ? "Tamanho ok." : `Mínimo de ${minLength} caracteres${value.length ? ` (faltam ${minLength - value.length})` : ""}.`}
        </small>
      ) : null}
    </>
  );
}

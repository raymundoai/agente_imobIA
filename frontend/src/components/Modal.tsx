import { type ReactNode, useEffect, useRef } from "react";
import { X } from "lucide-react";

/** Overlay dialog: closes on Escape or a click outside, and moves focus inside on open. */
export function Modal({
  title,
  description,
  onClose,
  children,
  footer,
  size = "compact",
}: {
  title: string;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "compact" | "wide";
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLElement>("button, input, textarea, select, a[href]")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div aria-labelledby="modal-title" aria-modal="true" className={`app-modal app-modal-${size}`} ref={dialogRef} role="dialog">
        <header className="app-modal-header">
          <div>
            <h2 id="modal-title">{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button aria-label="Fechar" className="icon-button" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </header>
        <div className="app-modal-body">{children}</div>
        {footer ? <footer className="app-modal-footer">{footer}</footer> : null}
      </div>
    </div>
  );
}

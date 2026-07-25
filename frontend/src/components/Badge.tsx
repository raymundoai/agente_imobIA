import type { ReactNode } from "react";

type BadgeVariant = "default" | "success" | "accent" | "muted" | "danger";

export function Badge({
  children,
  variant = "default",
}: {
  children: ReactNode;
  variant?: BadgeVariant;
}) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}

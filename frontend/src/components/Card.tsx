import type { ComponentPropsWithoutRef } from "react";

export function Card({
  children,
  className = "",
  ...props
}: ComponentPropsWithoutRef<"article">) {
  return <article className={`card ${className}`} {...props}>{children}</article>;
}

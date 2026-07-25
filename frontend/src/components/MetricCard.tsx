import type { LucideIcon } from "lucide-react";
import { formatNumber } from "../lib/format";

export function MetricCard({
  label,
  value,
  icon: Icon,
  detail,
  variation,
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  detail?: string;
  variation?: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-card-header">
        <span>{label}</span>
        <div className="metric-icon">
          <Icon size={18} />
        </div>
      </div>
      <strong>{typeof value === "number" ? formatNumber(value) : value}</strong>
      <div className="metric-footer">
        {variation ? <span className="metric-variation">{variation}</span> : null}
        {detail ? <small>{detail}</small> : null}
      </div>
    </article>
  );
}

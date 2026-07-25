import { ExternalLink, Home } from "lucide-react";
import type { Property } from "../api/types";
import { formatCurrency, labelOrDash } from "../lib/format";
import { Badge } from "./Badge";
import { Card } from "./Card";

export function PropertyCard({ property }: { property: Property }) {
  const firstImage = property.images.find((image) => typeof image.url === "string")?.url;

  return (
    <Card className="property-card">
      <div className="property-media">
        {typeof firstImage === "string" ? <img alt={property.title} src={firstImage} /> : <Home size={26} />}
      </div>
      <div className="property-body">
        <div className="property-title-row">
          <h3>{property.title}</h3>
          <Badge variant="muted">{labelOrDash(property.purpose)}</Badge>
        </div>
        <p>
          {property.neighborhood ? `${property.neighborhood}, ` : ""}
          {property.city}
        </p>
        <div className="property-meta">
          <strong>{formatCurrency(property.price)}</strong>
          <span>{labelOrDash(property.property_type)}</span>
        </div>
        {property.source_url ? (
          <a className="property-link" href={property.source_url} rel="noreferrer" target="_blank">
            Abrir origem
            <ExternalLink size={14} />
          </a>
        ) : null}
      </div>
    </Card>
  );
}

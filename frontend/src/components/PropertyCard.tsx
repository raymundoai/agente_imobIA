import { ExternalLink, Home, Share2 } from "lucide-react";
import type { Property } from "../api/types";
import { formatCurrency } from "../lib/format";
import { propertyKindPhrase } from "../lib/propertyLabels";
import { Card } from "./Card";

export function PropertyCard({
  property,
  imageUrl,
  onClick,
}: {
  property: Property;
  imageUrl?: string;
  onClick?: () => void;
}) {
  const price = property.price ?? property.sale_price ?? property.rent_price;
  const location = [property.neighborhood, property.city].filter(Boolean).join(", ");
  return (
    <Card className="property-card">
      <div
        className="property-card-button"
        onClick={onClick}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") onClick?.();
        }}
        role="button"
        tabIndex={0}
      >
        <div className="property-media">
          {imageUrl ? <img alt="" src={imageUrl} /> : <Home aria-hidden size={28} />}
          {property.network_shared ? (
            <span className="network-chip" title="Compartilhado na Rede ImmobIA">
              <Share2 size={12} /> Na Rede
            </span>
          ) : null}
          <span className={price ? "property-price" : "property-price missing"}>
            {price ? formatCurrency(price) : "Sem preço"}
          </span>
        </div>
        <div className="property-body">
          <p className="property-kind">{propertyKindPhrase(property.property_type, property.purpose)}</p>
          <h3>{property.title}</h3>
          {location ? <p>{location}</p> : null}
          <PropertyFacts property={property} />
          {property.source_url ? (
            <a className="property-link" href={property.source_url} rel="noreferrer" target="_blank">
              Abrir origem
              <ExternalLink size={14} />
            </a>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

type FactSource = Pick<Property, "area" | "bedrooms" | "parking_spaces">;

/** Spec-sheet line shared by portfolio and network cards: "72 m²  2 quartos  1 vaga". */
export function PropertyFacts({ property }: { property: FactSource }) {
  const facts = [
    property.area ? [property.area, "m²"] : null,
    property.bedrooms != null ? [property.bedrooms, property.bedrooms === 1 ? "quarto" : "quartos"] : null,
    property.parking_spaces != null ? [property.parking_spaces, property.parking_spaces === 1 ? "vaga" : "vagas"] : null,
  ].filter((fact): fact is [number, string] => fact !== null);
  if (!facts.length) return null;
  return (
    <p className="property-facts">
      {facts.map(([value, unit]) => (
        <span key={unit}>
          {value}
          <small>{unit}</small>
        </span>
      ))}
    </p>
  );
}

type SearchPurpose = "buy" | "rent" | string | null;

type SearchResultPrices = {
  purpose: string | null;
  price: string | null;
  sale_price: string | null;
  rent_price: string | null;
};

export type SearchPricePresentation = {
  primary: string | null;
  primaryLabel: "Aluguel" | "Venda";
  alternative: string | null;
  alternativeLabel: "Também à venda por" | "Também para aluguel por";
};

export function searchPricePresentation(
  demandPurpose: SearchPurpose,
  result: SearchResultPrices,
): SearchPricePresentation {
  const isRent = demandPurpose === "rent";
  const fallbackMatchesPurpose = isRent
    ? result.purpose === "rent" || result.purpose === "both"
    : result.purpose === "buy" || result.purpose === "both";
  const primary = isRent
    ? result.rent_price ?? (fallbackMatchesPurpose ? result.price : null)
    : result.sale_price ?? (fallbackMatchesPurpose ? result.price : null);
  const possibleAlternative = isRent ? result.sale_price : result.rent_price;
  return {
    primary,
    primaryLabel: isRent ? "Aluguel" : "Venda",
    alternative: possibleAlternative !== primary ? possibleAlternative : null,
    alternativeLabel: isRent ? "Também à venda por" : "Também para aluguel por",
  };
}

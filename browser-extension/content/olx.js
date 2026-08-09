(() => {
  if (globalThis.__imobiaOlxReaderInstalled) return;
  globalThis.__imobiaOlxReaderInstalled = true;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "IMOBIA_READ_RENDERED_LISTINGS") return false;
    sendResponse({ records: readListings() });
    return false;
  });

  function readListings() {
    const records = [];
    const seen = new Set();
    const anchors = document.querySelectorAll('a[href*="/d/"], a[href*="/anuncio/"]');
    for (const anchor of anchors) {
      const canonicalUrl = cleanUrl(anchor.href);
      if (!canonicalUrl || seen.has(canonicalUrl) || !looksLikeListing(canonicalUrl)) continue;
      const card = closestCard(anchor);
      const rawText = cleanText(card?.innerText || anchor.innerText || "");
      if (rawText.length < 12) continue;
      const title = cleanText(
        card?.querySelector("h2, h3, [role='heading']")?.textContent ||
          anchor.getAttribute("aria-label") ||
          rawText.split("\n")[0],
      );
      const image = card?.querySelector("img")?.currentSrc || card?.querySelector("img")?.src;
      records.push({
        sourceListingId: listingId(canonicalUrl),
        canonicalUrl,
        title: title || "Imóvel na OLX",
        priceText: rawText.match(/R\$\s*[\d.]+(?:,\d{2})?/)?.[0] || null,
        locationText: locationText(card, rawText),
        primaryImageUrl: validImage(image),
        rawText: rawText.slice(0, 2000),
      });
      seen.add(canonicalUrl);
    }
    return records;
  }

  function closestCard(anchor) {
    return (
      anchor.closest("[data-ds-component='DS-AdCard'], article, li, section") ||
      anchor.parentElement?.parentElement ||
      anchor
    );
  }

  function locationText(card, rawText) {
    const explicit = card?.querySelector(
      "[data-testid*='location'], [class*='location'], [aria-label*='Localização']",
    )?.textContent;
    if (explicit) return cleanText(explicit);
    return rawText
      .split("\n")
      .map(cleanText)
      .find((line) => /\b[A-Z]{2}\b/.test(line) && line.length < 140) || null;
  }

  function looksLikeListing(url) {
    return /\/d\//i.test(url) || /-\d{7,}(?:\/)?$/i.test(new URL(url).pathname);
  }

  function listingId(url) {
    return new URL(url).pathname.match(/(\d{7,})(?:\/)?$/)?.[1] || null;
  }

  function cleanUrl(value) {
    try {
      const url = new URL(value, location.href);
      if (!/(^|\.)olx\.com\.br$/i.test(url.hostname)) return null;
      url.search = "";
      url.hash = "";
      return url.toString();
    } catch {
      return null;
    }
  }

  function validImage(value) {
    return value && !value.startsWith("data:") ? value : null;
  }

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }
})();

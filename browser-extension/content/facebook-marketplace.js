(() => {
  if (globalThis.__imobiaFacebookReaderInstalled) return;
  globalThis.__imobiaFacebookReaderInstalled = true;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "IMOBIA_READ_RENDERED_LISTINGS") return false;
    sendResponse({ records: readListings() });
    return false;
  });

  function readListings() {
    const records = [];
    const seen = new Set();
    for (const anchor of document.querySelectorAll('a[href*="/marketplace/item/"]')) {
      const canonicalUrl = cleanUrl(anchor.href);
      if (!canonicalUrl || seen.has(canonicalUrl)) continue;
      const card = marketplaceCard(anchor);
      const rawText = cleanText(card?.innerText || anchor.innerText || "");
      if (rawText.length < 8) continue;
      const lines = (card?.innerText || anchor.innerText || "")
        .split("\n")
        .map(cleanText)
        .filter(Boolean);
      const priceText = lines.find((line) => /^(R\$\s*)?[\d.]+(?:,\d{2})?$/.test(line)) ||
        rawText.match(/R\$\s*[\d.]+(?:,\d{2})?/)?.[0] ||
        null;
      const title = lines.find((line) => line !== priceText && line.length > 4) || "Imóvel no Marketplace";
      const image = card?.querySelector("img")?.currentSrc || card?.querySelector("img")?.src;
      records.push({
        sourceListingId: new URL(canonicalUrl).pathname.match(/\/item\/(\d+)/)?.[1] || null,
        canonicalUrl,
        title,
        priceText,
        locationText: lines.find((line) => /\b(?:SP|RS)\b/i.test(line) && line.length < 140) || null,
        primaryImageUrl: image && !image.startsWith("data:") ? image : null,
        rawText: rawText.slice(0, 2000),
      });
      seen.add(canonicalUrl);
    }
    return records;
  }

  function marketplaceCard(anchor) {
    let node = anchor;
    for (let level = 0; node && level < 7; level += 1, node = node.parentElement) {
      const length = cleanText(node.innerText).length;
      if (length >= 20 && length <= 1400 && node.querySelector("img")) return node;
    }
    return anchor;
  }

  function cleanUrl(value) {
    try {
      const url = new URL(value, location.href);
      if (!/(^|\.)facebook\.com$/i.test(url.hostname)) return null;
      const id = url.pathname.match(/\/marketplace\/item\/(\d+)/)?.[1];
      return id ? `https://www.facebook.com/marketplace/item/${id}/` : null;
    } catch {
      return null;
    }
  }

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }
})();

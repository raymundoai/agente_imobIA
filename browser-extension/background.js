const SOURCES = [
  {
    id: "olx",
    host: /(^|\.)olx\.com\.br$/i,
    script: "content/olx.js",
  },
  {
    id: "facebook_marketplace",
    host: /(^|\.)facebook\.com$/i,
    script: "content/facebook-marketplace.js",
  },
];

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "IMOBIA_CAPTURE_ACTIVE_TAB") return false;
  captureActiveTab().then(sendResponse).catch((error) => {
    sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) });
  });
  return true;
});

async function captureActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) throw new Error("Nenhuma guia ativa disponível.");

  const url = new URL(tab.url);
  const source = SOURCES.find((candidate) => candidate.host.test(url.hostname));
  if (!source) {
    throw new Error("Abra uma busca da OLX ou do Facebook Marketplace nesta guia.");
  }
  if (source.id === "facebook_marketplace" && !url.pathname.includes("/marketplace")) {
    throw new Error("Abra o Marketplace do Facebook antes de capturar.");
  }

  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [source.script] });
  const batch = await chrome.tabs.sendMessage(tab.id, { type: "IMOBIA_READ_RENDERED_LISTINGS" });
  const capturedAt = new Date().toISOString();
  const payload = {
    schemaVersion: 1,
    sourceId: source.id,
    sourcePageUrl: tab.url,
    capturedAt,
    records: Array.isArray(batch?.records) ? batch.records : [],
  };
  await chrome.storage.local.set({ lastCapture: payload });
  return { ok: true, payload };
}

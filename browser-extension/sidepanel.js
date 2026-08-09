const captureButton = document.querySelector("#capture");
const downloadButton = document.querySelector("#download");
const statusNode = document.querySelector("#status");
const summaryNode = document.querySelector("#summary");
const sourceNode = document.querySelector("#source");
const countNode = document.querySelector("#count");
const resultsNode = document.querySelector("#results");
let currentPayload = null;

captureButton.addEventListener("click", async () => {
  captureButton.disabled = true;
  setStatus("Lendo os anúncios visíveis…");
  try {
    const response = await chrome.runtime.sendMessage({ type: "IMOBIA_CAPTURE_ACTIVE_TAB" });
    if (!response?.ok) throw new Error(response?.error || "Não foi possível capturar esta página.");
    render(response.payload);
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), true);
  } finally {
    captureButton.disabled = false;
  }
});

downloadButton.addEventListener("click", () => {
  if (!currentPayload) return;
  const blob = new Blob([JSON.stringify(currentPayload, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `imobia-${currentPayload.sourceId}-${Date.now()}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});

chrome.storage.local.get("lastCapture").then(({ lastCapture }) => {
  if (lastCapture) render(lastCapture);
});

function render(payload) {
  currentPayload = payload;
  sourceNode.textContent = payload.sourceId === "olx" ? "OLX" : "Facebook Marketplace";
  countNode.textContent = `${payload.records.length} anúncio(s)`;
  resultsNode.replaceChildren(
    ...payload.records.slice(0, 30).map((record) => {
      const row = document.createElement("div");
      row.className = "result";
      const image = document.createElement("img");
      image.alt = "";
      if (record.primaryImageUrl) image.src = record.primaryImageUrl;
      const content = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = record.title;
      const price = document.createElement("span");
      price.textContent = record.priceText || "Preço não identificado";
      content.append(title, price);
      row.append(image, content);
      return row;
    }),
  );
  summaryNode.hidden = false;
  setStatus(payload.records.length ? "Captura pronta para revisão." : "Nenhum card visível foi reconhecido.");
}

function setStatus(value, error = false) {
  statusNode.textContent = value;
  statusNode.classList.toggle("error", error);
}

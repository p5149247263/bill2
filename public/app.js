const form = document.getElementById("compare-form");
const statusEl = document.getElementById("status");
const previewBtn = document.getElementById("preview-btn");
const downloadBtn = document.getElementById("download-btn");
const previewSection = document.getElementById("preview-section");
const previewTable = document.getElementById("preview-table");

function setStatus(msg, isError = false) {
  statusEl.textContent = msg;
  statusEl.style.color = isError ? "#b00020" : "#1a4d1a";
}

function getFormData() {
  const oldBill = document.getElementById("old_bill").files[0];
  const newBill = document.getElementById("new_bill").files[0];
  const oldLabel = document.getElementById("old_label").value.trim();
  const newLabel = document.getElementById("new_label").value.trim();

  if (!oldBill || !newBill) {
    throw new Error("Please upload both PDF files.");
  }

  const formData = new FormData();
  formData.append("old_bill", oldBill);
  formData.append("new_bill", newBill);
  if (oldLabel) formData.append("old_label", oldLabel);
  if (newLabel) formData.append("new_label", newLabel);
  return formData;
}

function renderTable(header, rows) {
  const thead = document.createElement("thead");
  const trHead = document.createElement("tr");
  header.forEach((cell) => {
    const th = document.createElement("th");
    th.textContent = cell;
    trHead.appendChild(th);
  });
  thead.appendChild(trHead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((cell) => {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  previewTable.replaceChildren(thead, tbody);
  previewSection.classList.remove("hidden");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("");
  previewBtn.disabled = true;
  downloadBtn.disabled = true;

  try {
    const formData = getFormData();
    setStatus("Generating preview...");
    const response = await fetch("/api/preview", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Preview request failed.");
    }

    const payload = await response.json();
    renderTable(payload.header, payload.rows);
    setStatus("Preview generated.");
  } catch (err) {
    setStatus(err.message || "Failed to preview comparison.", true);
  } finally {
    previewBtn.disabled = false;
    downloadBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", async () => {
  setStatus("");
  previewBtn.disabled = true;
  downloadBtn.disabled = true;

  try {
    const formData = getFormData();
    setStatus("Generating Excel...");
    const response = await fetch("/api/compare", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Excel request failed.");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "gas_bill_comparison.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setStatus("Excel generated and downloaded.");
  } catch (err) {
    setStatus(err.message || "Failed to generate Excel.", true);
  } finally {
    previewBtn.disabled = false;
    downloadBtn.disabled = false;
  }
});

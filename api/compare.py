from flask import Flask, Response, jsonify, request

from api.gas_bill_core import build_comparison_table, build_comparison_xlsx

app = Flask(__name__)


@app.get("/")
def home():
    return Response(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Gas Bill PDF Compare</title>
    <style>
      body { font-family: Arial, sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; }
      .card { border: 1px solid #ddd; border-radius: 10px; padding: 16px; display: grid; gap: 10px; }
      .actions { display: flex; gap: 8px; }
      button { padding: 10px 12px; border: 0; border-radius: 8px; background: #0b66c3; color: white; cursor: pointer; }
      button:disabled { opacity: .7; cursor: wait; }
      #status { min-height: 20px; margin-top: 10px; font-weight: 600; }
      table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 14px; }
      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
      th { background: #f3f7fb; }
      .hidden { display: none; }
    </style>
  </head>
  <body>
    <h1>Gas Bill PDF Compare</h1>
    <p>Upload old and new gas bill PDFs, preview table, and download Excel.</p>
    <form id="compare-form" class="card">
      <label>Older Bill PDF <input type="file" id="old_bill" accept="application/pdf" required /></label>
      <label>Newer Bill PDF <input type="file" id="new_bill" accept="application/pdf" required /></label>
      <label>Old Bill Label (optional) <input type="text" id="old_label" placeholder="January (12/12-1/13)" /></label>
      <label>New Bill Label (optional) <input type="text" id="new_label" placeholder="February (1/14-2/11)" /></label>
      <div class="actions">
        <button type="submit" id="preview-btn">Preview Table</button>
        <button type="button" id="download-btn">Download Excel</button>
      </div>
    </form>
    <p id="status"></p>
    <div id="preview-wrap" class="hidden">
      <h2>Comparison Preview</h2>
      <table id="preview-table"></table>
    </div>
    <script>
      const form = document.getElementById("compare-form");
      const statusEl = document.getElementById("status");
      const previewBtn = document.getElementById("preview-btn");
      const downloadBtn = document.getElementById("download-btn");
      const previewWrap = document.getElementById("preview-wrap");
      const previewTable = document.getElementById("preview-table");
      function setStatus(msg, err=false){ statusEl.textContent=msg; statusEl.style.color=err?"#b00020":"#1a4d1a"; }
      function formData() {
        const oldBill = document.getElementById("old_bill").files[0];
        const newBill = document.getElementById("new_bill").files[0];
        if (!oldBill || !newBill) throw new Error("Please upload both PDF files.");
        const fd = new FormData();
        fd.append("old_bill", oldBill); fd.append("new_bill", newBill);
        const oldLabel = document.getElementById("old_label").value.trim();
        const newLabel = document.getElementById("new_label").value.trim();
        if (oldLabel) fd.append("old_label", oldLabel);
        if (newLabel) fd.append("new_label", newLabel);
        return fd;
      }
      function renderTable(header, rows) {
        const thead = document.createElement("thead"); const trh = document.createElement("tr");
        header.forEach(c => { const th = document.createElement("th"); th.textContent = c; trh.appendChild(th); });
        thead.appendChild(trh);
        const tbody = document.createElement("tbody");
        rows.forEach(r => { const tr = document.createElement("tr"); r.forEach(c => { const td = document.createElement("td"); td.textContent = c; tr.appendChild(td); }); tbody.appendChild(tr); });
        previewTable.replaceChildren(thead, tbody); previewWrap.classList.remove("hidden");
      }
      form.addEventListener("submit", async (e) => {
        e.preventDefault(); previewBtn.disabled = downloadBtn.disabled = true; setStatus("Generating preview...");
        try {
          const res = await fetch("/api/preview", { method: "POST", body: formData() });
          const payload = await res.json();
          if (!res.ok) throw new Error(payload.error || "Preview failed");
          renderTable(payload.header, payload.rows); setStatus("Preview generated.");
        } catch (err) { setStatus(err.message || "Preview failed", true); }
        finally { previewBtn.disabled = downloadBtn.disabled = false; }
      });
      downloadBtn.addEventListener("click", async () => {
        previewBtn.disabled = downloadBtn.disabled = true; setStatus("Generating Excel...");
        try {
          const res = await fetch("/api/compare", { method: "POST", body: formData() });
          if (!res.ok) { const payload = await res.json().catch(() => ({})); throw new Error(payload.error || "Excel generation failed"); }
          const blob = await res.blob(); const url = URL.createObjectURL(blob);
          const a = document.createElement("a"); a.href = url; a.download = "gas_bill_comparison.xlsx"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
          setStatus("Excel generated and downloaded.");
        } catch (err) { setStatus(err.message || "Excel generation failed", true); }
        finally { previewBtn.disabled = downloadBtn.disabled = false; }
      });
    </script>
  </body>
</html>""",
        mimetype="text/html",
    )


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.post("/api/compare")
def compare():
    old_file = request.files.get("old_bill")
    new_file = request.files.get("new_bill")

    if not old_file or not new_file:
        return jsonify({"error": "Both files are required: old_bill and new_bill"}), 400

    old_label = request.form.get("old_label") or None
    new_label = request.form.get("new_label") or None

    try:
        xlsx_data = build_comparison_xlsx(
            old_pdf_bytes=old_file.read(),
            new_pdf_bytes=new_file.read(),
            old_label=old_label,
            new_label=new_label,
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to process PDFs: {str(exc)}"}), 400

    return Response(
        xlsx_data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="gas_bill_comparison.xlsx"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/preview")
def preview():
    old_file = request.files.get("old_bill")
    new_file = request.files.get("new_bill")

    if not old_file or not new_file:
        return jsonify({"error": "Both files are required: old_bill and new_bill"}), 400

    old_label = request.form.get("old_label") or None
    new_label = request.form.get("new_label") or None

    try:
        table = build_comparison_table(
            old_pdf_bytes=old_file.read(),
            new_pdf_bytes=new_file.read(),
            old_label=old_label,
            new_label=new_label,
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to process PDFs: {str(exc)}"}), 400

    return jsonify(table)

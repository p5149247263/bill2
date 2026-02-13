from flask import Flask, Response, jsonify, request

from api.gas_bill_core import build_comparison_table, build_comparison_xlsx

app = Flask(__name__)


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

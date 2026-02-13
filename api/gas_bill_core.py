import datetime as dt
import io
import re
import zipfile
from dataclasses import dataclass
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

from pypdf import PdfReader


@dataclass
class BillData:
    label: str
    billing_days: Optional[int]
    usage_ccf: Optional[float]
    customer_charge: Optional[float]
    consumption_per_ccf: List[float]
    rider_gcr_per_ccf: List[float]
    rider_wna_per_ccf: List[float]
    tax_and_fees_total: Optional[float]
    total_bill: Optional[float]


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).replace("\r", "\n")


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    all_text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return _normalize_text(all_text)


def _extract_first_number(text: str, patterns: List[str]) -> Optional[float]:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _parse_service_period(text: str) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    meter_line_match = re.search(
        r"Meter Serial # From To Previous Present\s*\n[0-9]+\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2})\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2})",
        text,
        flags=re.IGNORECASE,
    )
    if not meter_line_match:
        return None, None
    from_s, to_s = meter_line_match.groups()
    try:
        return dt.datetime.strptime(from_s, "%m/%d/%y").date(), dt.datetime.strptime(
            to_s, "%m/%d/%y"
        ).date()
    except ValueError:
        return None, None


def _billing_days_from_period(from_d: Optional[dt.date], to_d: Optional[dt.date]) -> Optional[int]:
    if not from_d or not to_d:
        return None
    delta = (to_d - from_d).days + 1
    return delta if delta > 0 else None


def _label_from_period(text: str, fallback: str) -> str:
    from_d, to_d = _parse_service_period(text)
    if not from_d or not to_d:
        return fallback
    month = to_d.strftime("%B")
    return f"{month} ({from_d.month}/{from_d.day}-{to_d.month}/{to_d.day})"


def _parse_wna_rate(text: str) -> List[float]:
    vals: List[float] = []
    for m in re.finditer(
        r"Rider WNA\s+[0-9.]+\s+@\s+([0-9.]+)(-?)",
        text,
        flags=re.IGNORECASE,
    ):
        rate = float(m.group(1))
        if m.group(2) == "-":
            rate = -rate
        vals.append(rate)
    return vals


def _parse_bill(pdf_bytes: bytes, label_override: Optional[str], fallback_label: str) -> BillData:
    text = _extract_text_from_pdf_bytes(pdf_bytes)
    from_d, to_d = _parse_service_period(text)
    label = label_override or _label_from_period(text, fallback_label)

    billing_days = _billing_days_from_period(from_d, to_d)
    usage_ccf = _extract_first_number(text, [r"Actual Usage in CCF:\s*([0-9]+(?:\.[0-9]+)?)"])
    customer_charge = _extract_first_number(text, [r"Customer Charge\s+([0-9]+(?:\.[0-9]+)?)"])
    consumption_rate = _extract_first_number(
        text, [r"Consump Chrg\s+[0-9.]+\s+@\s+([0-9]+(?:\.[0-9]+)?)"]
    )
    rider_gcr_rate = _extract_first_number(
        text, [r"Rider GCR\s+[0-9.]+\s+@\s+([0-9]+(?:\.[0-9]+)?)"]
    )
    rider_wna_rates = _parse_wna_rate(text)
    tax_and_fees_total = _extract_first_number(text, [r"TAX/FEE CHARGE TOTAL\s+([0-9]+(?:\.[0-9]+)?)"])
    total_bill = _extract_first_number(
        text,
        [
            r"CURRENT CHARGES\s+([0-9]+\.[0-9]{2})",
            r"TOTAL AMOUNT DUE\s*\$([0-9]+\.[0-9]{2})",
            r"Current Charges\s+([0-9]+\.[0-9]{2})",
        ],
    )

    return BillData(
        label=label,
        billing_days=billing_days,
        usage_ccf=usage_ccf,
        customer_charge=customer_charge,
        consumption_per_ccf=[] if consumption_rate is None else [consumption_rate],
        rider_gcr_per_ccf=[] if rider_gcr_rate is None else [rider_gcr_rate],
        rider_wna_per_ccf=rider_wna_rates,
        tax_and_fees_total=tax_and_fees_total,
        total_bill=total_bill,
    )


def _currency(value: Optional[float], decimals: int = 2, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    if value < 0:
        return f"-${abs_value:.{decimals}f}"
    sign = "+" if signed else ""
    return f"{sign}${abs_value:.{decimals}f}"


def _ccf(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{int(round(value))}" if abs(value - round(value)) < 1e-8 else f"{value:.2f}"


def _number_with_unit(value: Optional[int], unit: str) -> str:
    return "N/A" if value is None else f"{value} {unit}"


def _value_or_single(values: List[float], decimals: int = 5, signed: bool = False) -> str:
    if not values:
        return "N/A"
    lo, hi = min(values), max(values)
    if abs(lo - hi) < 1e-9:
        if lo < 0:
            return f"-${abs(lo):.{decimals}f}"
        sign = "+" if signed else ""
        return f"{sign}${abs(lo):.{decimals}f}"
    left = f"-${abs(lo):.{decimals}f}" if lo < 0 else f"{'+' if signed else ''}${abs(lo):.{decimals}f}"
    right = f"-${abs(hi):.{decimals}f}" if hi < 0 else f"{'+' if signed else ''}${abs(hi):.{decimals}f}"
    return f"{left} to {right}"


def _approx_variable_cost_range(b: BillData) -> Optional[Tuple[float, float]]:
    if not b.consumption_per_ccf or not b.rider_gcr_per_ccf or not b.rider_wna_per_ccf:
        return None
    vals = [
        c + g + w
        for c in b.consumption_per_ccf
        for g in b.rider_gcr_per_ccf
        for w in b.rider_wna_per_ccf
    ]
    return min(vals), max(vals)


def _effective_total_cost_per_ccf(b: BillData) -> Optional[float]:
    if b.total_bill is None or b.usage_ccf in (None, 0):
        return None
    return b.total_bill / b.usage_ccf


def _change_text(old: Optional[float], new: Optional[float], unit: str = "", money: bool = False) -> str:
    if old is None or new is None or abs(old) < 1e-12:
        return "N/A"
    delta = new - old
    pct = abs((delta / old) * 100.0)
    if abs(delta) < 1e-9:
        return "No change"
    if money:
        return f"{_currency(delta, signed=True)} ({'up' if delta > 0 else 'down'} {pct:.1f}%)"
    sign = "+" if delta > 0 else ""
    delta_s = f"{int(round(delta))}" if abs(delta - round(delta)) < 1e-8 else f"{delta:.2f}"
    suffix = f" {unit}" if unit else ""
    return f"{sign}{delta_s}{suffix} ({'up' if delta > 0 else 'down'} {pct:.1f}%)"


def _range_str(r: Optional[Tuple[float, float]]) -> str:
    if r is None:
        return "N/A"
    lo, hi = r
    if abs(lo - hi) < 1e-9:
        return f"${lo:.2f}"
    return f"${lo:.2f} to ${hi:.2f}"


def _build_rows(old: BillData, new: BillData) -> List[List[str]]:
    old_var = _approx_variable_cost_range(old)
    new_var = _approx_variable_cost_range(new)
    old_eff = _effective_total_cost_per_ccf(old)
    new_eff = _effective_total_cost_per_ccf(new)
    old_wna = old.rider_wna_per_ccf[0] if old.rider_wna_per_ccf else None
    new_wna = new.rider_wna_per_ccf[0] if new.rider_wna_per_ccf else None

    return [
        [
            "Billing Days",
            _number_with_unit(old.billing_days, "days"),
            _number_with_unit(new.billing_days, "days"),
            _change_text(
                float(old.billing_days) if old.billing_days is not None else None,
                float(new.billing_days) if new.billing_days is not None else None,
                "days",
            ),
        ],
        ["Usage (CCF)", _ccf(old.usage_ccf), _ccf(new.usage_ccf), _change_text(old.usage_ccf, new.usage_ccf, "CCF")],
        ["Customer Charge", _currency(old.customer_charge), _currency(new.customer_charge), _change_text(old.customer_charge, new.customer_charge, money=True)],
        [
            "Consumption Charge / CCF",
            _value_or_single(old.consumption_per_ccf),
            _value_or_single(new.consumption_per_ccf),
            _change_text(
                old.consumption_per_ccf[0] if old.consumption_per_ccf else None,
                new.consumption_per_ccf[0] if new.consumption_per_ccf else None,
                money=True,
            ),
        ],
        [
            "Rider GCR / CCF",
            _value_or_single(old.rider_gcr_per_ccf),
            _value_or_single(new.rider_gcr_per_ccf),
            _change_text(
                old.rider_gcr_per_ccf[0] if old.rider_gcr_per_ccf else None,
                new.rider_gcr_per_ccf[0] if new.rider_gcr_per_ccf else None,
                money=True,
            ),
        ],
        ["Rider WNA / CCF", _value_or_single(old.rider_wna_per_ccf, signed=True), _value_or_single(new.rider_wna_per_ccf, signed=True), _change_text(old_wna, new_wna, money=True)],
        [
            "Approx Variable Cost / CCF (before tax)",
            _range_str(old_var),
            _range_str(new_var),
            _change_text((sum(old_var) / 2) if old_var else None, (sum(new_var) / 2) if new_var else None, money=True),
        ],
        ["Tax & Fees Total", _currency(old.tax_and_fees_total), _currency(new.tax_and_fees_total), _change_text(old.tax_and_fees_total, new.tax_and_fees_total, money=True)],
        ["Effective Total Cost / CCF (all-in)", _currency(old_eff), _currency(new_eff), _change_text(old_eff, new_eff, money=True)],
        ["Total Bill", _currency(old.total_bill), _currency(new.total_bill), _change_text(old.total_bill, new.total_bill, money=True)],
    ]


def _cell_ref(row: int, col: int) -> str:
    letters = ""
    n = col
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def _xml_row(row_num: int, values: List[str]) -> str:
    cells = []
    for col, value in enumerate(values, start=1):
        v = escape(value if value is not None else "")
        ref = _cell_ref(row_num, col)
        cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>')
    return f'<row r="{row_num}">{"".join(cells)}</row>'


def _xlsx_bytes(rows: List[List[str]]) -> bytes:
    sheet_rows = [_xml_row(i + 1, row) for i, row in enumerate(rows)]
    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    {''.join(sheet_rows)}
  </sheetData>
</worksheet>
"""

    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Gas Bill Comparison" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""

    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""

    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return out.getvalue()


def build_comparison_xlsx(
    old_pdf_bytes: bytes,
    new_pdf_bytes: bytes,
    old_label: Optional[str] = None,
    new_label: Optional[str] = None,
) -> bytes:
    table = build_comparison_table(old_pdf_bytes, new_pdf_bytes, old_label, new_label)
    rows = [table["header"], *table["rows"]]
    return _xlsx_bytes(rows)


def build_comparison_table(
    old_pdf_bytes: bytes,
    new_pdf_bytes: bytes,
    old_label: Optional[str] = None,
    new_label: Optional[str] = None,
) -> dict:
    old_bill = _parse_bill(old_pdf_bytes, old_label, "Old Bill")
    new_bill = _parse_bill(new_pdf_bytes, new_label, "New Bill")
    return {
        "header": ["Item", old_bill.label, new_bill.label, "Change"],
        "rows": _build_rows(old_bill, new_bill),
    }

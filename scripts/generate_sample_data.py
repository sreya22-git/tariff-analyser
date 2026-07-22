"""One-off generator for the bundled demo workbook data/procurement_demo.xlsx.
Run with: python scripts/generate_sample_data.py
"""
from __future__ import annotations
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = BASE_DIR / "data" / "procurement_demo.xlsx"

COUNTRIES = ["China", "Vietnam", "Mexico", "India", "Germany", "South Korea", "Canada"]
CATEGORIES = ["Electronics Components", "Industrial Machinery", "Packaging Materials", "Textiles", "Metal Fabrication", "Plastics & Resins"]
CONTRACT_TYPES = ["Fixed Price", "Cost Plus", "Framework Agreement"]
PAYMENT_TERMS = ["Net 30", "Net 45", "Net 60"]

# HS codes: one per category, each with a country-of-origin lane
HS_CODES = {
    "Electronics Components": "8542.31",
    "Industrial Machinery": "8479.89",
    "Packaging Materials": "4819.10",
    "Textiles": "5208.12",
    "Metal Fabrication": "7326.90",
    "Plastics & Resins": "3901.20",
}

DEST_COUNTRY = "USA"

# 25 vendors spread across countries/categories
VENDOR_ROWS = []
for i in range(1, 26):
    country = random.choice(COUNTRIES)
    category = random.choice(CATEGORIES)
    VENDOR_ROWS.append({
        "VendorID": f"V{i:03d}",
        "VendorName": f"{category.split()[0]} Supply Co {i}",
        "Country": country,
        "Category": category,
        "SpendYTD": round(random.uniform(50000, 1_200_000), 2),
        "ContractType": random.choice(CONTRACT_TYPES),
        "PaymentTerms": random.choice(PAYMENT_TERMS),
    })
# Force a couple of single-source categories: only 1 vendor for Metal Fabrication
for v in VENDOR_ROWS:
    if v["Category"] == "Metal Fabrication":
        v["Category"] = "Plastics & Resins"
VENDOR_ROWS[0]["Category"] = "Metal Fabrication"
VENDOR_ROWS[0]["Country"] = "China"
vendor_df = pd.DataFrame(VENDOR_ROWS)

# HS Code Tariff Rates: lane = HSCode + CountryOfOrigin -> DestinationCountry
TARIFF_ROWS = []
for category, hs in HS_CODES.items():
    for country in COUNTRIES:
        prior = round(random.uniform(0, 5), 1)
        # Simulate broad tariff escalation for China-origin lanes (common real-world scenario)
        if country == "China":
            new_rate = round(prior + random.uniform(15, 25), 1)
        else:
            new_rate = round(prior + random.uniform(0, 3), 1)
        fta_eligible = country in ("Mexico", "Canada", "South Korea")
        TARIFF_ROWS.append({
            "HSCode": hs,
            "Description": category,
            "CountryOfOrigin": country,
            "DestinationCountry": DEST_COUNTRY,
            "DutyRatePct": new_rate,
            "PriorDutyRatePct": prior,
            "FTAEligible": fta_eligible,
            "FTAProgram": ("USMCA" if country in ("Mexico", "Canada") else ("KORUS" if country == "South Korea" else "")),
            "EffectiveDate": date(2026, 3, 1).isoformat(),
        })
tariff_df = pd.DataFrame(TARIFF_ROWS)

# PO Master: 220 purchase orders
PO_ROWS = []
po_start = date(2025, 10, 1)
for i in range(1, 221):
    vendor = random.choice(VENDOR_ROWS)
    category = vendor["Category"]
    hs = HS_CODES[category]
    country_of_origin = vendor["Country"] if random.random() > 0.08 else random.choice(COUNTRIES)  # occasional mismatch
    po_date = po_start + timedelta(days=random.randint(0, 210))
    status = random.choices(["Completed", "In Transit", "Returned", "Cancelled"], weights=[80, 12, 5, 3])[0]
    value = round(random.uniform(2000, 85000), 2)
    if random.random() < 0.03:
        value = round(value * random.uniform(4, 6), 2)  # rare outlier PO
    PO_ROWS.append({
        "PONumber": f"PO{i:05d}",
        "VendorID": vendor["VendorID"],
        "PODate": po_date.isoformat(),
        "ItemCategory": category,
        "HSCode": hs,
        "CountryOfOrigin": country_of_origin if random.random() > 0.02 else "",
        "POValue": value,
        "Currency": "USD",
        "Status": status,
    })
po_df = pd.DataFrame(PO_ROWS)

# Spend Invoice Detail: 1-2 invoices per PO
INV_ROWS = []
inv_counter = 1
tariff_lookup = {(r["HSCode"], r["CountryOfOrigin"]): r for r in TARIFF_ROWS}
for po in PO_ROWS:
    n_invoices = random.choice([1, 1, 2])
    for _ in range(n_invoices):
        qty = random.randint(50, 5000)
        unit_cost = round(po["POValue"] / max(qty, 1) * random.uniform(0.9, 1.1), 4)
        lane = tariff_lookup.get((po["HSCode"], po["CountryOfOrigin"]))
        duty_rate = lane["DutyRatePct"] if lane else 0.0
        fta_eligible = lane["FTAEligible"] if lane else False
        base_value = qty * unit_cost
        expected_duty = base_value * duty_rate / 100.0
        if fta_eligible and random.random() < 0.6:
            # FTA correctly claimed most of the time -> near-zero duty
            duty_paid = round(expected_duty * random.uniform(0.0, 0.05), 2)
        elif fta_eligible:
            # FTA eligible but not claimed (optimization opportunity)
            duty_paid = round(expected_duty * random.uniform(0.95, 1.05), 2)
        else:
            duty_paid = round(expected_duty * random.uniform(0.92, 1.08), 2)
        invoice_date = date.fromisoformat(po["PODate"]) + timedelta(days=random.randint(5, 30))
        INV_ROWS.append({
            "InvoiceID": f"INV{inv_counter:05d}",
            "PONumber": po["PONumber"],
            "VendorID": po["VendorID"],
            "HSCode": po["HSCode"],
            "Qty": qty,
            "UnitCost": unit_cost,
            "DutyPaid": duty_paid,
            "InvoiceDate": invoice_date.isoformat(),
        })
        inv_counter += 1
invoice_df = pd.DataFrame(INV_ROWS)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
    vendor_df.to_excel(writer, sheet_name="Vendor Master", index=False)
    po_df.to_excel(writer, sheet_name="PO Master", index=False)
    tariff_df.to_excel(writer, sheet_name="HS Code Tariff Rates", index=False)
    invoice_df.to_excel(writer, sheet_name="Spend Invoice Detail", index=False)

print(f"Wrote {OUT_PATH} with {len(vendor_df)} vendors, {len(po_df)} POs, {len(tariff_df)} tariff lanes, {len(invoice_df)} invoices.")

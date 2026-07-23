"""
Supply-Side Tariff Exposure Analyzer — synthetic data + analytical dataframe.

Sub-sector: Electronics manufacturing (procurement / inbound direct materials).
Everything below is synthetic. No real companies, people, or quotes.
Reproducible via a fixed seed.

Outputs (to ./out):
  suppliers.csv          supplier master
  bom_parts.csv          direct-material parts / BOM
  trade_alerts.csv       synthetic Global Trade Alert-style measures
  exposure.csv           computed part-level tariff exposure
  demo.html              self-contained interactive dashboard (data inlined)
"""

import json
import os
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

N_SUPPLIERS = 50
N_PARTS = 150

# ----------------------------------------------------------------------------
# Reference tables
# ----------------------------------------------------------------------------
CATEGORIES = {
    "Semiconductors/ICs":       ["8542.31", "8542.32", "8542.39"],
    "PCB & Laminates":          ["8534.00"],
    "Capacitors":               ["8532.24", "8532.21"],
    "Connectors":               ["8536.69", "8536.90"],
    "Resistors & Passives":     ["8533.21", "8533.40"],
    "Display Modules":          ["9013.80"],
    "Li-ion Cells & Batteries": ["8507.60"],
    "Inductors & Transformers": ["8504.31", "8504.50"],
    "Insulated Wire & Cable":   ["8544.42", "8544.49"],
    "Aluminium Enclosures":     ["7616.99", "7606.12"],
    "Steel Hardware":           ["7326.90"],
    "Polymer Housings":         ["3926.90"],
}
CAT_LIST = list(CATEGORIES.keys())

COUNTRY_W = {
    "China": 0.30, "Taiwan": 0.14, "South Korea": 0.10, "Japan": 0.08,
    "Vietnam": 0.08, "Malaysia": 0.06, "Thailand": 0.05, "Mexico": 0.05,
    "Germany": 0.04, "USA": 0.04, "India": 0.03, "Philippines": 0.03,
}
COUNTRIES = list(COUNTRY_W.keys())
CW = np.array(list(COUNTRY_W.values()))
CW = CW / CW.sum()

REGION = {
    "China": "East Asia", "Taiwan": "East Asia", "South Korea": "East Asia",
    "Japan": "East Asia", "Vietnam": "SE Asia", "Malaysia": "SE Asia",
    "Thailand": "SE Asia", "Philippines": "SE Asia", "India": "South Asia",
    "Mexico": "North America", "USA": "North America", "Germany": "Europe",
}

# name fragments for invented supplier names
PREFIX = ["Volt", "Sil", "Nexa", "Kori", "Meishan", "Anser", "Trigon", "Halcyon",
          "Orin", "Zhen", "Baltic", "Cobalt", "Ferro", "Lumen", "Axion", "Terna",
          "Onyx", "Kestrel", "Vireo", "Sable", "Doran", "Elbe", "Pramar", "Hanwa",
          "Toko", "Ceyl", "Verda", "Ostro", "Kanto", "Miran"]
SUFFIX = ["Components", "Microelectronics", "Semicon", "Circuit Works", "Electronics",
          "Assemblies", "Precision", "Materials", "Systems", "Devices", "Technologies",
          "Industries", "Fabrication", "Interconnect"]


def pick_country():
    return COUNTRIES[rng.choice(len(COUNTRIES), p=CW)]


# ----------------------------------------------------------------------------
# Suppliers
# ----------------------------------------------------------------------------
sup_rows = []
used_names = set()
for i in range(1, N_SUPPLIERS + 1):
    while True:
        nm = f"{rng.choice(PREFIX)} {rng.choice(SUFFIX)}"
        if nm not in used_names:
            used_names.add(nm)
            break
    country = pick_country()
    cat = rng.choice(CAT_LIST)
    # spend follows a pareto-ish shape so a few suppliers dominate
    spend = float(np.round(rng.pareto(1.6) * 900_000 + 120_000, -3))
    crit = rng.choice(["High", "Medium", "Low"], p=[0.28, 0.42, 0.30])
    single = bool(rng.random() < (0.42 if crit == "High" else 0.22))
    otd = float(np.round(rng.normal(93 if crit != "High" else 90, 5), 1))
    otd = float(np.clip(otd, 70, 99.5))
    lead = int(np.clip(rng.normal(46 if REGION[country] != "North America" else 24, 16), 7, 130))
    tier = int(rng.choice([1, 2, 3], p=[0.6, 0.28, 0.12]))
    sup_rows.append(dict(
        supplier_id=f"S{i:03d}", supplier_name=nm, country_of_origin=country,
        region=REGION[country], tier=tier, category=cat,
        annual_spend_usd=spend, criticality=crit, single_source_flag=single,
        avg_lead_time_days=lead, on_time_delivery_pct=otd))
suppliers = pd.DataFrame(sup_rows)

# ----------------------------------------------------------------------------
# BOM parts (inherit country from supplier so joins stay consistent)
# ----------------------------------------------------------------------------
DESCRIPTORS = {
    "Semiconductors/ICs": ["32-bit MCU", "Power management IC", "RF transceiver",
                            "Gate driver IC", "DC-DC converter IC", "FPGA module",
                            "Signal amplifier IC", "Motor controller IC"],
    "PCB & Laminates": ["6-layer FR4 PCB", "HDI rigid-flex PCB", "8-layer backplane",
                        "Ceramic substrate", "Metal-core PCB"],
    "Capacitors": ["MLCC array 0402", "Tantalum capacitor 47uF", "Film capacitor 1uF",
                   "Aluminium electrolytic 470uF", "MLCC 1206 X7R"],
    "Connectors": ["Board-to-board connector", "USB-C receptacle", "FFC/FPC connector",
                   "RF coax connector", "Power blade connector"],
    "Resistors & Passives": ["Thin-film resistor array", "Current-sense shunt",
                             "Ferrite bead", "Chip resistor 0603", "Varistor"],
    "Display Modules": ["5.5in TFT-LCD module", "OLED display 1.3in",
                        "Touch panel assembly", "e-Paper module", "LCD backlight unit"],
    "Li-ion Cells & Batteries": ["21700 Li-ion cell", "LiPo pouch cell 3000mAh",
                                 "Battery pack 4S", "Prismatic cell 50Ah", "Coin cell CR2032"],
    "Inductors & Transformers": ["Power inductor 10uH", "Common-mode choke",
                                 "Planar transformer", "Flyback transformer", "Toroidal inductor"],
    "Insulated Wire & Cable": ["Shielded ribbon cable", "Silicone hookup wire",
                               "Coax assembly RG-174", "Multi-core control cable", "Harness sub-assembly"],
    "Aluminium Enclosures": ["Die-cast Al housing", "Extruded heatsink",
                             "Machined Al chassis", "Al shield can", "Al front bezel"],
    "Steel Hardware": ["Stainless fastener kit", "Stamped steel bracket",
                       "Spring steel clip", "Steel standoff set", "EMI gasket frame"],
    "Polymer Housings": ["ABS enclosure top", "PC/ABS bezel", "Nylon cable gland",
                         "Silicone keypad", "PBT connector housing"],
}

# assign parts to suppliers with a MILD spend bias (sqrt) so a few Pareto-large
# suppliers don't hoover up the whole BOM; keeps the part-country mix close to
# the supplier-base mix (~30% China), which is the exposure story.
sup_weights = np.sqrt(suppliers["annual_spend_usd"].values)
sup_weights = sup_weights / sup_weights.sum()

part_rows = []
for i in range(1, N_PARTS + 1):
    s_idx = rng.choice(len(suppliers), p=sup_weights)
    s = suppliers.iloc[s_idx]
    cat = s["category"]
    hs = rng.choice(CATEGORIES[cat])
    desc = rng.choice(DESCRIPTORS[cat])
    # cost + volume vary widely by category
    base_cost = {
        "Semiconductors/ICs": 9.5, "Display Modules": 22.0, "Li-ion Cells & Batteries": 6.5,
        "PCB & Laminates": 4.2, "Inductors & Transformers": 1.8, "Connectors": 0.9,
        "Capacitors": 0.06, "Resistors & Passives": 0.03, "Insulated Wire & Cable": 1.1,
        "Aluminium Enclosures": 5.5, "Steel Hardware": 0.7, "Polymer Housings": 1.9,
    }[cat]
    unit_cost = float(np.round(base_cost * rng.lognormal(0, 0.5), 3))
    volume = int(rng.integers(20_000, 900_000))
    if cat in ("Capacitors", "Resistors & Passives"):
        volume *= 6  # passives ship in huge volumes
    material_share = float(np.round(rng.uniform(0.35, 0.85), 2))
    part_rows.append(dict(
        part_id=f"P{i:04d}", part_description=desc, category=cat, hs_code=hs,
        supplier_id=s["supplier_id"], supplier_name=s["supplier_name"],
        tier=int(s["tier"]),
        country_of_origin=s["country_of_origin"], region=s["region"],
        annual_volume_units=int(volume), unit_cost_usd=unit_cost,
        material_share_pct=material_share, criticality=s["criticality"],
        single_source_flag=bool(s["single_source_flag"]),
        on_time_delivery_pct=float(s["on_time_delivery_pct"])))
parts = pd.DataFrame(part_rows)
parts["annual_spend_usd"] = np.round(parts["unit_cost_usd"] * parts["annual_volume_units"], 2)

# ----------------------------------------------------------------------------
# Trade alerts (synthetic Global Trade Alert-style)
# ----------------------------------------------------------------------------
def hs(*keys):
    out = []
    for k in keys:
        out += CATEGORIES[k]
    return out

# hand-crafted core measures — these create the hot spots
CORE = [
    # jurisdiction, partner, measure, hs_keys, rate, status, headline, summary
    ("USA", "China", "Section 301 tariff", ["Semiconductors/ICs"], 25.0, "In force",
     "United States raises Section 301 duties on Chinese integrated circuits",
     "US Trade Representative confirms a 25% additional ad valorem duty on a range of Chinese-origin semiconductor devices, citing continued technology-transfer concerns."),
    ("USA", "China", "Section 301 tariff", ["PCB & Laminates"], 25.0, "In force",
     "Section 301 list expanded to printed circuit boards of Chinese origin",
     "A 25% additional duty now applies to bare and assembled printed circuit boards imported from China under the latest Section 301 action."),
    ("USA", "China", "Anti-dumping duty", ["Li-ion Cells & Batteries"], 18.4, "In force",
     "Anti-dumping order issued on lithium-ion cells from China",
     "Commerce imposes a weighted-average anti-dumping margin of 18.4% on lithium-ion cells and packs from named Chinese exporters following a final affirmative determination."),
    ("USA", "China", "Section 301 tariff", ["Capacitors"], 15.0, "In force",
     "Chinese multilayer ceramic capacitors added to Section 301 tariff list",
     "Passive components including MLCCs from China now carry a 15% additional duty, affecting high-volume board assemblies."),
    ("USA", "China", "Section 232 tariff", ["Aluminium Enclosures"], 10.0, "In force",
     "Section 232 aluminium duties extended to fabricated enclosures",
     "Fabricated aluminium enclosures and heatsinks of Chinese origin fall under the extended Section 232 aluminium measure at a 10% rate."),
    ("USA", "China", "Anti-dumping duty", ["Connectors"], 12.5, "Announced",
     "Preliminary anti-dumping margin announced on Chinese electrical connectors",
     "A preliminary 12.5% margin has been announced on board-to-board and power connectors from China; the order is not yet in force pending final determination."),
    ("China", "China", "Export control", ["Semiconductors/ICs"], 6.0, "In force",
     "China tightens export licensing on gallium and germanium inputs",
     "New export-licensing requirements on gallium- and germanium-based inputs raise effective landed costs and lead-time risk for downstream IC buyers."),
    ("USA", "Malaysia", "Anti-dumping duty", ["Capacitors"], 8.0, "In force",
     "Anti-dumping duty confirmed on tantalum capacitors from Malaysia",
     "Commerce finalises an 8% anti-dumping margin on tantalum capacitors of Malaysian origin."),
    ("USA", "Vietnam", "Section 301 tariff", ["Insulated Wire & Cable", "Connectors"], 7.0, "Under review",
     "USTR opens review of Vietnamese wire, cable and connector imports",
     "A proposed 7% duty on selected Vietnamese-origin interconnect products is under public-comment review; no duty is currently collected."),
    ("USA", "China", "Section 232 tariff", ["Steel Hardware"], 8.0, "Under review",
     "Proposed Section 232 expansion to steel fasteners and brackets",
     "A proposed 8% expansion of Section 232 steel measures to stamped hardware and fasteners is under review."),
    ("USA", "South Korea", "Tariff-rate quota", ["Inductors & Transformers"], 5.0, "In force",
     "Tariff-rate quota applied to Korean magnetics above threshold",
     "Imports of Korean-origin transformers and inductors above the annual quota threshold attract a 5% over-quota rate."),
    ("USA", "China", "Section 301 tariff", ["Display Modules"], 20.0, "In force",
     "Display modules of Chinese origin subject to Section 301 duty",
     "TFT-LCD and OLED display modules from China carry a 20% additional duty under Section 301."),
    ("USA", "Taiwan", "Anti-dumping duty", ["PCB & Laminates"], 4.5, "Announced",
     "Preliminary review of Taiwanese laminate imports announced",
     "A preliminary 4.5% margin has been floated on selected Taiwanese copper-clad laminates; not yet collected."),
    ("USA", "China", "Section 301 tariff", ["Resistors & Passives"], 15.0, "In force",
     "Chinese chip resistors and passives added to Section 301 list",
     "High-volume chip resistors and ferrite components from China now carry a 15% additional duty."),
    ("USA", "Mexico", "Tariff removal", ["Polymer Housings"], -6.0, "In force",
     "USMCA review removes duty on qualifying Mexican polymer housings",
     "Qualifying polymer housings of Mexican origin see a 6% duty removed following a rules-of-origin determination — a downside-risk relief."),
    ("USA", "Thailand", "Anti-dumping duty", ["Aluminium Enclosures"], 9.0, "In force",
     "Anti-dumping duty on Thai aluminium extrusions confirmed",
     "A 9% anti-dumping margin applies to aluminium extrusions and heatsinks of Thai origin."),
    ("USA", "China", "Section 301 tariff", ["Inductors & Transformers"], 10.0, "Expired",
     "Earlier Section 301 duty on Chinese magnetics allowed to lapse",
     "A prior 10% duty on Chinese-origin inductors expired at the end of the exclusion window and is no longer collected."),
    ("USA", "Japan", "Tariff-rate quota", ["Semiconductors/ICs"], 3.0, "Announced",
     "Proposed quota on advanced Japanese IC imports",
     "A proposed 3% over-quota rate on advanced Japanese ICs has been announced for consultation."),
]

alert_rows = []
aid = 1
dates = pd.date_range(end=pd.Timestamp("2026-07-15"), periods=300, freq="D")
for (juris, partner, measure, keys, rate, status, headline, summary) in CORE:
    pub = pd.Timestamp(rng.choice(dates.values))
    alert_rows.append(dict(
        alert_id=f"GTA{aid:04d}", published_date=pub.strftime("%Y-%m-%d"),
        implementing_jurisdiction=juris, affected_partner_country=partner,
        measure_type=measure, affected_hs_codes=";".join(hs(*keys)),
        tariff_rate_change_pct=rate, status=status, headline=headline,
        summary=summary,
        source_url=f"https://www.globaltradealert.org/intervention/{60000 + aid}"))
    aid += 1

# programmatic filler variants to reach ~30, on secondary partner/category combos
FILLER_COMBOS = [
    ("Vietnam", "Semiconductors/ICs", "Section 301 tariff"),
    ("India", "Connectors", "Anti-dumping duty"),
    ("Philippines", "Resistors & Passives", "Anti-dumping duty"),
    ("Germany", "Inductors & Transformers", "Tariff-rate quota"),
    ("South Korea", "Display Modules", "Anti-dumping duty"),
    ("Taiwan", "Semiconductors/ICs", "Section 301 tariff"),
    ("Thailand", "Insulated Wire & Cable", "Anti-dumping duty"),
    ("Mexico", "Steel Hardware", "Section 232 tariff"),
    ("China", "Polymer Housings", "Section 301 tariff"),
    ("Malaysia", "PCB & Laminates", "Anti-dumping duty"),
    ("Vietnam", "Aluminium Enclosures", "Section 232 tariff"),
    ("Japan", "Capacitors", "Tariff-rate quota"),
]
for partner, cat, measure in FILLER_COMBOS:
    rate = float(np.round(rng.uniform(3, 14), 1))
    status = str(rng.choice(["In force", "Announced", "Under review"], p=[0.5, 0.25, 0.25]))
    pub = pd.Timestamp(rng.choice(dates.values))
    alert_rows.append(dict(
        alert_id=f"GTA{aid:04d}", published_date=pub.strftime("%Y-%m-%d"),
        implementing_jurisdiction="USA", affected_partner_country=partner,
        measure_type=measure, affected_hs_codes=";".join(CATEGORIES[cat]),
        tariff_rate_change_pct=rate, status=status,
        headline=f"{measure} reported on {cat.lower()} from {partner}",
        summary=f"A {rate:.1f}% {measure.lower()} affecting {cat.lower()} of {partner} origin has been recorded ({status.lower()}).",
        source_url=f"https://www.globaltradealert.org/intervention/{60000 + aid}"))
    aid += 1

alerts = pd.DataFrame(alert_rows).sort_values("published_date", ascending=False).reset_index(drop=True)

# ----------------------------------------------------------------------------
# Exposure computation
# ----------------------------------------------------------------------------
inforce = alerts[alerts["status"] == "In force"].copy()
inforce["hs_set"] = inforce["affected_hs_codes"].str.split(";")

def match_alerts(row):
    hits = []
    delta = 0.0
    for _, a in inforce.iterrows():
        if row["country_of_origin"] == a["affected_partner_country"] and row["hs_code"] in a["hs_set"]:
            hits.append(a["alert_id"])
            delta += a["tariff_rate_change_pct"]
    return pd.Series({"matched_alert_ids": ";".join(hits), "applied_delta_pct": max(delta, -100.0)})

matched = parts.apply(match_alerts, axis=1)
exp = pd.concat([parts, matched], axis=1)

exp["landed_cost_before_usd"] = exp["unit_cost_usd"]
exp["landed_cost_after_usd"] = np.round(exp["unit_cost_usd"] * (1 + exp["applied_delta_pct"] / 100.0), 4)
exp["annual_cost_impact_usd"] = np.round(
    (exp["landed_cost_after_usd"] - exp["landed_cost_before_usd"]) * exp["annual_volume_units"], 2)

# Composite exposure score (0-100). Kept simple enough to replicate exactly in JS.
#   cost:   45 * min(impact / 150k, 1)   -> dollar severity
#   hit:    +12 if any live tariff applies -> exposure registers even when $ is small
#   crit:   High 20 / Medium 11 / Low 4
#   single: +14 if single-sourced
#   otd:    6 * (1 - otd/100)
# Bands: Red >= 50, Amber >= 25, else Green.
CRIT_W = {"High": 20, "Medium": 11, "Low": 4}
COST_CAP = 150_000

def score_row(r):
    cost_norm = min(max(r["annual_cost_impact_usd"], 0) / COST_CAP, 1.0)
    s = 45 * cost_norm
    s += 12 if r["applied_delta_pct"] > 0 else 0
    s += CRIT_W[r["criticality"]]
    s += 14 if r["single_source_flag"] else 0
    s += 6 * (1 - r["on_time_delivery_pct"] / 100.0)
    return round(min(s, 100), 1)

exp["exposure_score"] = exp.apply(score_row, axis=1)
exp["risk_band"] = np.where(exp["exposure_score"] >= 50, "Red",
                    np.where(exp["exposure_score"] >= 25, "Amber", "Green"))
# any part under a live tariff is at least on the watchlist (Amber)
exp.loc[(exp["applied_delta_pct"] > 0) & (exp["risk_band"] == "Green"), "risk_band"] = "Amber"

# ----------------------------------------------------------------------------
# Roll-ups
# ----------------------------------------------------------------------------
total_spend = float(exp["annual_spend_usd"].sum())
total_impact = float(exp["annual_cost_impact_usd"].sum())
at_risk_spend = float(exp.loc[exp["risk_band"] != "Green", "annual_spend_usd"].sum())
at_risk_pct = round(100 * at_risk_spend / total_spend, 1)
red_count = int((exp["risk_band"] == "Red").sum())
ss_exposed = int(((exp["single_source_flag"]) & (exp["annual_cost_impact_usd"] > 0)).sum())

by_country = (exp.groupby("country_of_origin")["annual_cost_impact_usd"].sum()
              .sort_values(ascending=False).round(0).astype(int))
by_category = (exp.groupby("category")["annual_cost_impact_usd"].sum()
               .sort_values(ascending=False).round(0).astype(int))

# ----------------------------------------------------------------------------
# Export CSVs
# ----------------------------------------------------------------------------
suppliers.to_csv(os.path.join(OUT, "suppliers.csv"), index=False)
parts.to_csv(os.path.join(OUT, "bom_parts.csv"), index=False)
alerts.drop(columns=[c for c in ["hs_set"] if c in alerts.columns]).to_csv(
    os.path.join(OUT, "trade_alerts.csv"), index=False)
exp.to_csv(os.path.join(OUT, "exposure.csv"), index=False)

# ----------------------------------------------------------------------------
# Build JSON payload for the dashboard
# ----------------------------------------------------------------------------
payload = {
    "company": "Voltaic Systems (synthetic)",
    "generated": "2026-07-22",
    "totals": {
        "total_spend": total_spend, "total_impact": total_impact,
        "at_risk_pct": at_risk_pct, "red_count": red_count,
        "ss_exposed": ss_exposed, "n_parts": int(len(exp)),
        "cost_cap": COST_CAP,
    },
    "crit_w": CRIT_W,
    "data_quality": {
        "raw": int(len(exp)) + 7, "clean": int(len(exp)),
        "issues": [
            {"issue": "Missing part description", "rows": 3, "action": "Imputed"},
            {"issue": "Missing unit cost", "rows": 5, "action": "Imputed"},
            {"issue": "Missing country of origin", "rows": 4, "action": "Enriched"},
            {"issue": "Unmapped HS code", "rows": 6, "action": "Matched"},
            {"issue": "Duplicate part rows", "rows": 7, "action": "Removed"},
        ],
    },
    "by_country": [{"country": k, "impact": int(v)} for k, v in by_country.items()],
    "by_category": [{"category": k, "impact": int(v)} for k, v in by_category.items()],
    "countries": COUNTRIES,
    "categories": CAT_LIST,
    "alerts": alerts.drop(columns=[c for c in ["hs_set"] if c in alerts.columns]).to_dict("records"),
    "parts": [
        {
            "id": r.part_id, "desc": r.part_description, "category": r.category,
            "hs": r.hs_code, "country": r.country_of_origin, "region": r.region,
            "supplier_id": r.supplier_id, "supplier": r.supplier_name, "tier": int(r.tier),
            "unit_cost": float(r.unit_cost_usd), "volume": int(r.annual_volume_units),
            "spend": float(r.annual_spend_usd), "crit": r.criticality,
            "single_source": bool(r.single_source_flag), "otd": float(r.on_time_delivery_pct),
            "base_delta": float(r.applied_delta_pct), "base_after": float(r.landed_cost_after_usd),
            "base_impact": float(r.annual_cost_impact_usd), "base_score": float(r.exposure_score),
            "base_band": r.risk_band, "matched": r.matched_alert_ids,
        }
        for r in exp.itertuples(index=False)
    ],
}

# ----------------------------------------------------------------------------
# Inject into the HTML template -> demo.html
# ----------------------------------------------------------------------------
tpl_path = os.path.join(os.path.dirname(__file__), "template.html")
with open(tpl_path, "r", encoding="utf-8") as f:
    tpl = f.read()
html = tpl.replace("/*__PAYLOAD__*/", json.dumps(payload))
with open(os.path.join(OUT, "demo.html"), "w", encoding="utf-8") as f:
    f.write(html)

# ----------------------------------------------------------------------------
# Validation summary + previews
# ----------------------------------------------------------------------------
print("=" * 66)
print("VALIDATION SUMMARY")
print("=" * 66)
print(f"Suppliers: {len(suppliers)} | Parts: {len(parts)} | Alerts: {len(alerts)} "
      f"({(alerts.status=='In force').sum()} in force)")
print(f"Total annual spend      : ${total_spend:,.0f}")
print(f"Total annual tariff cost : ${total_impact:,.0f}")
print(f"At-risk spend            : {at_risk_pct}%")
print(f"Red-band parts           : {red_count} / {len(exp)}")
print(f"Single-source exposures  : {ss_exposed}")
print("\nRisk band distribution:")
print(exp["risk_band"].value_counts().to_string())
print("\nTop 8 exposed parts:")
cols = ["part_id", "part_description", "country_of_origin", "hs_code",
        "applied_delta_pct", "annual_cost_impact_usd", "exposure_score", "risk_band"]
print(exp.sort_values("annual_cost_impact_usd", ascending=False)[cols].head(8).to_string(index=False))
print("\nImpact by country (top 6):")
print(by_country.head(6).to_string())
print("\n--- suppliers.csv (head) ---")
print(suppliers.head(4).to_string(index=False))
print("\n--- bom_parts.csv (head) ---")
print(parts[["part_id","part_description","category","hs_code","country_of_origin",
             "unit_cost_usd","annual_volume_units","annual_spend_usd"]].head(4).to_string(index=False))
print("\n--- trade_alerts.csv (head) ---")
print(alerts[["alert_id","published_date","affected_partner_country","measure_type",
              "tariff_rate_change_pct","status"]].head(5).to_string(index=False))
print("\nWrote: suppliers.csv, bom_parts.csv, trade_alerts.csv, exposure.csv, demo.html")

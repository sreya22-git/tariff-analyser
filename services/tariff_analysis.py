from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import calendar
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

CHECKS_PER_BUCKET = 4
BUCKET_NAMES = ["Cost Impact Analysis", "Supplier & Country Risk", "Duty Optimization & Compliance"]



def _load_sheets(file_path: str | Path) -> Dict[str, pd.DataFrame]:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    xls = pd.ExcelFile(file_path)
    out: Dict[str, pd.DataFrame] = {}
    for name in xls.sheet_names:
        try:
            out[name] = xls.parse(name)
        except Exception:
            continue
    return out


def _get(sheets: Dict[str, pd.DataFrame], *names: str) -> Optional[pd.DataFrame]:
    for n in names:
        if n in sheets:
            return sheets[n]
    return None


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _money(v: float) -> str:
    try:
        return f"${v:,.2f}"
    except Exception:
        return str(v)


def _row(table: str, record_id: str, field: str, description: str, value_found: str, proposed_action: str, check: str) -> Dict[str, str]:
    return {
        "table": table,
        "record_id": str(record_id),
        "field": field,
        "description": description,
        "value_found": value_found,
        "proposed_action": proposed_action,
        "check": check,
    }


def numeric_outliers(series: pd.Series) -> pd.Series:
    """Boolean mask of IQR-based outliers."""
    x = _num(series)
    q1, q3 = x.quantile(0.25), x.quantile(0.75)
    iqr = q3 - q1
    if pd.isna(iqr) or iqr == 0:
        return pd.Series([False] * len(series), index=series.index)
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return (x < lower) | (x > upper)


def _summary(sheets: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    total_rows = sum(len(df) for df in sheets.values())
    return {"total_rows": int(total_rows), "total_tables": len(sheets)}


# ---------------------------------------------------------------------------
# Cost Impact Analysis
# ---------------------------------------------------------------------------

def analyze_cost_impact(file_path: str | Path) -> Dict[str, Any]:
    sheets = _load_sheets(file_path)
    po = _get(sheets, "PO Master")
    tariff = _get(sheets, "HS Code Tariff Rates")
    inv = _get(sheets, "Spend Invoice Detail")

    buckets: Dict[str, List[Dict[str, str]]] = {
        "Tariff Rate Increase Exposure": [],
        "High-Duty Category Concentration": [],
        "Landed Cost Calculation Mismatch": [],
        "PO Value Outliers": [],
    }

    merged = None
    if inv is not None and po is not None and tariff is not None:
        m = inv.merge(po[["PONumber", "ItemCategory", "CountryOfOrigin"]], on="PONumber", how="left")
        m = m.merge(
            tariff[["HSCode", "CountryOfOrigin", "DutyRatePct", "PriorDutyRatePct", "FTAEligible"]],
            on=["HSCode", "CountryOfOrigin"], how="left",
        )
        merged = m

    if merged is not None:
        merged["_base_value"] = _num(merged["Qty"]) * _num(merged["UnitCost"])
        merged["_rate_increase"] = _num(merged["DutyRatePct"]) - _num(merged["PriorDutyRatePct"])
        merged["_cost_impact"] = merged["_base_value"] * merged["_rate_increase"].clip(lower=0) / 100.0
        merged["_expected_duty"] = merged["_base_value"] * _num(merged["DutyRatePct"]) / 100.0

        # 1) Tariff Rate Increase Exposure
        flagged = merged[merged["_cost_impact"] > 500]
        for _, r in flagged.iterrows():
            buckets["Tariff Rate Increase Exposure"].append(_row(
                table="Spend Invoice Detail", record_id=r["InvoiceID"], field="DutyRatePct",
                description=f"Duty rate on HS {r['HSCode']} from {r['CountryOfOrigin']} rose {r['_rate_increase']:.1f}pp ({r['PriorDutyRatePct']}% -> {r['DutyRatePct']}%).",
                value_found=_money(r["_cost_impact"]) + " added cost exposure",
                proposed_action="Renegotiate vendor pricing, pass through cost, or qualify an alternate sourcing lane to offset the increase.",
                check="Flag invoices where the applicable duty rate increased vs. the prior rate.",
            ))

        # 3) Landed Cost Calculation Mismatch (exclude correctly-claimed FTA lines)
        correctly_claimed = merged["FTAEligible"].fillna(False).astype(bool) & (merged["DutyPaid"] <= 0.05 * merged["_expected_duty"].clip(lower=0.01))
        tol = merged["_expected_duty"].abs() * 0.15
        tol = tol.clip(lower=50)
        mismatch = (~correctly_claimed) & ((merged["DutyPaid"] - merged["_expected_duty"]).abs() > tol) & merged["_expected_duty"].notna()
        for _, r in merged[mismatch].iterrows():
            buckets["Landed Cost Calculation Mismatch"].append(_row(
                table="Spend Invoice Detail", record_id=r["InvoiceID"], field="DutyPaid",
                description=f"Duty paid does not reconcile with Qty x UnitCost x DutyRatePct for HS {r['HSCode']}.",
                value_found=f"Paid {_money(r['DutyPaid'])} vs expected {_money(r['_expected_duty'])}",
                proposed_action="Reconcile invoice duty calculation with broker/customs entry; correct or recover the variance.",
                check="Compare DutyPaid to Qty x UnitCost x DutyRatePct within a 15% tolerance.",
            ))

    # 2) High-Duty Category Concentration
    if inv is not None and po is not None:
        cat_map = po.set_index("PONumber")["ItemCategory"] if "PONumber" in po.columns else None
        if cat_map is not None:
            tmp = inv.copy()
            tmp["ItemCategory"] = tmp["PONumber"].map(cat_map)
            grp = tmp.groupby("ItemCategory")["DutyPaid"].sum(numeric_only=True)
            total = grp.sum()
            if total and total > 0:
                for cat, val in grp.items():
                    pct = val / total * 100
                    if pct >= 25:
                        buckets["High-Duty Category Concentration"].append(_row(
                            table="Spend Invoice Detail", record_id=str(cat), field="ItemCategory",
                            description=f"'{cat}' accounts for {pct:.1f}% of total duty paid across all categories.",
                            value_found=_money(val) + f" ({pct:.1f}% of total)",
                            proposed_action="Prioritize this category for tariff-mitigation review (reclassification, FTA, alternate sourcing).",
                            check="Flag item categories responsible for >=25% of total duty paid.",
                        ))

    # 4) PO Value Outliers
    if po is not None and "POValue" in po.columns:
        mask = numeric_outliers(po["POValue"])
        for _, r in po[mask].iterrows():
            buckets["PO Value Outliers"].append(_row(
                table="PO Master", record_id=r["PONumber"], field="POValue",
                description="Purchase order value is a statistical outlier (IQR method) relative to other POs.",
                value_found=_money(_num(pd.Series([r["POValue"]])).iloc[0]),
                proposed_action="Verify PO value against contract/quote; check for data entry error or unapproved spend.",
                check="Flag PO values outside 1.5x IQR of the PO value distribution.",
            ))

    report: Dict[str, Any] = {
        "summary": _summary(sheets),
        "issues_by_bucket": buckets,
        "buckets_order": list(buckets.keys()),
    }
    return report


# ---------------------------------------------------------------------------
# Supplier & Country Risk
# ---------------------------------------------------------------------------

def analyze_supplier_risk(file_path: str | Path) -> Dict[str, Any]:
    sheets = _load_sheets(file_path)
    po = _get(sheets, "PO Master")
    vendor = _get(sheets, "Vendor Master")
    tariff = _get(sheets, "HS Code Tariff Rates")

    buckets: Dict[str, List[Dict[str, str]]] = {
        "Single-Source Category Risk": [],
        "Country Concentration Risk": [],
        "Vendor / Country-of-Origin Mismatch": [],
        "Continued Sourcing Despite Tariff Increase": [],
    }

    if po is not None:
        # 1) Single-Source Category Risk
        grp = po.groupby("ItemCategory").agg(vendors=("VendorID", "nunique"), spend=("POValue", "sum"))
        for cat, r in grp.iterrows():
            if r["vendors"] == 1 and r["spend"] > 20000:
                vname = po[po["ItemCategory"] == cat]["VendorID"].iloc[0]
                buckets["Single-Source Category Risk"].append(_row(
                    table="PO Master", record_id=str(cat), field="VendorID",
                    description=f"'{cat}' is sourced from a single vendor ({vname}) with {_money(r['spend'])} in total PO value.",
                    value_found=f"1 vendor, {_money(r['spend'])} spend",
                    proposed_action="Qualify a second supplier for this category to reduce single-source dependency risk.",
                    check="Flag item categories sourced from only one vendor above a spend threshold.",
                ))

        # 2) Country Concentration Risk
        grp2 = po.groupby("CountryOfOrigin")["POValue"].sum(numeric_only=True)
        total = grp2.sum()
        if total and total > 0:
            for country, val in grp2.items():
                if not country:
                    continue
                pct = val / total * 100
                if pct >= 35:
                    buckets["Country Concentration Risk"].append(_row(
                        table="PO Master", record_id=str(country), field="CountryOfOrigin",
                        description=f"{pct:.1f}% of total procurement spend originates from {country}.",
                        value_found=_money(val) + f" ({pct:.1f}% of total)",
                        proposed_action="Diversify country-of-origin mix to reduce exposure to a single trade lane's tariff/geopolitical risk.",
                        check="Flag countries of origin representing >=35% of total PO spend.",
                    ))

        # 3) Vendor / Country-of-Origin Mismatch
        if vendor is not None:
            merged = po.merge(vendor[["VendorID", "Country"]], on="VendorID", how="left")
            mismatch = merged["CountryOfOrigin"].astype(str).str.strip().ne("") & (merged["CountryOfOrigin"] != merged["Country"])
            for _, r in merged[mismatch].iterrows():
                buckets["Vendor / Country-of-Origin Mismatch"].append(_row(
                    table="PO Master", record_id=r["PONumber"], field="CountryOfOrigin",
                    description=f"PO country of origin ({r['CountryOfOrigin']}) differs from the vendor's registered country ({r['Country']}).",
                    value_found=f"PO={r['CountryOfOrigin']} vs Vendor={r['Country']}",
                    proposed_action="Confirm goods were not transshipped to obscure true origin; verify certificate of origin.",
                    check="Compare PO CountryOfOrigin against the vendor's registered Country.",
                ))

        # 4) Continued Sourcing Despite Tariff Increase
        if tariff is not None:
            increased = tariff[(_num(tariff["DutyRatePct"]) - _num(tariff["PriorDutyRatePct"])) > 5]
            if not increased.empty and "EffectiveDate" in tariff.columns:
                po_dates = pd.to_datetime(po["PODate"], errors="coerce")
                for _, lane in increased.iterrows():
                    eff = pd.to_datetime(lane["EffectiveDate"], errors="coerce")
                    if pd.isna(eff):
                        continue
                    lane_pos = po[(po["HSCode"] == lane["HSCode"]) & (po["CountryOfOrigin"] == lane["CountryOfOrigin"])]
                    if lane_pos.empty:
                        continue
                    lane_dates = po_dates.loc[lane_pos.index]
                    after = lane_pos.loc[lane_dates >= eff, "POValue"].sum()
                    before = lane_pos.loc[lane_dates < eff, "POValue"].sum()
                    if after > 0 and after >= before * 0.5:
                        buckets["Continued Sourcing Despite Tariff Increase"].append(_row(
                            table="HS Code Tariff Rates", record_id=f"{lane['HSCode']}/{lane['CountryOfOrigin']}", field="EffectiveDate",
                            description=f"Sourcing from {lane['CountryOfOrigin']} for HS {lane['HSCode']} continued after a "
                                        f"{(lane['DutyRatePct'] - lane['PriorDutyRatePct']):.1f}pp duty increase effective {lane['EffectiveDate']}.",
                            value_found=f"Pre: {_money(before)}, Post: {_money(after)}",
                            proposed_action="Re-evaluate this lane's total landed cost against alternate-country suppliers.",
                            check="Flag lanes with a >5pp duty increase where post-increase spend remains material.",
                        ))

    report: Dict[str, Any] = {
        "summary": _summary(sheets),
        "issues_by_bucket": buckets,
        "buckets_order": list(buckets.keys()),
    }
    return report


# ---------------------------------------------------------------------------
# Duty Optimization & Compliance
# ---------------------------------------------------------------------------

def analyze_duty_optimization(file_path: str | Path) -> Dict[str, Any]:
    sheets = _load_sheets(file_path)
    po = _get(sheets, "PO Master")
    tariff = _get(sheets, "HS Code Tariff Rates")
    inv = _get(sheets, "Spend Invoice Detail")

    buckets: Dict[str, List[Dict[str, str]]] = {
        "FTA Underutilization": [],
        "HS Code Classification Inconsistency": [],
        "Duty Drawback Opportunity": [],
        "Missing Compliance Documentation": [],
    }

    if inv is not None and po is not None and tariff is not None:
        m = inv.merge(po[["PONumber", "ItemCategory", "CountryOfOrigin"]], on="PONumber", how="left")
        m = m.merge(
            tariff[["HSCode", "CountryOfOrigin", "DutyRatePct", "FTAEligible", "FTAProgram"]],
            on=["HSCode", "CountryOfOrigin"], how="left",
        )
        m["_base_value"] = _num(m["Qty"]) * _num(m["UnitCost"])
        m["_expected_duty"] = m["_base_value"] * _num(m["DutyRatePct"]) / 100.0
        eligible = m["FTAEligible"].fillna(False).astype(bool)
        not_claimed = eligible & (m["DutyPaid"] > 0.5 * m["_expected_duty"].clip(lower=0.01))
        for _, r in m[not_claimed].iterrows():
            buckets["FTA Underutilization"].append(_row(
                table="Spend Invoice Detail", record_id=r["InvoiceID"], field="DutyPaid",
                description=f"Shipment is eligible for {r['FTAProgram'] or 'an FTA'} but full duty ({_money(r['DutyPaid'])}) was paid.",
                value_found=_money(r["DutyPaid"]) + " recoverable",
                proposed_action=f"File a certificate of origin under {r['FTAProgram'] or 'the applicable FTA'} to claim duty-free treatment.",
                check="Flag FTA-eligible lanes where duty paid is not materially reduced from the standard rate.",
            ))

    if po is not None:
        # 2) HS Code Classification Inconsistency
        grp = po.groupby("ItemCategory")["HSCode"].nunique()
        for cat, n in grp.items():
            if n > 1:
                codes = sorted(po[po["ItemCategory"] == cat]["HSCode"].dropna().unique().tolist())
                buckets["HS Code Classification Inconsistency"].append(_row(
                    table="PO Master", record_id=str(cat), field="HSCode",
                    description=f"'{cat}' is classified under {n} different HS codes: {', '.join(str(c) for c in codes)}.",
                    value_found=", ".join(str(c) for c in codes),
                    proposed_action="Review classification rulings; consolidate to the correct HS code to avoid misclassification penalties.",
                    check="Flag item categories mapped to more than one HS code.",
                ))

        # 3) Duty Drawback Opportunity
        if inv is not None:
            returned = po[po["Status"].isin(["Returned", "Cancelled"])]
            if not returned.empty:
                duty_by_po = inv.groupby("PONumber")["DutyPaid"].sum(numeric_only=True)
                for _, r in returned.iterrows():
                    duty = duty_by_po.get(r["PONumber"], 0)
                    if duty and duty > 0:
                        buckets["Duty Drawback Opportunity"].append(_row(
                            table="PO Master", record_id=r["PONumber"], field="Status",
                            description=f"PO status is '{r['Status']}' but {_money(duty)} in duty was already paid on related invoices.",
                            value_found=_money(duty) + " duty paid",
                            proposed_action="File a duty drawback claim to recover duty paid on returned/cancelled goods.",
                            check="Flag returned/cancelled POs with associated duty payments.",
                        ))

        # 4) Missing Compliance Documentation
        missing_mask = po["CountryOfOrigin"].astype(str).str.strip().eq("") | po["HSCode"].isna() | po["HSCode"].astype(str).str.strip().eq("")
        for _, r in po[missing_mask].iterrows():
            buckets["Missing Compliance Documentation"].append(_row(
                table="PO Master", record_id=r["PONumber"], field="CountryOfOrigin / HSCode",
                description="Country of origin or HS code is missing, which is required for customs entry documentation.",
                value_found=f"CountryOfOrigin='{r.get('CountryOfOrigin', '')}', HSCode='{r.get('HSCode', '')}'",
                proposed_action="Obtain and record the certificate of origin and correct HS classification before the next filing.",
                check="Flag POs missing CountryOfOrigin or HSCode.",
            ))

    report: Dict[str, Any] = {
        "summary": _summary(sheets),
        "issues_by_bucket": buckets,
        "buckets_order": list(buckets.keys()),
    }
    return report


# ---------------------------------------------------------------------------
# Deterministic dashboard payload (non-LLM fallback; also usable to sanity
# check the agentic/LLM output since it shares the same JSON contract)
# ---------------------------------------------------------------------------

def build_dashboard_payload(file_path: str | Path) -> Dict[str, Any]:
    sheets = _load_sheets(file_path)
    po = _get(sheets, "PO Master")
    vendor = _get(sheets, "Vendor Master")
    inv = _get(sheets, "Spend Invoice Detail")

    cost = analyze_cost_impact(file_path)
    supplier = analyze_supplier_risk(file_path)
    duty = analyze_duty_optimization(file_path)
    reports = {"Cost Impact Analysis": cost, "Supplier & Country Risk": supplier, "Duty Optimization & Compliance": duty}

    counts = {name: sum(len(v) for v in r["issues_by_bucket"].values()) for name, r in reports.items()}
    total_findings = sum(counts.values())

    total_spend = float(_num(po["POValue"]).sum()) if po is not None else 0.0
    total_duty = float(_num(inv["DutyPaid"]).sum()) if inv is not None else 0.0
    vendors_analyzed = int(vendor["VendorID"].nunique()) if vendor is not None else 0
    pos_analyzed = int(len(po)) if po is not None else 0

    cost_exposure_ratio = min(1.0, total_duty / total_spend) if total_spend else 0.0
    cost_impact_score = round(100 * (1 - min(1.0, counts["Cost Impact Analysis"] / max(pos_analyzed, 1) * 4)))

    max_country_pct = 0.0
    if po is not None and "CountryOfOrigin" in po.columns:
        grp = po.groupby("CountryOfOrigin")["POValue"].sum(numeric_only=True)
        if grp.sum():
            max_country_pct = float((grp / grp.sum()).max())
    supplier_risk_score = round(100 * (1 - max_country_pct)) if max_country_pct else 78

    fta_findings = len(duty["issues_by_bucket"].get("FTA Underutilization", []))
    total_invoices = int(len(inv)) if inv is not None else 1
    duty_optimization_score = round(100 * (1 - min(1.0, fta_findings / max(total_invoices, 1) * 3)))

    summary_cards = {
        "total_tariff_exposure": round(total_duty, 2),
        "total_spend_analyzed": round(total_spend, 2),
        "vendors_analyzed": vendors_analyzed,
        "pos_analyzed": pos_analyzed,
        "high_risk_findings": total_findings,
    }

    impact_metrics = {
        "Cost Impact Analysis": {"score": cost_impact_score, "checks_failing": len(cost["issues_by_bucket"]), "rows_audited": pos_analyzed},
        "Supplier & Country Risk": {"score": supplier_risk_score, "checks_failing": len(supplier["issues_by_bucket"]), "rows_audited": pos_analyzed},
        "Duty Optimization & Compliance": {"score": duty_optimization_score, "checks_failing": len(duty["issues_by_bucket"]), "rows_audited": total_invoices},
    }

    pie = {"labels": BUCKET_NAMES, "series": [counts[n] for n in BUCKET_NAMES]}
    treemap = [
        {"name": name, "data": [{"x": k, "y": len(v)} for k, v in r["issues_by_bucket"].items()]}
        for name, r in reports.items()
    ]

    months: List[str] = []
    monthly_duty: List[float] = []
    if inv is not None and "InvoiceDate" in inv.columns:
        dates = pd.to_datetime(inv["InvoiceDate"], errors="coerce")
        now = dates.max() if dates.notna().any() else datetime.now()
        for i in range(5, -1, -1):
            m_end = (now.replace(day=1) - pd.DateOffset(months=i))
            months.append(f"{calendar.month_abbr[m_end.month]} {m_end.year}")
        for i in range(5, -1, -1):
            m_start = (now.replace(day=1) - pd.DateOffset(months=i))
            m_stop = m_start + pd.DateOffset(months=1)
            mask = (dates >= m_start) & (dates < m_stop)
            monthly_duty.append(float(_num(inv.loc[mask, "DutyPaid"]).sum()))
    if not months:
        months = ["--"] * 6
        monthly_duty = [0.0] * 6

    total_c, total_s, total_d = counts["Cost Impact Analysis"], counts["Supplier & Country Risk"], counts["Duty Optimization & Compliance"]
    total_all = max(total_c + total_s + total_d, 1)
    trend = {
        "months": months,
        "cost_impact": [round(v * (total_c / total_all) / 1000, 1) for v in monthly_duty],
        "supplier_risk": [round(v * (total_s / total_all) / 1000, 1) for v in monthly_duty],
        "duty_optimization": [round(v * (total_d / total_all) / 1000, 1) for v in monthly_duty],
    }
    total_last_6 = sum(monthly_duty)
    peak_idx = int(np.argmax(monthly_duty)) if monthly_duty else 0

    category_summary_list: List[Dict[str, Any]] = []
    if po is not None:
        cats = po["ItemCategory"].dropna().unique().tolist()
        for cat in cats[:8]:
            cat_pos = po[po["ItemCategory"] == cat]
            n_pos = len(cat_pos)
            po_numbers = set(cat_pos["PONumber"].astype(str).tolist())

            def _matches(it: Dict[str, str]) -> bool:
                rid = str(it.get("record_id"))
                return rid == str(cat) or rid in po_numbers

            hits = sum(1 for r in reports.values() for items in r["issues_by_bucket"].values() for it in items if _matches(it))
            score = round(100 * (1 - min(1.0, hits / max(n_pos, 1))))
            issues = [k for r in reports.values() for k, items in r["issues_by_bucket"].items() if any(_matches(it) for it in items)]
            category_summary_list.append({
                "title": cat,
                "score_pct": score,
                "issue_count": hits,
                "issues": issues[:3] if issues else ["No findings"],
                "threshold": "good" if score >= 90 else "warn",
            })

    return {
        "summary_cards": summary_cards,
        "impact_metrics": impact_metrics,
        "issue_overview": {
            "pie": pie,
            "treemap": treemap,
            "trend": trend,
            "six_month_summary": {
                "total_duty_last_6": round(total_last_6, 2),
                "avg_per_month": round(total_last_6 / 6, 1),
                "peak_month_index": peak_idx,
            },
        },
        "category_summary_list": category_summary_list,
    }

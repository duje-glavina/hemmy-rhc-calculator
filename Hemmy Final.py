# Hemy – Hemodynamic RHC Calculator (Console)
# Author: Josip A. Borovac, MD, PhD
# Version: 1.3.4
#
# Baseline: v1.3.3 (optional N/A fields allowed, auto mPAP, Hb in g/L, Qp/Qs Hb-based, TXT/NONE export)
# Update in v1.3.4:
#  - Append guideline-aligned PH treatment options section at end of report (ESC/ERS 2022-era/2023 practice)
#  - Restore "example values in parentheses" in prompts
#
# Python 3.14.x / IDLE-safe (no leading-zero integer literals)

import math
from datetime import datetime
import os
import platform
import subprocess

APP_NAME = "HEMMY"
APP_AUTHOR = "Josip A. Borovac, MD, PhD"
APP_VERSION = "1.3.4"
DEFAULT_INSTITUTION = "Department of Cardiovascular Diseases, University Hospital of Split"

HUFNER = 1.34
DYNE_PER_WU = 80.0
RVSWI_FACTOR = 0.0136  # RVSWI = SVI*(mPAP-RAP)*0.0136 (g·m/m²/beat)


def banner(run_ts_str):
    print(f"\n{APP_NAME} – Right Heart Catheterization Hemodynamics (Console)")
    print(f"Author: {APP_AUTHOR} | Version: {APP_VERSION}")
    print(f"Run timestamp: {run_ts_str}\n")


def s_input(prompt, default="", example=None):
    ex = f" (e.g., {example})" if example is not None and str(example) != "" else ""
    suffix = f" [{default}]" if default else ""
    s = input(f"{prompt}{ex}{suffix}: ").strip()
    return s if s else default


def f_input(prompt, default=None, example=None, allow_blank=False):
    ex = f" (e.g., {example})" if example is not None and str(example) != "" else ""
    while True:
        suffix = f" [{default}]" if default is not None else ""
        s = input(f"{prompt}{ex}{suffix}: ").strip()
        if s == "":
            if allow_blank:
                return None
            if default is not None:
                return float(default)
            print("  -> Required.")
            continue
        try:
            return float(s)
        except ValueError:
            print("  -> Please enter a number.")


def bsa_mosteller(height_cm, weight_kg):
    if height_cm <= 0 or weight_kg <= 0:
        return float("nan")
    return math.sqrt((height_cm * weight_kg) / 3600.0)


def safe_div(n, d):
    return n / d if abs(d) > 1e-12 else float("nan")


def is_nan(x):
    return isinstance(x, float) and math.isnan(x)


def mean_from_sys_dia(sys_p, dia_p):
    return dia_p + (sys_p - dia_p) / 3.0


def map_from_sbp_dbp(sbp, dbp):
    return dbp + (sbp - dbp) / 3.0


def o2_content_ml_per_dl(hb_g_dl, sat_frac):
    return HUFNER * hb_g_dl * sat_frac


def pick_mixed_venous_sat(pa, ra, rv, svc, ivc):
    if pa is not None:
        return pa, "PA"
    if ra is not None:
        return ra, "RA"
    if svc is not None and ivc is not None:
        return (2.0 * ivc + 1.0 * svc) / 3.0, "weighted(2/3 IVC + 1/3 SVC)"
    if rv is not None:
        return rv, "RV"
    return 75.0, "default(75%)"


def classify_range(value, low=None, high=None, normal_label="NORMAL", low_label="LOW", high_label="HIGH"):
    if value is None or is_nan(value):
        return "N/A"
    if low is not None and value < low:
        return low_label
    if high is not None and value > high:
        return high_label
    return normal_label


def classify_threshold(value, threshold, normal_label="NORMAL", abnormal_label="ELEVATED", direction="gt"):
    if value is None or is_nan(value):
        return "N/A"
    if direction == "gt":
        return abnormal_label if value > threshold else normal_label
    return abnormal_label if value < threshold else normal_label


def pvr_severity(pvr_wu):
    if pvr_wu is None or is_nan(pvr_wu):
        return "N/A"
    if pvr_wu >= 5.0:
        return "SEVERE (≥5 WU)"
    if pvr_wu > 2.0:
        return "ELEVATED (>2 WU)"
    return "NORMAL (≤2 WU)"


def ph_phenotype_key(mpap, pcwp, pvr_wu):
    # ESC/ERS haemodynamics:
    # PH: mPAP > 20
    # Pre-capillary: mPAP>20, PCWP<=15, PVR>2
    # Post-capillary: mPAP>20, PCWP>15; IpcPH if PVR<=2, CpcPH if PVR>2
    if is_nan(mpap) or is_nan(pcwp) or is_nan(pvr_wu):
        return "unknown"
    if mpap <= 20:
        return "no_ph"
    if pcwp <= 15:
        return "precap" if pvr_wu > 2 else "ph_pvr_le2"
    # pcwp > 15
    return "cpcph" if pvr_wu > 2 else "ipcph"


def interpret_ph_esc_ers(mpap, pcwp, pvr_wu):
    if is_nan(mpap) or is_nan(pcwp) or is_nan(pvr_wu):
        return "Unable to classify PH (missing/invalid inputs)."
    if mpap <= 20:
        return f"No PH by ESC/ERS hemodynamics: mPAP {mpap:.1f} mmHg (≤ 20)."
    if pcwp <= 15:
        if pvr_wu > 2:
            return (f"PH present (mPAP > 20). Pre-capillary PH: "
                    f"PCWP {pcwp:.1f} (≤15), PVR {pvr_wu:.2f} (>2).")
        return (f"PH present (mPAP > 20) with PCWP ≤ 15 but PVR ≤ 2 "
                f"(borderline/flow-related; interpret clinically).")
    if pvr_wu > 2:
        return (f"PH present (mPAP > 20). Combined post- and pre-capillary PH (CpcPH): "
                f"PCWP {pcwp:.1f} (>15), PVR {pvr_wu:.2f} (>2).")
    return (f"PH present (mPAP > 20). Isolated post-capillary PH (IpcPH): "
            f"PCWP {pcwp:.1f} (>15), PVR {pvr_wu:.2f} (≤2).")


def hb_gL_to_gdL(hb_g_L):
    corrected = False
    hb = hb_g_L
    if hb_g_L is not None and hb_g_L > 0 and hb_g_L < 40:
        hb = hb_g_L * 10.0
        corrected = True
    return hb, (hb / 10.0), corrected


def compute_qpqs_o2content(hb_g_dl, sao2, svo2, pa_sat):
    """
    Qp/Qs = (Ca - Cv) / (Cpv - Cpa)
    Assumption: SpvO2 ≈ max(98%, SaO2), capped at 100%
    """
    if pa_sat is None:
        return float("nan"), "N/A (PA sat missing)"

    spv = max(98.0, sao2)
    if spv > 100.0:
        spv = 100.0

    ca = o2_content_ml_per_dl(hb_g_dl, sao2 / 100.0)
    cv = o2_content_ml_per_dl(hb_g_dl, svo2 / 100.0)
    cpa = o2_content_ml_per_dl(hb_g_dl, pa_sat / 100.0)
    cpv = o2_content_ml_per_dl(hb_g_dl, spv / 100.0)

    denom = cpv - cpa
    if abs(denom) < 1e-9:
        return float("nan"), f"N/A (Cpv≈Cpa; SpvO2 assumed {spv:.1f}%)"

    qpqs = (ca - cv) / denom
    return qpqs, f"SpvO2 assumed {spv:.1f}% (Hb-based O2 content method)"


def interpret_shunt(qpqs):
    if qpqs is None or is_nan(qpqs):
        return "Shunt: unable to determine (Qp/Qs not available)."

    if qpqs > 1.05:
        direction = "Left-to-right shunt suggested (Qp/Qs > 1)."
        if qpqs < 1.5:
            sev = "Non-significant/small (Qp/Qs < 1.5)."
        elif qpqs <= 2.0:
            sev = "Moderate (Qp/Qs 1.5–2.0)."
        else:
            sev = "Significant/large (Qp/Qs > 2.0)."
        return f"Shunt: {direction} Severity: {sev}"

    if qpqs < 0.95:
        direction = "Right-to-left shunt suggested (Qp/Qs < 1)."
        if qpqs >= 0.80:
            sev = "Moderate (Qp/Qs 0.80–0.95)."
        else:
            sev = "Significant (Qp/Qs < 0.80)."
        return f"Shunt: {direction} Severity: {sev}"

    return "Shunt: no significant shunt suggested (Qp/Qs ~ 1)."


def treatment_recommendations_block(mpap, pcwp, pvr_wu):
    """
    High-level, ESC/ERS-aligned options based on haemodynamic phenotype.
    NOTE: Definitive therapy depends on PH group (1–5) + full diagnostic work-up.
    """
    key = ph_phenotype_key(mpap, pcwp, pvr_wu)
    lines = []
    lines.append("Treatment options (ESC/ERS-aligned, haemodynamic phenotype-based; high-level):")

    if key == "no_ph":
        lines.append("- No haemodynamic PH (mPAP ≤ 20): treat underlying condition; follow clinically.")
        return "\n".join(lines)

    # General supportive options
    lines.append("- General/supportive (as appropriate): diuretics for congestion/right HF; oxygen if hypoxaemic; supervised rehab/exercise when stable; vaccinations; manage comorbidities; consider PH expert-centre referral.")

    if key == "precap":
        lines.append("- Pre-capillary PH: complete diagnostic work-up to define PH group (PAH vs lung/hypoxia vs CTEPH vs others) before targeted therapy.")
        lines.append("- If PAH (Group 1) confirmed: risk-based therapy—often initial dual oral combination (ERA + PDE5 inhibitor) for low/intermediate risk; escalate by follow-up risk assessment.")
        lines.append("- If high-risk PAH or severe haemodynamics: consider initial triple therapy including parenteral prostacyclin (i.v./s.c.) in expert centre; consider transplant evaluation if inadequate response.")
        lines.append("- If CTEPH suspected/confirmed: lifelong anticoagulation; refer to CTEPH team for operability—pulmonary endarterectomy (PEA) if operable; balloon pulmonary angioplasty (BPA) if inoperable/residual; riociguat for symptomatic inoperable or persistent/recurrent PH after PEA.")
        lines.append("- If PH due to lung disease/hypoxia: optimize lung disease and hypoxaemia; PAH drugs generally not recommended in non-severe cases; individualized decisions in severe cases at expert centre.")
        return "\n".join(lines)

    if key == "ipcph":
        lines.append("- Post-capillary PH (IpcPH; PH-LHD): optimize left-heart disease/valvular management first (GDMT, volume control, rhythm/ischemia/valve strategy as indicated).")
        lines.append("- PAH-approved drugs are generally not recommended in PH due to left heart disease; reassess haemodynamics after optimization when it changes management.")
        return "\n".join(lines)

    if key == "cpcph":
        lines.append("- Post-capillary PH with pre-capillary component (CpcPH): optimize left-heart disease first; consider PH/HF expert-centre referral, especially with RV dysfunction or advanced HF.")
        if (not is_nan(pvr_wu)) and pvr_wu >= 5.0:
            lines.append("- PVR ≥ 5 WU suggests severe pulmonary vascular disease: prioritize expert-centre management; consider advanced HF pathways (including transplant/LVAD evaluation where clinically appropriate).")
        lines.append("- PAH-approved drugs are not routinely recommended in PH-LHD; any targeted therapy should be individualized within an expert centre and appropriate diagnostic context.")
        return "\n".join(lines)

    # unknown / edge
    lines.append("- Haemodynamic pattern uncertain: complete work-up (repeat measures, volume status, echo/CTEPH screen, lung/left-heart evaluation) and manage in specialist setting if needed.")
    return "\n".join(lines)


def save_txt(report, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
        f.write("\n")


def try_print_file(path):
    try:
        sysname = platform.system()
        if sysname == "Windows":
            os.startfile(path, "print")  # type: ignore[attr-defined]
            return True, "Sent to printer via Windows shell."
        subprocess.run(["lp", path], check=False)
        return True, "Sent to printer via lp."
    except Exception as e:
        return False, str(e)


def main():
    run_ts = datetime.now()
    run_ts_str = run_ts.strftime("%Y-%m-%d %H:%M")
    banner(run_ts_str)

    patient_name = s_input("Patient name", "", example="Eugene Braunwald")
    patient_id = s_input("Patient ID/MBO")
    operator_name = s_input("Physician/Operator")
    institution = s_input("Institution", DEFAULT_INSTITUTION)

    height_cm = f_input("Height (cm)", 175)
    weight_kg = f_input("Weight (kg)", 80)

    hb_in = f_input("Hemoglobin (g/L)", 140)
    hb_g_L, hb_g_dl, hb_corrected = hb_gL_to_gdL(hb_in)

    bsa = bsa_mosteller(height_cm, weight_kg)

    sao2 = f_input("Radial artery SaO2 (%)", 95)
    svc = f_input("SVC saturation (%) (blank if N/A)", allow_blank=True, example=65)
    ivc = f_input("IVC saturation (%) (blank if N/A)", allow_blank=True, example=70)
    ra_sat = f_input("RA saturation (%) (blank if N/A)", allow_blank=True, example=65)
    rv_sat = f_input("RV saturation (%) (blank if N/A)", allow_blank=True, example=65)
    pa_sat = f_input("PA saturation (%) (blank if N/A)", allow_blank=True, example=65)

    svo2, svo2_source = pick_mixed_venous_sat(pa_sat, ra_sat, rv_sat, svc, ivc)

    ra_mean = f_input("RA mean pressure (mmHg)", 10)
    pa_sys = f_input("PA systolic (mmHg)", 40,)
    pa_dia = f_input("PA diastolic (mmHg)", 20)
    mpap = mean_from_sys_dia(pa_sys, pa_dia)  # AUTO mPAP
    pcwp = f_input("PCWP mean (mmHg)", 15)
    hr = f_input("Heart rate (bpm)", 70, example=70)

    sbp = f_input("Systemic SBP (mmHg) (blank if N/A)", allow_blank=True, example=120)
    dbp = None
    if sbp is not None:
        dbp = f_input("Systemic DBP (mmHg)", 70, example=70)

    vo2_measured = f_input("Measured VO2 (mL/min) (blank to estimate 3.5 mL/kg/min × weight)", allow_blank=True, example=250)
    if vo2_measured is None:
        vo2 = 3.5 * weight_kg
        vo2_source = "estimated (3.5 mL/kg/min × weight)"
    else:
        vo2 = vo2_measured
        vo2_source = "measured"

    ca = o2_content_ml_per_dl(hb_g_dl, sao2 / 100.0)
    cv = o2_content_ml_per_dl(hb_g_dl, svo2 / 100.0)
    av_diff = max(ca - cv, 1e-9)
    co = (vo2 / av_diff) / 10.0

    ci = safe_div(co, bsa)
    sv = safe_div(co * 1000.0, hr)
    svi = safe_div(sv, bsa)

    tpg = mpap - pcwp
    dpg = pa_dia - pcwp
    pvr_wu = safe_div((mpap - pcwp), co)
    pvr_dyn = pvr_wu * DYNE_PER_WU
    pvri = pvr_wu * bsa if not is_nan(bsa) else float("nan")

    papi = safe_div((pa_sys - pa_dia), ra_mean)
    rap_pcwp = safe_div(ra_mean, pcwp)
    pac = safe_div(sv, (pa_sys - pa_dia))

    rvswi = svi * (mpap - ra_mean) * RVSWI_FACTOR

    map_mmHg = None
    svr_wu = None
    svr_dyn = None
    svri = None
    cpo = None
    cpi = None
    if sbp is not None and dbp is not None:
        map_mmHg = map_from_sbp_dbp(sbp, dbp)
        svr_wu = safe_div((map_mmHg - ra_mean), co)
        svr_dyn = svr_wu * DYNE_PER_WU
        svri = svr_wu * bsa if not is_nan(bsa) else float("nan")
        cpo = (map_mmHg * co) / 451.0
        cpi = (map_mmHg * ci) / 451.0

    qpqs, qpqs_note = compute_qpqs_o2content(hb_g_dl, sao2, svo2, pa_sat)
    shunt_text = interpret_shunt(qpqs)

    flag_co = classify_range(co, low=4.0, high=8.0)
    flag_ci = classify_range(ci, low=2.2, high=4.0)
    flag_sv = classify_range(sv, low=55.0, high=100.0)
    flag_svi = classify_range(svi, low=33.0, high=47.0)

    flag_rap = classify_range(ra_mean, low=0.0, high=8.0, high_label="HIGH")
    flag_pcwp = classify_range(pcwp, low=4.0, high=12.0, high_label="HIGH")

    flag_pvr = classify_threshold(pvr_wu, threshold=2.0, abnormal_label="ELEVATED", direction="gt")
    flag_pvr_sev = pvr_severity(pvr_wu)
    flag_tpg = classify_threshold(tpg, threshold=12.0, abnormal_label="ELEVATED", direction="gt")
    flag_dpg = classify_threshold(dpg, threshold=7.0, abnormal_label="ELEVATED", direction="gt")

    if is_nan(papi):
        flag_papi = "N/A"
    elif papi < 0.9:
        flag_papi = "LOW"
    elif papi < 1.5:
        flag_papi = "BORDERLINE"
    else:
        flag_papi = "OK"

    if is_nan(rap_pcwp):
        flag_rap_pcwp = "N/A"
    elif rap_pcwp >= 1.0:
        flag_rap_pcwp = "VERY HIGH"
    elif rap_pcwp >= 0.47:
        flag_rap_pcwp = "HIGH"
    else:
        flag_rap_pcwp = "OK"

    if is_nan(pac):
        flag_pac = "N/A"
    elif pac < 2.15:
        flag_pac = "LOW"
    elif pac < 3.0:
        flag_pac = "BORDERLINE"
    else:
        flag_pac = "OK"

    if cpo is None or is_nan(cpo):
        flag_cpo = "N/A"
    elif cpo < 0.6:
        flag_cpo = "LOW (severe)"
    elif cpo < 0.8:
        flag_cpo = "LOW"
    elif cpo <= 1.1:
        flag_cpo = "NORMAL"
    else:
        flag_cpo = "HIGH"

    if cpi is None or is_nan(cpi):
        flag_cpi = "N/A"
    elif cpi < 0.4:
        flag_cpi = "LOW (severe)"
    elif cpi < 0.6:
        flag_cpi = "LOW"
    elif cpi <= 0.8:
        flag_cpi = "NORMAL"
    else:
        flag_cpi = "HIGH"

    flag_rvswi = classify_range(rvswi, low=5.0, high=10.0)

    ph_class = interpret_ph_esc_ers(mpap, pcwp, pvr_wu)

    alerts = []
    if not is_nan(pvr_wu) and pvr_wu >= 5.0:
        alerts.append("PVR ≥ 5 WU: SEVERE pulmonary vascular disease / high transplant risk.")
    elif not is_nan(pvr_wu) and pvr_wu > 3.0:
        alerts.append("PVR > 3 WU: elevated PVR (Tx/LVAD evaluation often considers reversibility).")
    if tpg >= 15.0:
        alerts.append("TPG ≥ 15 mmHg: elevated transpulmonary gradient (Tx risk marker).")
    if ra_mean >= 15.0:
        alerts.append("RAP ≥ 15 mmHg: high right-sided filling pressure.")
    if ci < 2.0:
        alerts.append("CI < 2.0 L/min/m²: low cardiac index.")
    if (cpo is not None) and (not is_nan(cpo)) and cpo < 0.6:
        alerts.append("CPO < 0.6 W: severe low-output state.")
    if (not is_nan(papi)) and papi < 0.9:
        alerts.append("PAPi < 0.9: suggests significant RV dysfunction risk.")
    if (not is_nan(rap_pcwp)) and rap_pcwp >= 1.0:
        alerts.append("RAP/PCWP ≥ 1.0: disproportionate RV failure pattern.")

    lines = []
    lines.append(f"{APP_NAME} – RHC Hemodynamics Report")
    lines.append(f"Author: {APP_AUTHOR} | Version: {APP_VERSION}")
    lines.append(f"Run timestamp: {run_ts_str}")
    lines.append("")
    if patient_name:
        lines.append(f"Patient: {patient_name}")
    if patient_id:
        lines.append(f"Patient ID: {patient_id}")
    lines.append(f"Institution: {institution}")
    lines.append(f"Physician/Operator: {operator_name}")
    lines.append("")

    if hb_corrected:
        lines.append("Hb input looked like g/dL; auto-converted to g/L.")
        lines.append("")

    lines.append(f"Height: {height_cm:.1f} cm | Weight: {weight_kg:.1f} kg | BSA: {bsa:.2f} m²")
    lines.append(f"Hb: {hb_g_L:.0f} g/L (={hb_g_dl:.1f} g/dL)")
    lines.append(f"SaO2: {sao2:.1f}% | SvO2 used: {svo2:.1f}% (source: {svo2_source})")
    if pa_sat is not None:
        lines.append(f"PA sat (SpaO2): {pa_sat:.1f}%")
    lines.append(f"VO2: {vo2:.0f} mL/min ({vo2_source})")
    lines.append("")

    lines.append("Calculated flow / pump performance:")
    lines.append(f"  CO (Fick): {co:.2f} L/min [{flag_co}]")
    lines.append(f"  CI: {ci:.2f} L/min/m² [{flag_ci}]")
    lines.append(f"  SV: {sv:.0f} mL/beat [{flag_sv}]")
    lines.append(f"  SVI: {svi:.1f} mL/beat/m² [{flag_svi}]")
    if cpo is not None:
        lines.append(f"  CPO: {cpo:.2f} W [{flag_cpo}]")
    if cpi is not None:
        lines.append(f"  CPI: {cpi:.2f} W/m² [{flag_cpi}]")
    lines.append("")

    lines.append("Pressures & pulmonary vascular indices:")
    lines.append(f"  RAP(mean): {ra_mean:.1f} mmHg [{flag_rap}]")
    lines.append(f"  PA: {pa_sys:.1f}/{pa_dia:.1f} mmHg | mPAP (auto): {mpap:.1f} mmHg")
    lines.append(f"  PCWP(mean): {pcwp:.1f} mmHg [{flag_pcwp}]")
    lines.append(f"  TPG: {tpg:.1f} mmHg [{flag_tpg}]")
    lines.append(f"  DPG: {dpg:.1f} mmHg [{flag_dpg}]")
    lines.append(f"  PVR: {pvr_wu:.2f} WU [{flag_pvr}] | Severity: {flag_pvr_sev}")
    lines.append(f"       ({pvr_dyn:.0f} dyn·s/cm⁵) | PVRI: {pvri:.2f} WU·m²")
    lines.append(f"  PAPi: {papi:.2f} [{flag_papi}]")
    lines.append(f"  RAP/PCWP: {rap_pcwp:.2f} [{flag_rap_pcwp}]")
    lines.append(f"  PA compliance (SV/PP): {pac:.2f} mL/mmHg [{flag_pac}]")
    lines.append(f"  RVSWI: {rvswi:.1f} g·m/m²/beat [{flag_rvswi}]")
    lines.append("")

    lines.append("Shunt assessment (Qp/Qs):")
    if is_nan(qpqs):
        lines.append(f"  Qp/Qs: N/A ({qpqs_note})")
    else:
        lines.append(f"  Qp/Qs: {qpqs:.2f} ({qpqs_note})")
    lines.append(f"  {shunt_text}")
    lines.append("")

    if map_mmHg is not None:
        lines.append("Systemic:")
        lines.append(f"  SBP/DBP: {sbp:.0f}/{dbp:.0f} mmHg | MAP: {map_mmHg:.1f} mmHg")
        lines.append(f"  SVR: {svr_wu:.2f} WU ({svr_dyn:.0f} dyn·s/cm⁵) | SVRI: {svri:.2f} WU·m²")
        lines.append("")

    lines.append("Final ESC/ERS PH classification (hemodynamics):")
    lines.append(f"  {ph_class}")
    lines.append("")

    if alerts:
        lines.append("Advanced HF/Transplant alerts:")
        for a in alerts:
            lines.append(f"  - {a}")
        lines.append("")

    # >>> Appended treatment section (only addition requested) <<<
    lines.append("Treatment summary (appended):")
    lines.append(treatment_recommendations_block(mpap, pcwp, pvr_wu))
    lines.append("")
    lines.append("NOTE: Treatment section is high-level and depends on PH group (1–5) + full diagnostic work-up.")

    report = "\n".join(lines)
    print("\n" + report + "\n")

    print("Export options:")
    print("  1) TXT")
    print("  2) NONE")
    choice = s_input("Choose export (1/2)", "2", example="1").strip()

    saved_path = None
    if choice == "1":
        filename = s_input("Enter .txt filename", f"Hemy_Report_{run_ts.strftime('%Y%m%d_%H%M')}.txt", example="Hemy_Report_20260106_1215.txt")
        if not filename.lower().endswith(".txt"):
            filename += ".txt"
        save_txt(report, filename)
        saved_path = filename
        print(f"Saved TXT: {filename}")
    else:
        print("No export selected.")

    if saved_path:
        do_print = s_input("Print now? (y/n)", "n", example="y").lower().strip()
        if do_print == "y":
            ok, msg = try_print_file(saved_path)
            print("Print:", "OK" if ok else "FAILED", "-", msg)


if __name__ == "__main__":
    main()

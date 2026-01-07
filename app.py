# Hemmy Web - Hemodynamic RHC Calculator
# Author: Josip A. Borovac, MD, PhD
# Web version: 1.4.0
# Adapted for Flask web deployment

from flask import Flask, render_template, request
import math
from datetime import datetime

app = Flask(__name__)

APP_NAME = "HEMMY"
APP_AUTHOR = "Josip A. Borovac, MD, PhD"
APP_VERSION = "1.4.0 (Web)"
DEFAULT_INSTITUTION = "Department of Cardiovascular Diseases, University Hospital of Split"

HUFNER = 1.34
DYNE_PER_WU = 80.0
RVSWI_FACTOR = 0.0136


def safe_float(value, default=None):
    """Convert to float, return default if empty/invalid."""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


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
    if is_nan(mpap) or is_nan(pcwp) or is_nan(pvr_wu):
        return "unknown"
    if mpap <= 20:
        return "no_ph"
    if pcwp <= 15:
        return "precap" if pvr_wu > 2 else "ph_pvr_le2"
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
    key = ph_phenotype_key(mpap, pcwp, pvr_wu)
    lines = []
    lines.append("Treatment options (ESC/ERS-aligned, haemodynamic phenotype-based; high-level):")

    if key == "no_ph":
        lines.append("- No haemodynamic PH (mPAP ≤ 20): treat underlying condition; follow clinically.")
        return "\n".join(lines)

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

    lines.append("- Haemodynamic pattern uncertain: complete work-up (repeat measures, volume status, echo/CTEPH screen, lung/left-heart evaluation) and manage in specialist setting if needed.")
    return "\n".join(lines)


@app.route('/')
def index():
    return render_template('index.html',
                         app_name=APP_NAME,
                         app_version=APP_VERSION,
                         app_author=APP_AUTHOR,
                         default_institution=DEFAULT_INSTITUTION)


@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        # Get form data
        patient_name = request.form.get('patient_name', '')
        patient_id = request.form.get('patient_id', '')
        operator_name = request.form.get('operator_name', '')
        institution = request.form.get('institution', DEFAULT_INSTITUTION)

        # Anthropometrics
        height_cm = safe_float(request.form.get('height_cm'), 175)
        weight_kg = safe_float(request.form.get('weight_kg'), 80)
        hb_in = safe_float(request.form.get('hb'), 140)

        # Saturations
        sao2 = safe_float(request.form.get('sao2'), 95)
        svc = safe_float(request.form.get('svc'))
        ivc = safe_float(request.form.get('ivc'))
        ra_sat = safe_float(request.form.get('ra_sat'))
        rv_sat = safe_float(request.form.get('rv_sat'))
        pa_sat = safe_float(request.form.get('pa_sat'))

        # Pressures
        ra_mean = safe_float(request.form.get('ra_mean'), 10)
        pa_sys = safe_float(request.form.get('pa_sys'), 40)
        pa_dia = safe_float(request.form.get('pa_dia'), 20)
        pcwp = safe_float(request.form.get('pcwp'), 15)
        hr = safe_float(request.form.get('hr'), 70)

        sbp = safe_float(request.form.get('sbp'))
        dbp = safe_float(request.form.get('dbp'))

        vo2_measured = safe_float(request.form.get('vo2'))

        # Calculations
        hb_g_L, hb_g_dl, hb_corrected = hb_gL_to_gdL(hb_in)
        bsa = bsa_mosteller(height_cm, weight_kg)

        svo2, svo2_source = pick_mixed_venous_sat(pa_sat, ra_sat, rv_sat, svc, ivc)

        mpap = mean_from_sys_dia(pa_sys, pa_dia)

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

        # Classifications
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

        # Alerts
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

        treatment_text = treatment_recommendations_block(mpap, pcwp, pvr_wu)

        run_ts_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Prepare results dictionary
        results = {
            'timestamp': run_ts_str,
            'patient_name': patient_name,
            'patient_id': patient_id,
            'operator_name': operator_name,
            'institution': institution,
            'height_cm': height_cm,
            'weight_kg': weight_kg,
            'bsa': bsa,
            'hb_g_L': hb_g_L,
            'hb_g_dl': hb_g_dl,
            'hb_corrected': hb_corrected,
            'sao2': sao2,
            'svo2': svo2,
            'svo2_source': svo2_source,
            'pa_sat': pa_sat,
            'vo2': vo2,
            'vo2_source': vo2_source,
            'co': co,
            'ci': ci,
            'sv': sv,
            'svi': svi,
            'ra_mean': ra_mean,
            'pa_sys': pa_sys,
            'pa_dia': pa_dia,
            'mpap': mpap,
            'pcwp': pcwp,
            'tpg': tpg,
            'dpg': dpg,
            'pvr_wu': pvr_wu,
            'pvr_dyn': pvr_dyn,
            'pvri': pvri,
            'papi': papi,
            'rap_pcwp': rap_pcwp,
            'pac': pac,
            'rvswi': rvswi,
            'qpqs': qpqs,
            'qpqs_note': qpqs_note,
            'shunt_text': shunt_text,
            'flag_co': flag_co,
            'flag_ci': flag_ci,
            'flag_sv': flag_sv,
            'flag_svi': flag_svi,
            'flag_rap': flag_rap,
            'flag_pcwp': flag_pcwp,
            'flag_pvr': flag_pvr,
            'flag_pvr_sev': flag_pvr_sev,
            'flag_tpg': flag_tpg,
            'flag_dpg': flag_dpg,
            'flag_papi': flag_papi,
            'flag_rap_pcwp': flag_rap_pcwp,
            'flag_pac': flag_pac,
            'flag_cpo': flag_cpo,
            'flag_cpi': flag_cpi,
            'flag_rvswi': flag_rvswi,
            'ph_class': ph_class,
            'alerts': alerts,
            'treatment_text': treatment_text,
            'map_mmHg': map_mmHg,
            'svr_wu': svr_wu,
            'svr_dyn': svr_dyn,
            'svri': svri,
            'cpo': cpo,
            'cpi': cpi,
            'sbp': sbp,
            'dbp': dbp,
        }

        return render_template('results.html',
                             app_name=APP_NAME,
                             app_version=APP_VERSION,
                             app_author=APP_AUTHOR,
                             **results)

    except Exception as e:
        return f"Error in calculation: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

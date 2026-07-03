"""
openIMIS Claims Fraud Triage — demo UI
=======================================
A Streamlit front end for the `fraud_detect` openIMIS backend module.

Every screen maps directly onto the module's real REST API:

  GET  /api/fraud_detect/flags/            -> Triage dashboard
  GET  /api/fraud_detect/flags/{claim_id}/ -> Review a claim
  POST /api/fraud_detect/score/            -> Score a claim (on demand, no DB write)
  POST /api/fraud_detect/rescore/{id}/     -> Re-score a saved claim (persists)
  POST /api/fraud_detect/override/         -> Reviewer override

Run:  streamlit run app.py
"""

from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Page config + visual identity
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Claims Fraud Triage",
    page_icon="🩺",
    layout="wide",
)

RISK_COLORS = {"HIGH": "#C24634", "MEDIUM": "#D89317", "LOW": "#2E7D5B"}
RISK_BG = {"HIGH": "#F9E7E3", "MEDIUM": "#FBF0DA", "LOW": "#E4F1EA"}
INK = "#0F3D3E"
ACCENT = "#147D74"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {{ color: {INK}; }}
    .stApp {{ background: #FAFBF9; }}

    h1, h2, h3 {{ font-family: 'Sora', sans-serif !important; color: {INK}; }}

    .mono {{ font-family: 'IBM Plex Mono', monospace; }}

    .risk-chip {{
        display: inline-block; padding: 2px 12px; border-radius: 999px;
        font-family: 'IBM Plex Mono', monospace; font-weight: 500; font-size: 0.85rem;
    }}
    .desk-header {{
        border-left: 6px solid {ACCENT}; padding: 4px 0 4px 16px; margin-bottom: 4px;
    }}
    .desk-header .sub {{ color: #5A6B6A; font-size: 0.95rem; }}

    .rule-card {{
        border: 1px solid #E3E8E5; border-left: 4px solid {RISK_COLORS['HIGH']};
        border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; background: white;
    }}
    .rule-card .rule-name {{ font-weight: 600; }}
    .rule-card .rule-desc {{ color: #4A5A58; font-size: 0.9rem; }}

    div[data-testid="stMetric"] {{
        background: white; border: 1px solid #E3E8E5; border-radius: 8px; padding: 10px 14px;
    }}
    div[data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def risk_chip(level: str) -> str:
    color = RISK_COLORS.get(level, "#5A6B6A")
    bg = RISK_BG.get(level, "#EEE")
    return (
        f'<span class="risk-chip" style="color:{color};background:{bg};'
        f'border:1px solid {color}">{level}</span>'
    )


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    token = st.session_state.get("auth_token", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_get(path: str, params: dict | None = None):
    base = st.session_state["api_base"].rstrip("/")
    return requests.get(f"{base}{path}", params=params, headers=_headers(), timeout=15)


def api_post(path: str, payload: dict):
    base = st.session_state["api_base"].rstrip("/")
    return requests.post(f"{base}{path}", json=payload, headers=_headers(), timeout=30)


def friendly_error(exc: Exception) -> None:
    st.error(
        "Could not reach the fraud detection API. "
        "Check that the openIMIS Docker stack is running and that the "
        "API base URL in the sidebar is correct."
    )
    st.caption(f"Detail: {exc}")


# ---------------------------------------------------------------------------
# Sidebar — connection settings + reference
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Connection")
    st.text_input(
        "API base URL",
        value=st.session_state.get("api_base", "http://localhost/api/fraud_detect"),
        key="api_base",
        help="The fraud_detect module mount point inside openIMIS.",
    )
    st.text_input(
        "Bearer token (optional)",
        value=st.session_state.get("auth_token", ""),
        key="auth_token",
        type="password",
        help="Leave empty if the API is open in your environment.",
    )
    if st.button("Test connection"):
        try:
            r = api_get("/flags/", params={"limit": 1})
            if r.ok:
                st.success(f"Connected — {r.json().get('count', 0)} claims scored so far.")
            else:
                st.warning(f"API answered with HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            friendly_error(exc)

    st.divider()
    st.markdown("### How a claim is categorized")
    st.caption(
        "Each claim passes through **5 business rules** and an **Isolation Forest** "
        "anomaly model. The two verdicts combine into one risk level:"
    )
    st.markdown(
        f"""
- {risk_chip("HIGH")} rules **and** ML both flag it, or **2+ rules** fire
- {risk_chip("MEDIUM")} exactly one of the two flags it, or the ML score is a near-miss
- {risk_chip("LOW")} all clear
""",
        unsafe_allow_html=True,
    )

    with st.expander("The 5 rules"):
        st.markdown(
            """
1. **Claim lag exceeds 90 days** — filed long after the service date
2. **Invoice inflation above 3×** — invoiced far more than was approved
3. **Vague ICD code used** — e.g. Z51.9 "medical care, unspecified"
4. **Claim filed after audit date** — logically impossible; suggests tampering
5. **High-value claim with vague diagnosis** — above 20,000 KES without a precise code
"""
        )
    st.caption("Anomaly score: more negative = more suspicious.")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="desk-header">
      <h1 style="margin-bottom:0">Claims Fraud Triage</h1>
      <div class="sub">Rules + machine learning working together on every claim — openIMIS <span class="mono">fraud_detect</span> module</div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_dash, tab_score, tab_review = st.tabs(
    ["📋  Triage dashboard", "⚖️  Score a claim", "👤  Review & override"]
)


# ---------------------------------------------------------------------------
# Tab 1 — Triage dashboard (GET /flags/)
# ---------------------------------------------------------------------------

with tab_dash:
    top_l, top_r = st.columns([3, 1])
    with top_r:
        risk_filter = st.selectbox("Show", ["All risk levels", "HIGH", "MEDIUM", "LOW"])
        limit = st.slider("Rows", 25, 500, 100, step=25)
        refresh = st.button("Refresh", use_container_width=True)

    params = {"limit": limit}
    if risk_filter != "All risk levels":
        params["risk_level"] = risk_filter

    flags_payload = None
    try:
        r = api_get("/flags/", params=params)
        if r.ok:
            flags_payload = r.json()
        else:
            st.warning(f"API answered with HTTP {r.status_code}: {r.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        friendly_error(exc)

    if flags_payload is not None:
        results = flags_payload.get("results", [])
        df = pd.DataFrame(results)

        # Headline counters — computed over the fetched page
        with top_l:
            if df.empty:
                st.info(
                    "No claims have been scored yet. Seed demo claims in the backend "
                    "(`python manage.py seed_demo_claims`) or submit a claim through "
                    "openIMIS, then refresh."
                )
            else:
                counts = df["overall_risk_level"].value_counts()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Claims scored", f"{flags_payload.get('count', len(df)):,}")
                c2.metric("High risk", int(counts.get("HIGH", 0)))
                c3.metric("Medium risk", int(counts.get("MEDIUM", 0)))
                c4.metric("Low risk", int(counts.get("LOW", 0)))

        if not df.empty:
            # Claim log table
            show = df.copy()
            show["rules fired"] = show["rule_flag_reasons"].apply(len)
            show["anomaly_score"] = show["anomaly_score"].map(
                lambda v: None if v is None else round(float(v), 4)
            )
            show = show[
                [
                    "claim_id",
                    "overall_risk_level",
                    "rules fired",
                    "is_ml_anomaly",
                    "anomaly_score",
                    "updated_at",
                ]
            ].rename(
                columns={
                    "claim_id": "Claim ID",
                    "overall_risk_level": "Risk",
                    "is_ml_anomaly": "ML anomaly",
                    "anomaly_score": "Anomaly score",
                    "updated_at": "Last scored",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)

            # Distribution charts
            ch1, ch2 = st.columns(2)
            with ch1:
                st.caption("Risk level distribution")
                dist = (
                    df["overall_risk_level"]
                    .value_counts()
                    .reindex(["HIGH", "MEDIUM", "LOW"])
                    .fillna(0)
                )
                st.bar_chart(dist, color=ACCENT)
            with ch2:
                st.caption("Anomaly score distribution (more negative = more suspicious)")
                scores = df["anomaly_score"].dropna()
                if scores.empty:
                    st.caption("No ML scores recorded yet.")
                else:
                    hist = pd.cut(scores.astype(float), bins=20).value_counts().sort_index()
                    hist.index = [f"{iv.left:.2f}" for iv in hist.index]
                    st.bar_chart(hist, color=ACCENT)


# ---------------------------------------------------------------------------
# Tab 2 — Score a claim on demand (POST /score/)
# ---------------------------------------------------------------------------

PRESETS = {
    "Clean claim": dict(
        claimed_amount=3_500.0, approved_amount=3_500.0,
        lag_days=7, icd_code="J06.9", include_audit=False, audit_offset=0,
    ),
    "Inflated invoice": dict(
        claimed_amount=48_000.0, approved_amount=9_000.0,
        lag_days=12, icd_code="K35.8", include_audit=False, audit_offset=0,
    ),
    "Late + vague diagnosis": dict(
        claimed_amount=26_000.0, approved_amount=22_000.0,
        lag_days=120, icd_code="Z51.9", include_audit=False, audit_offset=0,
    ),
}

with tab_score:
    st.caption(
        "Runs a claim through the rules engine and the ML model **without saving "
        "anything** — the module's on-demand scoring endpoint. Useful for previewing "
        "how a claim would be assessed."
    )

    preset_cols = st.columns(len(PRESETS) + 1)
    preset_cols[0].markdown("**Try an example:**")
    for i, (label, values) in enumerate(PRESETS.items(), start=1):
        if preset_cols[i].button(label, use_container_width=True):
            st.session_state["preset"] = values

    p = st.session_state.get("preset", PRESETS["Clean claim"])

    with st.form("score_form"):
        f1, f2, f3 = st.columns(3)
        claimed_amount = f1.number_input(
            "Invoiced amount (KES)", min_value=0.0, value=float(p["claimed_amount"]), step=500.0
        )
        approved_amount = f2.number_input(
            "Approved amount (KES)", min_value=0.0, value=float(p["approved_amount"]), step=500.0
        )
        icd_code = f3.text_input("Primary ICD-10 code", value=p["icd_code"])

        d1, d2, d3 = st.columns(3)
        date_from = d1.date_input("Service date", value=date.today() - timedelta(days=p["lag_days"]))
        date_claimed = d2.date_input("Date claim submitted", value=date.today())
        with d3:
            include_audit = st.checkbox("Claim was audited", value=p["include_audit"])
            audit_date = st.date_input(
                "Audit date", value=date.today() - timedelta(days=p["audit_offset"]),
                disabled=not include_audit,
            )

        submitted = st.form_submit_button("Assess this claim", type="primary")

    if submitted:
        payload = {
            "claimed_amount": claimed_amount,
            "approved_amount": approved_amount,
            "icd_code": icd_code.strip(),
            "date_from": str(date_from),
            "date_claimed": str(date_claimed),
        }
        if include_audit:
            payload["audit_date"] = str(audit_date)

        try:
            with st.spinner("Scoring…"):
                r = api_post("/score/", payload)
            if not r.ok:
                st.warning(f"API answered with HTTP {r.status_code}: {r.text[:300]}")
            else:
                out = r.json()
                level = out.get("overall_risk_level", "LOW")
                rules = out.get("rules", {})
                ml = out.get("ml", {})

                st.markdown("---")
                h1, h2, h3 = st.columns([1, 1, 2])
                h1.markdown(
                    f"##### Overall assessment<br>{risk_chip(level)}", unsafe_allow_html=True
                )
                score_val = ml.get("anomaly_score")
                h2.metric(
                    "ML anomaly score",
                    "—" if score_val is None else f"{score_val:.4f}",
                    help="Isolation Forest decision score. More negative = more suspicious.",
                )
                h3.metric(
                    "ML verdict",
                    "Anomaly" if ml.get("is_anomaly") else "Normal pattern",
                )

                fired = rules.get("fired_rules", [])
                if fired:
                    st.markdown(f"**{len(fired)} rule{'s' if len(fired) != 1 else ''} fired:**")
                    for rule in fired:
                        st.markdown(
                            f"""<div class="rule-card">
                                <div class="rule-name">⚠️ {rule.get("name", "")}</div>
                                <div class="rule-desc">{rule.get("description", "")}</div>
                            </div>""",
                            unsafe_allow_html=True,
                        )
                else:
                    st.success("No business rules fired for this claim.")

                # Explain the categorization using the module's actual decision matrix
                n_fired = len(fired)
                is_anom = bool(ml.get("is_anomaly"))
                if n_fired >= 2:
                    why = "two or more independent rules fired"
                elif n_fired >= 1 and is_anom:
                    why = "both the rules engine and the ML model flagged it"
                elif n_fired >= 1 or is_anom:
                    why = "exactly one of the two systems flagged it"
                elif (score_val is not None) and score_val < -0.1:
                    why = "no flags, but the ML score was a near-miss"
                else:
                    why = "neither the rules engine nor the ML model found anything unusual"
                st.caption(f"Categorized **{level}** because {why}.")
        except Exception as exc:  # noqa: BLE001
            friendly_error(exc)


# ---------------------------------------------------------------------------
# Tab 3 — Review & override (GET /flags/{id}, POST /rescore/{id}, POST /override/)
# ---------------------------------------------------------------------------

with tab_review:
    st.caption(
        "The human-in-the-loop step: look up a scored claim, re-score it against the "
        "live database record, and record a reviewer decision. Overrides are stored "
        "and feed the retraining pipeline."
    )

    lk1, lk2, lk3 = st.columns([2, 1, 1])
    claim_id = lk1.number_input("Claim ID", min_value=1, step=1, value=st.session_state.get("review_claim_id", 1))
    lookup = lk2.button("Look up", use_container_width=True)
    rescore = lk3.button("Re-score from database", use_container_width=True)

    if lookup or rescore:
        st.session_state["review_claim_id"] = int(claim_id)
        try:
            if rescore:
                with st.spinner("Re-scoring against the live claim record…"):
                    r = api_post(f"/rescore/{int(claim_id)}/", {})
            else:
                r = api_get(f"/flags/{int(claim_id)}/")

            if r.status_code == 404:
                st.warning(
                    f"Claim {int(claim_id)} has no fraud assessment yet. "
                    "If the claim exists in openIMIS, use **Re-score from database** "
                    "to create one."
                )
                st.session_state.pop("review_flag", None)
            elif not r.ok:
                st.warning(f"API answered with HTTP {r.status_code}: {r.text[:300]}")
            else:
                st.session_state["review_flag"] = r.json()
                if rescore:
                    st.success("Claim re-scored and the assessment saved.")
        except Exception as exc:  # noqa: BLE001
            friendly_error(exc)

    flag = st.session_state.get("review_flag")
    if flag and flag.get("claim_id") == int(claim_id):
        st.markdown("---")
        a, b, c = st.columns([1, 1, 2])
        a.markdown(
            f"##### Claim <span class='mono'>{flag['claim_id']}</span><br>{risk_chip(flag.get('overall_risk_level', 'LOW'))}",
            unsafe_allow_html=True,
        )
        sc = flag.get("anomaly_score")
        b.metric("ML anomaly score", "—" if sc is None else f"{float(sc):.4f}")
        c.metric("ML verdict", "Anomaly" if flag.get("is_ml_anomaly") else "Normal pattern")

        reasons = flag.get("rule_flag_reasons", [])
        if reasons:
            st.markdown(f"**{len(reasons)} rule{'s' if len(reasons) != 1 else ''} fired:**")
            for rule in reasons:
                st.markdown(
                    f"""<div class="rule-card">
                        <div class="rule-name">⚠️ {rule.get("name", "")}</div>
                        <div class="rule-desc">{rule.get("description", "")}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.success("No business rules fired for this claim.")

        st.markdown("#### Record your decision")
        with st.form("override_form"):
            o1, o2 = st.columns(2)
            decision = o1.selectbox(
                "Decision",
                ["APPROVE", "REJECT", "ESCALATE"],
                help="Approve the claim, reject it, or escalate for deeper investigation.",
            )
            reviewer_id = o2.number_input("Reviewer ID", min_value=1, step=1, value=1)
            notes = st.text_area("Notes (optional)", placeholder="Why you agree or disagree with the assessment…")
            save = st.form_submit_button("Save decision", type="primary")

        if save:
            try:
                r = api_post(
                    "/override/",
                    {
                        "claim_id": int(claim_id),
                        "reviewer_decision": decision,
                        "reviewer_id": int(reviewer_id),
                        "notes": notes,
                    },
                )
                if r.status_code == 201:
                    st.success(
                        f"Decision saved: claim {int(claim_id)} — {decision}. "
                        "This override is stored and will inform model retraining."
                    )
                else:
                    st.warning(f"API answered with HTTP {r.status_code}: {r.text[:300]}")
            except Exception as exc:  # noqa: BLE001
                friendly_error(exc)

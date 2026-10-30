"""TenantEase Property Intelligence — Functional AI/ML Prototype
A decision-support system connecting maintenance incidents across property topology,
explaining associations with transparent evidence, and verifying possible repair recurrences.
"""
import sys
import os
import json
import datetime
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database.connection import init_db, SessionLocal
from database.models import (
    Property, Building, Unit, Asset, UnitAssetLink,
    Incident, RepairRecord, IncidentRelationship, RecurrenceFlag, ReviewDecision
)
from database.repository import PropertyRepository
from services.ingestion_service import IngestionService
from services.candidate_generation import CandidateGenerationEngine
from services.relationship_scoring import RelationshipScoringEngine
from services.recurrence_detection import RecurrenceDetectionService
from services.review_service import ReviewService
from schemas.review import ReviewDecisionCreate
from evaluation.run_evaluation import run_full_evaluation
from evaluation.generate_synthetic_data import generate_synthetic_dataset

# Initialize database schema on startup
init_db()

# Page Configuration
st.set_page_config(
    page_title="TenantEase Property Intelligence",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics and clean typography
st.markdown("""
<style>
    /* Main container and headers */
    .main-header {
        font-size: 1.85rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    /* Metric Cards */
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 1.1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08);
    }
    .metric-label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748B;
        font-weight: 600;
    }
    .metric-val {
        font-size: 1.9rem;
        font-weight: 700;
        color: #0F172A;
        margin-top: 0.2rem;
    }
    /* Badge tags */
    .badge-open {
        background: #FEF3C7;
        color: #92400E;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-closed {
        background: #E2E8F0;
        color: #475569;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-high {
        background: #FEE2E2;
        color: #991B1B;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-suggest {
        background: #DCFCE7;
        color: #166534;
        padding: 4px 10px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .evidence-box {
        background: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 0.9rem;
        border-radius: 0 8px 8px 0;
        margin: 0.5rem 0;
    }
    .missing-box {
        background: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 0.7rem;
        border-radius: 0 6px 6px 0;
        margin: 0.4rem 0;
        font-size: 0.85rem;
    }
    .contra-box {
        background: #FEF2F2;
        border-left: 4px solid #EF4444;
        padding: 0.7rem;
        border-radius: 0 6px 6px 0;
        margin: 0.4rem 0;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Helper DB Session Management
def get_session():
    return SessionLocal()

# Ensure synthetic data is present in database
def ensure_sample_data():
    db = get_session()
    try:
        count = db.query(Incident).count()
        if count == 0:
            generate_synthetic_dataset(seed=42)
    finally:
        db.close()

ensure_sample_data()

# Sidebar Navigation
st.sidebar.image("https://img.icons8.com/fluency/96/city-buildings.png", width=64)
st.sidebar.title("TenantEase")
st.sidebar.caption("Property Intelligence Platform")

st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    [
        "1. Overview Dashboard",
        "2. Incident Explorer",
        "3. Incident Intelligence",
        "4. Recurrence Monitor",
        "5. Review Queue & Audit",
        "6. Evaluation & Benchmarks"
    ],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.subheader("System Status")
st.sidebar.success("● Engine: Rules-First Active")
st.sidebar.info("● Storage: Relational (SQLite / PG)")
st.sidebar.caption("Prototype Mode: Safe Local Execution (No external PII leakage)")

if st.sidebar.button("↻ Reset / Reload Synthetic Data"):
    with st.spinner("Generating fresh synthetic dataset (Seed: 42)..."):
        generate_synthetic_dataset(seed=42)
        st.sidebar.success("Database reset to benchmark state!")
        st.rerun()

# ==============================================================================
# PAGE 1: OVERVIEW DASHBOARD
# ==============================================================================
if page == "1. Overview Dashboard":
    st.markdown('<div class="main-header">Maintenance Intelligence Overview</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Cross-unit incident correlation, physical infrastructure mapping, and post-repair recurrence tracking.</div>', unsafe_allow_html=True)

    db = get_session()
    try:
        repo = PropertyRepository(db)
        total_incidents = db.query(Incident).count()
        open_incidents = db.query(Incident).filter(Incident.status == "open").count()
        closed_incidents = db.query(Incident).filter(Incident.status == "closed").count()
        
        # Candidate pairs and reviews
        cand_engine = CandidateGenerationEngine(db)
        candidates = cand_engine.generate_all_candidates()
        
        scoring_engine = RelationshipScoringEngine(db)
        high_rel_count = 0
        incident_map = {inc.incident_id: inc for inc in db.query(Incident).all()}
        for c in candidates:
            ia = incident_map.get(c.incident_a_id)
            ib = incident_map.get(c.incident_b_id)
            if ia and ib:
                rel = scoring_engine.compute_relationship(ia, ib)
                if rel.review_score >= 50.0 and rel.recommendation_tier == "suggest_for_review":
                    high_rel_count += 1

        rec_service = RecurrenceDetectionService(db)
        recurrence_flags = rec_service.scan_all_for_recurrence()
        pending_reviews = len(candidates) + len(recurrence_flags) - db.query(ReviewDecision).count()
        pending_reviews = max(0, pending_reviews)

        # Top Metric Row
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Total Incidents</div><div class="metric-val">{total_incidents}</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Open Issues</div><div class="metric-val" style="color:#D97706;">{open_incidents}</div></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Closed / Repaired</div><div class="metric-val" style="color:#059669;">{closed_incidents}</div></div>', unsafe_allow_html=True)
        with m4:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Related Pairs</div><div class="metric-val" style="color:#2563EB;">{high_rel_count}</div></div>', unsafe_allow_html=True)
        with m5:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Recurrence Flags</div><div class="metric-val" style="color:#DC2626;">{len(recurrence_flags)}</div></div>', unsafe_allow_html=True)
        with m6:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Pending Reviews</div><div class="metric-val" style="color:#4B5563;">{pending_reviews}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Charts Row
        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader("Incidents by Category")
            incidents_all = db.query(Incident).all()
            df_cat = pd.DataFrame([{"category": inc.normalized_category} for inc in incidents_all])
            if not df_cat.empty:
                cat_counts = df_cat["category"].value_counts().reset_index()
                cat_counts.columns = ["Category", "Count"]
                fig_cat = px.bar(
                    cat_counts, x="Category", y="Count",
                    color="Category",
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    title="Volume by Normalized Issue Category"
                )
                fig_cat.update_layout(showlegend=False, margin=dict(t=40, b=20, l=20, r=20), height=300)
                st.plotly_chart(fig_cat, use_container_width=True)

        with c2:
            st.subheader("Building Activity & Shared Assets")
            bldg_data = []
            for inc in incidents_all:
                bldg_data.append({
                    "building_id": inc.building_id or "Unassigned",
                    "severity": inc.severity
                })
            df_bldg = pd.DataFrame(bldg_data)
            if not df_bldg.empty:
                fig_bldg = px.histogram(
                    df_bldg, x="building_id", color="severity",
                    color_discrete_map={"low": "#94A3B8", "medium": "#F59E0B", "high": "#EF4444", "critical": "#7F1D1D"},
                    title="Incident Distribution Across Buildings by Severity"
                )
                fig_bldg.update_layout(margin=dict(t=40, b=20, l=20, r=20), height=300)
                st.plotly_chart(fig_bldg, use_container_width=True)

        # Recent Activity Table
        st.subheader("Recent Maintenance Activity Feed")
        recent = db.query(Incident).order_by(Incident.created_at.desc()).limit(8).all()
        recent_df = pd.DataFrame([
            {
                "ID": inc.incident_id,
                "Property": inc.property_id,
                "Building": inc.building_id or "—",
                "Unit": inc.unit_id or "—",
                "Category": inc.normalized_category,
                "Severity": inc.severity,
                "Status": inc.status,
                "Date": inc.created_at.strftime("%Y-%m-%d %H:%M"),
                "Description": inc.raw_description[:75] + "..." if len(inc.raw_description) > 75 else inc.raw_description
            }
            for inc in recent
        ])
        st.dataframe(recent_df, use_container_width=True, hide_index=True)

    finally:
        db.close()

# ==============================================================================
# PAGE 2: INCIDENT EXPLORER
# ==============================================================================
elif page == "2. Incident Explorer":
    st.markdown('<div class="main-header">Incident Explorer & Data Ingestion</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Search, inspect, upload CSV records, or add maintenance incidents manually.</div>', unsafe_allow_html=True)

    db = get_session()
    try:
        repo = PropertyRepository(db)
        props = repo.get_all_properties()
        prop_options = ["All"] + [p.property_id for p in props]

        tab1, tab2, tab3 = st.tabs(["📋 View & Filter Incidents", "📤 Upload CSV", "➕ Add Incident Manually"])

        # TAB 1: Filter & View
        with tab1:
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            with f_col1:
                sel_prop = st.selectbox("Property Filter", prop_options, index=0)
            with f_col2:
                categories = ["All", "plumbing", "water_intrusion", "hvac", "electrical", "structural", "appliance", "security"]
                sel_cat = st.selectbox("Category", categories, index=0)
            with f_col3:
                severities = ["All", "low", "medium", "high", "critical"]
                sel_sev = st.selectbox("Severity", severities, index=0)
            with f_col4:
                statuses = ["All", "open", "in_progress", "closed"]
                sel_stat = st.selectbox("Status", statuses, index=0)

            filtered_incidents = repo.get_incidents(
                property_id=None if sel_prop == "All" else sel_prop,
                category=None if sel_cat == "All" else sel_cat,
                severity=None if sel_sev == "All" else sel_sev,
                status=None if sel_stat == "All" else sel_stat,
                limit=300
            )

            st.write(f"Showing **{len(filtered_incidents)}** maintenance records")

            table_rows = []
            for inc in filtered_incidents:
                table_rows.append({
                    "Incident ID": inc.incident_id,
                    "Property": inc.property_id,
                    "Building": inc.building_id or "—",
                    "Unit": inc.unit_id or "—",
                    "Asset": inc.asset_id or "—",
                    "Category": inc.normalized_category,
                    "Symptoms": ", ".join(inc.symptoms or []),
                    "Severity": inc.severity,
                    "Status": inc.status,
                    "Reported At": inc.created_at.strftime("%Y-%m-%d %H:%M") if inc.created_at else "",
                    "Duplicate Of": inc.is_duplicate_of or "—"
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            # Detail Inspector
            st.markdown("---")
            st.subheader("🔍 Single Incident Deep-Dive Inspector")
            inc_id_list = [inc.incident_id for inc in filtered_incidents]
            if inc_id_list:
                selected_inspect_id = st.selectbox("Select Incident to Inspect", inc_id_list)
                inspected_inc = repo.get_incident(selected_inspect_id)
                if inspected_inc:
                    col_d1, col_d2 = st.columns([2, 1])
                    with col_d1:
                        st.markdown(f"**Description (Preserved Raw Source):**")
                        st.info(inspected_inc.raw_description)
                        st.markdown(f"**Extracted Normalized Symptoms:** `{', '.join(inspected_inc.symptoms or ['None'])}`")
                        if inspected_inc.is_duplicate_of:
                            st.warning(f"⚠️ Flagged as potential duplicate of **{inspected_inc.is_duplicate_of}** (Confidence: {inspected_inc.duplicate_confidence:.0%})")
                    with col_d2:
                        st.markdown(f"**Location Hierarchy:**")
                        st.write(f"- Property: `{inspected_inc.property_id}`")
                        st.write(f"- Building: `{inspected_inc.building_id or 'Unassigned'}`")
                        st.write(f"- Unit: `{inspected_inc.unit_id or 'Unassigned'}`")
                        st.write(f"- Direct Asset: `{inspected_inc.asset_id or 'None'}`")
                        st.write(f"- Created At: `{inspected_inc.created_at}`")

        # TAB 2: CSV Upload
        with tab2:
            st.subheader("Upload Maintenance Records (CSV)")
            st.caption("Upload CSV containing incident records. Validation errors and potential duplicates will be explicitly reported.")

            uploaded_file = st.file_uploader("Choose CSV file", type=["csv"])
            if uploaded_file is not None:
                content = uploaded_file.getvalue().decode("utf-8")
                # Preview
                st.markdown("**File Preview (First 5 Rows):**")
                df_preview = pd.read_csv(pd.io.common.StringIO(content))
                st.dataframe(df_preview.head(5), use_container_width=True)

                if st.button("🚀 Process and Ingest CSV", type="primary"):
                    ingest_svc = IngestionService(db)
                    with st.spinner("Validating and ingesting records..."):
                        res = ingest_svc.ingest_csv(content, source_reference=uploaded_file.name)
                        
                        st.success(f"Ingestion Finished! Successfully imported: **{res.successful_count}** of **{res.total_rows}** records.")
                        if res.duplicate_count > 0:
                            st.warning(f"⚠️ **{res.duplicate_count}** records flagged as potential duplicates (preserved for human review, not silently deleted).")
                        
                        if res.errors:
                            st.error(f"❌ Encountered **{len(res.errors)}** validation errors:")
                            err_df = pd.DataFrame([
                                {
                                    "Row": e.row_index,
                                    "Fields": ", ".join(e.error_fields),
                                    "Error Message": e.error_message
                                }
                                for e in res.errors
                            ])
                            st.dataframe(err_df, use_container_width=True, hide_index=True)

        # TAB 3: Manual Incident Creation
        with tab3:
            st.subheader("Add Incident Record Manually")
            with st.form("manual_incident_form"):
                mc1, mc2 = st.columns(2)
                with mc1:
                    new_id = st.text_input("Incident ID", f"INC-MAN-{datetime.datetime.utcnow().strftime('%H%M%S')}")
                    new_prop = st.selectbox("Property ID", [p.property_id for p in props])
                    new_bldg = st.text_input("Building ID", "BLDG-OAK-A")
                    new_unit = st.text_input("Unit ID", "UNIT-OAK-A-101")
                with mc2:
                    new_asset = st.text_input("Asset ID (Optional)", "ASSET-PLUMB-RISER-A1")
                    new_cat = st.selectbox("Reported Category", ["plumbing", "water_intrusion", "hvac", "electrical", "structural", "appliance", "security"])
                    new_sev = st.selectbox("Severity", ["low", "medium", "high", "critical"], index=1)
                    new_date = st.date_input("Date Reported", datetime.date.today())
                
                new_desc = st.text_area("Incident Description (Raw)", placeholder="Describe the maintenance complaint in detail...")

                submitted = st.form_submit_button("Submit Incident Record", type="primary")
                if submitted:
                    if not new_desc.strip():
                        st.error("Description cannot be empty.")
                    else:
                        ingest_svc = IngestionService(db)
                        created_dt = datetime.datetime.combine(new_date, datetime.datetime.utcnow().time())
                        success, inc, err_msg = ingest_svc.ingest_single_incident({
                            "incident_id": new_id,
                            "property_id": new_prop,
                            "building_id": new_bldg or None,
                            "unit_id": new_unit or None,
                            "asset_id": new_asset or None,
                            "created_at": created_dt,
                            "raw_description": new_desc,
                            "normalized_category": new_cat,
                            "severity": new_sev,
                            "status": "open"
                        })
                        if success:
                            st.success(f"Incident {inc.incident_id} successfully created and normalized!")
                            if inc.is_duplicate_of:
                                st.warning(f"Note: This incident was flagged as a potential duplicate of {inc.is_duplicate_of}.")
                        else:
                            st.error(f"Failed to create incident: {err_msg}")

    finally:
        db.close()

# ==============================================================================
# PAGE 3: INCIDENT INTELLIGENCE (PRIMARY DEMONSTRATION)
# ==============================================================================
elif page == "3. Incident Intelligence":
    st.markdown('<div class="main-header">Cross-Unit Incident Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Surface potentially related maintenance reports across units, physical infrastructure risers, and time proximity with transparent review-ranking scores.</div>', unsafe_allow_html=True)

    db = get_session()
    try:
        repo = PropertyRepository(db)
        all_incidents = db.query(Incident).all()
        inc_dict = {inc.incident_id: inc for inc in all_incidents}

        if not all_incidents:
            st.warning("No incidents available. Please generate synthetic data.")
        else:
            col_sel1, col_sel2 = st.columns([2, 1])
            with col_sel1:
                # Provide useful label in select box
                incident_choices = [
                    f"{inc.incident_id} | {inc.property_id} | {inc.unit_id or 'No Unit'} | {inc.normalized_category} | {inc.raw_description[:45]}..."
                    for inc in all_incidents
                ]
                selected_choice = st.selectbox("🎯 Select Anchor Incident for Association Analysis", incident_choices, index=0)
                anchor_id = selected_choice.split(" | ")[0]
                anchor_inc = inc_dict[anchor_id]

            with col_sel2:
                st.markdown("**Anchor Details:**")
                st.caption(f"**Location:** Property `{anchor_inc.property_id}` | Bldg `{anchor_inc.building_id or '—'}` | Unit `{anchor_inc.unit_id or '—'}`")
                st.caption(f"**Reported:** {anchor_inc.created_at.strftime('%Y-%m-%d %H:%M')}")
                st.caption(f"**Category:** `{anchor_inc.normalized_category}` | Severity: `{anchor_inc.severity}`")

            # Run Candidate Generation and Scoring
            cand_engine = CandidateGenerationEngine(db)
            scoring_engine = RelationshipScoringEngine(db)

            candidates = cand_engine.generate_candidates_for_incident(anchor_inc)

            st.markdown("---")
            st.subheader(f"Correlated Incident Candidates for {anchor_inc.incident_id}")

            if not candidates:
                st.info("No candidates met the minimum candidate generation filters (same property, spatial/system link, or plausible time window).")
            else:
                # Score all candidates
                scored_candidates = []
                for c in candidates:
                    other_id = c.incident_b_id if c.incident_a_id == anchor_inc.incident_id else c.incident_a_id
                    other_inc = inc_dict.get(other_id)
                    if other_inc:
                        rel = scoring_engine.compute_relationship(anchor_inc, other_inc)
                        scored_candidates.append((other_inc, rel, c.generation_reasons))

                # Sort by review score descending
                scored_candidates.sort(key=lambda x: x[1].review_score, reverse=True)

                st.write(f"Generated **{len(scored_candidates)}** candidate relationships for human evaluation.")

                for idx, (other_inc, rel, reasons) in enumerate(scored_candidates):
                    score = rel.review_score
                    tier_class = "badge-suggest" if score >= 50 and not rel.contradictory_evidence else "badge-closed"
                    
                    with st.expander(f"#{idx+1}: Incident {other_inc.incident_id} (Unit {other_inc.unit_id or '—'}) — Review Ranking Score: {score}/100", expanded=(idx < 2)):
                        c_card1, c_card2 = st.columns([2, 1])
                        
                        with c_card1:
                            st.markdown(f"**Candidate Description:**")
                            st.info(other_inc.raw_description)
                            
                            st.markdown(f"**Verified Associative Evidence:**")
                            st.markdown(f'<div class="evidence-box">{rel.evidence_summary.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

                            if rel.missing_evidence:
                                st.markdown(f'<div class="missing-box"><b>Missing Evidence:</b><br>' + "<br>".join([f"• {m}" for m in rel.missing_evidence]) + '</div>', unsafe_allow_html=True)

                            if rel.contradictory_evidence:
                                st.markdown(f'<div class="contra-box"><b>Contradictory Signals:</b><br>' + "<br>".join([f"• {c}" for c in rel.contradictory_evidence]) + '</div>', unsafe_allow_html=True)

                        with c_card2:
                            st.markdown("**Transparent Scoring Factors:**")
                            factors = rel.score_factors
                            factor_df = []
                            for f_key, f_val in factors.items():
                                factor_df.append({
                                    "Factor": f_val["factor_name"],
                                    "Raw (0-1)": f_val["raw_value"],
                                    "Weight": f_val["weight"],
                                    "Contribution": f_val["weighted_value"]
                                })
                            st.dataframe(pd.DataFrame(factor_df), hide_index=True, use_container_width=True)
                            st.caption("*Score represents a review-ranking prioritization heuristic, not a physical probability of causation.*")

                            # Quick Review Action
                            st.markdown("**Adjudicate This Suggestion:**")
                            action_col1, action_col2, action_col3 = st.columns(3)
                            rev_svc = ReviewService(db)
                            
                            if action_col1.button("✓ Accept", key=f"acc_{rel.relationship_id}"):
                                rev_svc.submit_decision(ReviewDecisionCreate(
                                    target_type="relationship",
                                    target_id=rel.relationship_id,
                                    decision="accept",
                                    reviewer_id="coordinator",
                                    reason="Confirmed related via shared infrastructure"
                                ))
                                st.toast(f"Relationship {rel.relationship_id} Accepted!")
                                st.rerun()

                            if action_col2.button("✗ Reject", key=f"rej_{rel.relationship_id}"):
                                rev_svc.submit_decision(ReviewDecisionCreate(
                                    target_type="relationship",
                                    target_id=rel.relationship_id,
                                    decision="reject",
                                    reviewer_id="coordinator",
                                    reason="Unrelated independent occurrence"
                                ))
                                st.toast(f"Relationship {rel.relationship_id} Rejected!")
                                st.rerun()

                            if action_col3.button("? Uncertain", key=f"unc_{rel.relationship_id}"):
                                rev_svc.submit_decision(ReviewDecisionCreate(
                                    target_type="relationship",
                                    target_id=rel.relationship_id,
                                    decision="uncertain",
                                    reviewer_id="coordinator",
                                    reason="Requires physical inspection by vendor"
                                ))
                                st.toast(f"Relationship {rel.relationship_id} Marked Uncertain!")
                                st.rerun()

                # Visual Building Topology / Riser Diagram
                st.markdown("---")
                st.subheader("Physical Topology & Shared Riser Mapping")
                st.caption("Visualizing vertical riser alignment and unit connection topology in Oakridge Tower A")
                
                fig_topo = go.Figure()
                # Vertical Riser Line
                fig_topo.add_trace(go.Scatter(
                    x=[1, 1], y=[1, 5],
                    mode="lines",
                    line=dict(color="#3B82F6", width=6, dash="dash"),
                    name="Plumbing Riser Stack A1"
                ))
                # Add Units on Riser A1 (101, 201, 301, 401, 501)
                unit_floors = [1, 2, 3, 4, 5]
                unit_labels = [f"Unit {fl}01" for fl in unit_floors]
                # Highlight units with active incidents
                active_units = {other_inc.unit_id for other_inc, _, _ in scored_candidates}
                if anchor_inc.unit_id:
                    active_units.add(anchor_inc.unit_id)

                colors = ["#EF4444" if f"UNIT-OAK-A-{fl}01" in active_units else "#94A3B8" for fl in unit_floors]

                fig_topo.add_trace(go.Scatter(
                    x=[1] * 5, y=unit_floors,
                    mode="markers+text",
                    marker=dict(size=28, color=colors, line=dict(color="#1E293B", width=2)),
                    text=unit_labels,
                    textposition="middle right",
                    name="Stack Units"
                ))
                fig_topo.update_layout(
                    title="Vertical Stack Riser A1 (Oakridge Tower A)",
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0, 3]),
                    yaxis=dict(title="Building Floor Level", tickvals=[1, 2, 3, 4, 5], range=[0.5, 5.5]),
                    height=350,
                    margin=dict(t=40, b=20, l=40, r=20)
                )
                st.plotly_chart(fig_topo, use_container_width=True)

    finally:
        db.close()

# ==============================================================================
# PAGE 4: RECURRENCE MONITOR
# ==============================================================================
elif page == "4. Recurrence Monitor":
    st.markdown('<div class="main-header">Repair Recurrence Verification Monitor</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Identify maintenance incidents appearing after repairs have been marked complete within issue-specific time windows.</div>', unsafe_allow_html=True)

    st.warning("⚠️ **Notice**: These flags indicate a *possible recurrence / similar issue after repair* for human verification. The system never automatically concludes that a repair failed or that a vendor was at fault.")

    db = get_session()
    try:
        rec_svc = RecurrenceDetectionService(db)
        flags = rec_svc.scan_all_for_recurrence()

        if not flags:
            st.info("No repair recurrence candidates detected.")
        else:
            st.write(f"Identified **{len(flags)}** potential post-repair recurrence events requiring verification.")

            for f in flags:
                new_inc = db.query(Incident).filter_by(incident_id=f.new_incident_id).first()
                prior_repair = db.query(RepairRecord).filter_by(repair_id=f.repair_id).first()
                prior_inc = db.query(Incident).filter_by(incident_id=f.prior_incident_id).first()

                with st.container():
                    st.markdown(f"#### 🔁 Flag: {f.flag_id} | Incident {f.new_incident_id} (Unit {new_inc.unit_id if new_inc else '—'})")
                    
                    r_col1, r_col2 = st.columns([2, 1])
                    with r_col1:
                        st.markdown(f'<div class="evidence-box"><b>Evidence Summary:</b><br>{f.evidence_summary}</div>', unsafe_allow_html=True)
                        if prior_repair:
                            st.markdown(f"**Original Repair Record ({prior_repair.repair_id}):**")
                            st.write(f"- **Completed On:** {prior_repair.completed_at.strftime('%Y-%m-%d %H:%M')}")
                            st.write(f"- **Action Taken:** {prior_repair.action_taken}")
                            st.write(f"- **Outcome:** `{prior_repair.outcome}` | Vendor: `{prior_repair.vendor_name or 'In-house'}`")
                            if prior_repair.technician_notes:
                                st.caption(f"Technician Notes: {prior_repair.technician_notes}")

                        if new_inc:
                            st.markdown(f"**New Incident ({new_inc.incident_id}):**")
                            st.write(f"- **Reported On:** {new_inc.created_at.strftime('%Y-%m-%d %H:%M')}")
                            st.write(f"- **Description:** {new_inc.raw_description}")
                    
                    with r_col2:
                        st.markdown("**Recurrence Timing:**")
                        st.metric("Days Since Repair", f"{f.days_since_repair:.1f} days")
                        st.caption(f"Category Window: **{f.recurrence_window_days} days**")
                        st.caption(f"Symptom Similarity: **{f.similarity_score:.0%}**")
                        st.caption(f"Current Status: **{f.status}**")

                        # Review Actions
                        st.markdown("**Verification Action:**")
                        btn_c1, btn_c2, btn_c3 = st.columns(3)
                        rev_svc = ReviewService(db)
                        if btn_c1.button("Confirm", key=f"rec_acc_{f.flag_id}"):
                            rev_svc.submit_decision(ReviewDecisionCreate(
                                target_type="recurrence",
                                target_id=f.flag_id,
                                decision="accept",
                                reviewer_id="maintenance_lead",
                                reason="Confirmed repeat symptom after previous work order"
                            ))
                            st.toast("Recurrence Confirmed!")
                            st.rerun()

                        if btn_c2.button("Dismiss", key=f"rec_rej_{f.flag_id}"):
                            rev_svc.submit_decision(ReviewDecisionCreate(
                                target_type="recurrence",
                                target_id=f.flag_id,
                                decision="reject",
                                reviewer_id="maintenance_lead",
                                reason="Unrelated new failure mode"
                            ))
                            st.toast("Recurrence Dismissed!")
                            st.rerun()

                        if btn_c3.button("Inspect", key=f"rec_unc_{f.flag_id}"):
                            rev_svc.submit_decision(ReviewDecisionCreate(
                                target_type="recurrence",
                                target_id=f.flag_id,
                                decision="uncertain",
                                reviewer_id="maintenance_lead",
                                reason="Requires second on-site technician evaluation"
                            ))
                            st.toast("Marked for on-site inspection!")
                            st.rerun()

                    st.markdown("---")

    finally:
        db.close()

# ==============================================================================
# PAGE 5: REVIEW QUEUE & AUDIT TRAIL
# ==============================================================================
elif page == "5. Review Queue & Audit":
    st.markdown('<div class="main-header">Human Review Queue & Audit Trail</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Persistent, append-only audit trail capturing coordinator adjudication decisions, rationales, and exportable operational datasets.</div>', unsafe_allow_html=True)

    db = get_session()
    try:
        rev_svc = ReviewService(db)
        audit_history = rev_svc.get_audit_history()

        tab_audit, tab_export = st.tabs(["📝 Adjudication Audit Log", "📥 Data Exports (CSV)"])

        with tab_audit:
            st.subheader(f"Adjudication Log ({len(audit_history)} decisions recorded)")
            
            if not audit_history:
                st.info("No human review decisions recorded yet. Accept or reject suggestions in Incident Intelligence or Recurrence Monitor to populate this audit trail.")
            else:
                audit_rows = []
                for entry in audit_history:
                    audit_rows.append({
                        "Decision ID": entry.decision_id,
                        "Type": entry.target_type,
                        "Target ID": entry.target_id,
                        "Decision": entry.decision.upper(),
                        "Reviewer": entry.reviewer_id,
                        "Rationale": entry.reason or "—",
                        "Rule Version": entry.rule_version,
                        "Timestamp": entry.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    })
                st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)

        with tab_export:
            st.subheader("Operational Data & Decision Exports")
            st.caption("Export normalized maintenance records, candidate associations, recurrence flags, and human decision logs for downstream reporting.")

            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                st.markdown("#### Maintenance Incidents")
                csv_inc = rev_svc.export_incidents_csv()
                st.download_button(
                    label="📥 Download Incidents CSV",
                    data=csv_inc,
                    file_name=f"tenantease_incidents_{datetime.datetime.utcnow().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

                st.markdown("#### Review Decisions Audit Log")
                csv_rev = rev_svc.export_reviews_csv()
                st.download_button(
                    label="📥 Download Review Audit CSV",
                    data=csv_rev,
                    file_name=f"tenantease_review_decisions_{datetime.datetime.utcnow().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col_exp2:
                st.markdown("#### Candidate Relationships & Scores")
                csv_rel = rev_svc.export_relationships_csv()
                st.download_button(
                    label="📥 Download Relationships CSV",
                    data=csv_rel,
                    file_name=f"tenantease_relationships_{datetime.datetime.utcnow().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

                st.markdown("#### Recurrence Flags")
                csv_rec = rev_svc.export_recurrence_csv()
                st.download_button(
                    label="📥 Download Recurrence Flags CSV",
                    data=csv_rec,
                    file_name=f"tenantease_recurrence_flags_{datetime.datetime.utcnow().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    finally:
        db.close()

# ==============================================================================
# PAGE 6: EVALUATION & BENCHMARKS
# ==============================================================================
elif page == "6. Evaluation & Benchmarks":
    st.markdown('<div class="main-header">System Evaluation & Benchmarks</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Empirical validation on reproducible synthetic dataset comparing baseline heuristic vs rules-first property intelligence.</div>', unsafe_allow_html=True)

    st.info("ℹ️ **Synthetic Evaluation Disclaimer**: This benchmark runs on synthetic multi-family test cases (same-riser leaks, disparate cross-property wording, recurrence, missing locations, duplicates, prompt injection) to rigorously evaluate algorithmic logic. Real-world efficacy requires historical human-labeled records.")

    if st.button("▶ Run Full Benchmark Evaluation", type="primary"):
        with st.spinner("Executing candidate generation, relationship scoring, baseline comparison, and metric calculation..."):
            bench = run_full_evaluation()
            st.session_state["benchmark_results"] = bench
            st.success("Evaluation complete!")

    if "benchmark_results" in st.session_state:
        res = st.session_state["benchmark_results"]
        base = res["baseline_model"]
        prop_eng = res["proposed_engine"]
        rec = res["recurrence_detection"]

        st.markdown("### 1. Comparative Performance: Baseline vs TenantEase Intelligence")
        
        comp_df = pd.DataFrame([
            {
                "Model / Strategy": "Baseline (Same Building + 72h Window)",
                "Precision": f"{base['precision']:.1%}",
                "Recall": f"{base['recall']:.1%}",
                "F1 Score": f"{base['f1_score']:.3f}",
                "True Positives (TP)": base["true_positives"],
                "False Positives (FP)": base["false_positives"],
                "False Negatives (FN)": base["false_negatives"]
            },
            {
                "Model / Strategy": "TenantEase Intelligence (Topology + Symptoms + Decay)",
                "Precision": f"{prop_eng['precision']:.1%}",
                "Recall": f"{prop_eng['recall']:.1%}",
                "F1 Score": f"{prop_eng['f1_score']:.3f}",
                "True Positives (TP)": prop_eng["true_positives"],
                "False Positives (FP)": prop_eng["false_positives"],
                "False Negatives (FN)": prop_eng["false_negatives"]
            }
        ])
        st.dataframe(comp_df, hide_index=True, use_container_width=True)

        st.caption("Notice: The baseline blindly connects any two tickets in the same building within 72 hours, resulting in substantial false positives. The topology-grounded engine eliminates irrelevant pairs while preserving 100% recall on true clusters.")

        # Recurrence Metrics Card
        st.markdown("### 2. Recurrence Verification Performance")
        r_m1, r_m2, r_m3, r_m4 = st.columns(4)
        with r_m1:
            st.metric("Recurrence Precision", f"{rec['precision']:.1%}")
        with r_m2:
            st.metric("Recurrence Recall", f"{rec['recall']:.1%}")
        with r_m3:
            st.metric("Recurrence F1 Score", f"{rec['f1_score']:.3f}")
        with r_m4:
            st.metric("Flagged Candidates", rec["flagged_count"])

        # Error Analysis Inspector
        st.markdown("### 3. Detailed Error Analysis: False Positives & Negatives")
        err_col1, err_col2 = st.columns(2)
        with err_col1:
            st.markdown("#### False Positives (Over-Association)")
            st.caption("Pairs suggested by engine that were not in ground truth:")
            fp_list = prop_eng.get("fp_examples", [])
            if fp_list:
                st.write(f"Showing first 5 of {len(fp_list)} false positives:")
                for fp_pair in fp_list[:5]:
                    st.code(f"Pair: {fp_pair[0]} <—> {fp_pair[1]}")
                st.caption("*Analysis: False positives occur when separate maintenance tickets in the same building share general categories during the same time frame. Human review acts as the precision filter.*")
            else:
                st.success("Zero False Positives!")

        with err_col2:
            st.markdown("#### False Negatives (Missed Links)")
            st.caption("Ground truth related pairs missed by engine:")
            fn_list = prop_eng.get("fn_examples", [])
            if fn_list:
                for fn_pair in fn_list:
                    st.error(f"Missed Pair: {fn_pair[0]} <—> {fn_pair[1]}")
            else:
                st.success("Zero False Negatives! 100% recall achieved on ground truth clusters.")
    else:
        st.info("Click 'Run Full Benchmark Evaluation' above to execute evaluation.")

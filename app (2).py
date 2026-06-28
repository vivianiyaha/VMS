"""
Smart Visitor Entry & Exit Management System
============================================
Run with: streamlit run app.py

Architecture:
    app.py              — entry point, routing, sidebar nav
    modules/database.py — SQLite CRUD and schema
    modules/qr_utils.py — QR generation, badge, PDF pass
    modules/reports.py  — Excel / CSV / PDF reports
"""

import os, sys, uuid, base64, io, re
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from PIL import Image
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pytz
from datetime import datetime, timedelta

# ── Bootstrap ────────────────────────────────────────────────────────────────
from modules.database import init_db, lagos_now
init_db()                                   # create DB + dirs on first run

from modules import database as db
from modules import qr_utils as qru
from modules import reports

LAGOS_TZ = pytz.timezone("Africa/Lagos")

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Smart VMS",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] {
    background: #f1f5f9;
}
[data-testid="stSidebar"] {
    background: #1a2744 !important;
    color: white;
}
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] hr { border-color: #334155 !important; }

/* ── Metric cards ── */
.metric-card {
    background: white;
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
    box-shadow: 0 1px 6px rgba(0,0,0,.07);
    border-top: 4px solid #22c55e;
    transition: transform .15s;
}
.metric-card:hover { transform: translateY(-2px); }
.metric-card h2 { margin: 0; font-size: 2rem; color: #1a2744; }
.metric-card p  { margin: 4px 0 0; font-size: .8rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }
.metric-card.orange  { border-top-color: #f59e0b; }
.metric-card.red     { border-top-color: #ef4444; }
.metric-card.blue    { border-top-color: #3b82f6; }
.metric-card.purple  { border-top-color: #a855f7; }
.metric-card.gray    { border-top-color: #6b7280; }

/* ── Status badges ── */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: .75rem;
    font-weight: 600;
    letter-spacing: .04em;
}
.badge-green  { background:#dcfce7; color:#15803d; }
.badge-yellow { background:#fef9c3; color:#854d0e; }
.badge-red    { background:#fee2e2; color:#b91c1c; }
.badge-blue   { background:#dbeafe; color:#1d4ed8; }

/* ── Section titles ── */
.section-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #1a2744;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid #e2e8f0;
}

/* ── Visitor card ── */
.visitor-card {
    background: white;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
    border-left: 4px solid #e2e8f0;
}
.visitor-card.approved  { border-left-color: #22c55e; }
.visitor-card.pending   { border-left-color: #f59e0b; }
.visitor-card.rejected  { border-left-color: #ef4444; }
.visitor-card.checked   { border-left-color: #3b82f6; }

/* ── Form panels ── */
.form-panel {
    background: white;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 6px rgba(0,0,0,.06);
    margin-bottom: 20px;
}

/* ── Buttons ── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
}

/* ── Sidebar nav ── */
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 8px;
    cursor: pointer;
    transition: background .15s;
    margin: 2px 0;
    color: #cbd5e1;
    font-size: .9rem;
}
.nav-item:hover, .nav-item.active {
    background: rgba(255,255,255,.1);
    color: white;
}
</style>
""", unsafe_allow_html=True)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SESSION STATE HELPERS                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def ss():
    """Return st.session_state as a convenience alias."""
    return st.session_state


def init_session():
    defaults = {
        "logged_in": False,
        "admin": None,
        "page": "dashboard",
        "dark_mode": False,
        "scan_result": "",
        "visitor_form": {},
        "form_submitted": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  HELPERS                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def status_badge(status: str) -> str:
    cls = {"Approved": "green", "Pending": "yellow",
           "Rejected": "red", "Checked Out": "blue"}.get(status, "yellow")
    return f'<span class="badge badge-{cls}">{status}</span>'


def metric_card(label: str, value, color="green", icon=""):
    return f"""
    <div class="metric-card {color}">
        <h2>{icon} {value}</h2>
        <p>{label}</p>
    </div>"""


def save_photo(photo_bytes: bytes, visitor_number: str) -> str:
    """Save webcam photo bytes, return file path."""
    path = f"data/photos/{visitor_number}.jpg"
    with open(path, "wb") as f:
        f.write(photo_bytes)
    return path


def generate_barcode_id() -> str:
    return "VMS-" + str(uuid.uuid4()).replace("-", "")[:12].upper()


def validate_phone(phone: str) -> bool:
    return bool(re.match(r"^[0-9+\-\s]{7,15}$", phone.strip()))


def nav_button(label, page, icon=""):
    active = "active" if st.session_state.page == page else ""
    if st.sidebar.button(f"{icon}  {label}", key=f"nav_{page}",
                          use_container_width=True):
        st.session_state.page = page
        st.rerun()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SIDEBAR                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def render_sidebar():
    with st.sidebar:
        # Logo / brand
        st.markdown("""
        <div style="text-align:center;padding:20px 0 10px">
            <div style="font-size:2.5rem">🏢</div>
            <div style="font-size:1rem;font-weight:700;color:white;margin-top:4px">Smart VMS</div>
            <div style="font-size:.7rem;color:#94a3b8">Visitor Management System</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")

        if not st.session_state.logged_in:
            # Public pages
            nav_button("Visitor Registration", "register", "📝")
            nav_button("Visitor Check-Out", "checkout", "🚪")
            nav_button("Track My Visit", "track", "🔍")
            st.markdown("---")
            nav_button("Admin Login", "login", "🔐")
        else:
            admin = st.session_state.admin
            st.markdown(f"""
            <div style="background:rgba(255,255,255,.08);border-radius:8px;padding:10px;margin-bottom:10px">
                <div style="font-size:.75rem;color:#94a3b8">Signed in as</div>
                <div style="font-weight:700;color:white">{admin['full_name']}</div>
                <div style="font-size:.7rem;color:#22c55e">{admin['role']}</div>
            </div>
            """, unsafe_allow_html=True)

            nav_button("Dashboard", "dashboard", "📊")
            nav_button("Visitor Registration", "register", "📝")
            nav_button("Approval Center", "approvals", "✅")
            nav_button("Visitor Tracking", "tracking", "📍")
            nav_button("Visitor Check-Out", "checkout", "🚪")
            nav_button("Reports", "reports", "📄")
            nav_button("Settings", "settings", "⚙️")
            st.markdown("---")
            if st.sidebar.button("🚪  Logout", use_container_width=True, type="secondary"):
                db.log_audit(admin["username"], "LOGOUT", "Admin logged out")
                st.session_state.logged_in = False
                st.session_state.admin = None
                st.session_state.page = "register"
                st.rerun()

        st.markdown("---")
        # Dark mode toggle (cosmetic)
        dm = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
        st.session_state.dark_mode = dm

        st.markdown("""
        <div style="text-align:center;font-size:.65rem;color:#475569;margin-top:16px">
            Smart VMS v1.0<br>© 2025 Cardstel Solutions
        </div>
        """, unsafe_allow_html=True)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: ADMIN LOGIN                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-bottom:24px">
            <div style="font-size:3rem">🔐</div>
            <h2 style="color:#1a2744;margin:8px 0 4px">Admin Login</h2>
            <p style="color:#64748b;font-size:.9rem">Smart Visitor Management System</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            if not username or not password:
                st.error("Please enter both username and password.")
            else:
                admin = db.verify_admin(username, password)
                if admin:
                    db.update_last_login(username)
                    db.log_audit(username, "LOGIN", f"Role: {admin['role']}")
                    st.session_state.logged_in = True
                    st.session_state.admin = admin
                    if admin["must_change_pw"]:
                        st.session_state.page = "change_password"
                    else:
                        st.session_state.page = "dashboard"
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please try again.")
                    db.log_audit(username, "FAILED_LOGIN", "Invalid credentials")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: CHANGE PASSWORD                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_change_password():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-bottom:24px">
            <div style="font-size:3rem">🔑</div>
            <h2 style="color:#1a2744">Set New Password</h2>
            <p style="color:#64748b">You must change your password before continuing.</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("change_pw_form"):
            new_pw  = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            sub     = st.form_submit_button("Update Password", type="primary",
                                             use_container_width=True)
        if sub:
            if len(new_pw) < 8:
                st.error("Password must be at least 8 characters.")
            elif new_pw != confirm:
                st.error("Passwords do not match.")
            else:
                admin = st.session_state.admin
                db.update_admin_password(admin["username"], new_pw)
                db.log_audit(admin["username"], "PASSWORD_CHANGED", "Initial password changed")
                # Refresh admin session
                updated = db.verify_admin(admin["username"], new_pw)
                st.session_state.admin = updated
                st.success("Password updated successfully!")
                st.session_state.page = "dashboard"
                st.rerun()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: VISITOR REGISTRATION                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_register():
    st.markdown('<p class="section-title">📝 Visitor Registration</p>', unsafe_allow_html=True)

    # Show success message if just submitted
    if st.session_state.get("form_submitted"):
        vn  = st.session_state.get("last_visitor_number", "")
        bid = st.session_state.get("last_barcode_id", "")
        st.success(f"✅ Visit request submitted! Your Visitor Number is **{vn}**")
        st.info("Your visit request has been submitted and is awaiting approval.")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Your QR Code (for entry/exit)**")
            qr_bytes = qru.generate_qr_code(bid)
            st.image(qr_bytes, width=200, caption=bid)
            st.download_button("⬇️ Download QR Code", qr_bytes, f"{vn}_qr.png", "image/png")
        with col2:
            st.markdown("**Visitor Badge Preview**")
            visitor = db.get_visitor_by_number(vn)
            if visitor:
                badge = qru.generate_visitor_badge(visitor)
                st.image(badge, width=250)
                st.download_button("⬇️ Download Badge (PNG)", badge, f"{vn}_badge.png", "image/png")

        if st.button("➕ Register Another Visitor", type="primary"):
            st.session_state.form_submitted = False
            st.rerun()
        return

    # ── QR / Barcode Scanner ────────────────────────────────────────────────
    with st.expander("📷 Scan Existing QR Code (for returning visitors)", expanded=False):
        st.caption("Upload a QR code image to auto-fill Visitor Number")
        uploaded_qr = st.file_uploader("Upload QR Code Image", type=["png", "jpg", "jpeg"],
                                        key="qr_upload")
        if uploaded_qr:
            decoded = qru.decode_qr_from_image(uploaded_qr.read())
            if decoded:
                st.success(f"QR Decoded: **{decoded}**")
                st.session_state.scan_result = decoded
            else:
                st.warning("Could not decode QR code. Please fill the form manually.")

    # ── Auto-generated values ───────────────────────────────────────────────
    visitor_number = db.get_next_visitor_number()
    barcode_id     = generate_barcode_id()
    now            = lagos_now()

    st.markdown(f"""
    <div class="form-panel" style="border-left:4px solid #22c55e">
        <div style="display:flex;gap:40px;flex-wrap:wrap">
            <div><span style="color:#64748b;font-size:.8rem">VISITOR NUMBER</span><br>
                 <strong style="font-size:1.1rem;color:#1a2744">{visitor_number}</strong></div>
            <div><span style="color:#64748b;font-size:.8rem">ENTRY DATE</span><br>
                 <strong>{now.strftime('%d %b %Y')}</strong></div>
            <div><span style="color:#64748b;font-size:.8rem">ENTRY TIME</span><br>
                 <strong>{now.strftime('%H:%M:%S')}</strong></div>
            <div><span style="color:#64748b;font-size:.8rem">BARCODE ID</span><br>
                 <strong style="font-family:monospace;font-size:.85rem">{barcode_id}</strong></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    departments = db.get_departments()
    hosts       = [h["name"] for h in db.get_hosts()]

    with st.form("visitor_registration_form", clear_on_submit=False):
        # ── Personal Information ─────────────────────────────────────────
        st.markdown("### 👤 Personal Information")
        c1, c2 = st.columns(2)
        with c1:
            full_name = st.text_input("Full Name *", placeholder="e.g. Chidinma Okafor")
            phone     = st.text_input("Phone Number *", placeholder="e.g. 08012345678")
            gender    = st.selectbox("Gender", ["", "Male", "Female", "Prefer not to say"])
        with c2:
            email    = st.text_input("Email Address", placeholder="visitor@example.com")
            company  = st.text_input("Company / Organization", placeholder="Company name")
            address  = st.text_input("Address", placeholder="Street, City, State")

        st.divider()
        # ── Visit Information ────────────────────────────────────────────
        st.markdown("### 📋 Visit Information")
        c1, c2 = st.columns(2)
        with c1:
            dept = st.selectbox("Department *", [""] + departments)
            person_to_visit = st.text_input("Person to Visit *", placeholder="e.g. Mrs. Adaeze Okonkwo")
        with c2:
            purpose = st.text_area("Purpose of Visit *", placeholder="Describe reason for visit", height=80)
            vehicle_reg = st.text_input("Vehicle Reg. Number (optional)", placeholder="e.g. ABC-123-DE")

        st.divider()
        # ── Identity Information ─────────────────────────────────────────
        st.markdown("### 🪪 Identity Information")
        c1, c2 = st.columns(2)
        with c1:
            id_type = st.selectbox("ID Type *",
                ["", "National ID", "Driver's License", "Voter Card", "International Passport"])
        with c2:
            id_number = st.text_input("ID Number *", placeholder="Enter ID number")

        st.divider()
        # ── Security Information ─────────────────────────────────────────
        st.markdown("### 🔒 Security Information")
        items_carried = st.text_area("Items Carried", placeholder="List items brought in (laptop, bag, tools, etc.)", height=60)

        # ── Visitor Photo ────────────────────────────────────────────────
        st.markdown("**Visitor Photograph**")
        photo_col1, photo_col2 = st.columns([1, 2])
        with photo_col1:
            photo_file = st.file_uploader("Upload Photo", type=["jpg", "jpeg", "png"], key="photo_upload")
        with photo_col2:
            if photo_file:
                st.image(photo_file, width=120, caption="Preview")

        st.divider()
        # ── Emergency Contact ────────────────────────────────────────────
        st.markdown("### 🆘 Emergency Contact")
        c1, c2 = st.columns(2)
        with c1:
            emergency_name  = st.text_input("Emergency Contact Name")
        with c2:
            emergency_phone = st.text_input("Emergency Contact Phone")

        st.divider()
        col_sub, col_clr = st.columns([3, 1])
        with col_sub:
            submitted = st.form_submit_button("📤 Submit Request", type="primary",
                                               use_container_width=True)
        with col_clr:
            cleared = st.form_submit_button("🗑️ Clear Form", use_container_width=True)

        if cleared:
            st.rerun()

        if submitted:
            # Validation
            errors = []
            if not full_name.strip():         errors.append("Full Name is required.")
            if not phone.strip():             errors.append("Phone Number is required.")
            if not dept:                      errors.append("Department is required.")
            if not person_to_visit:           errors.append("Person to Visit is required.")
            if not purpose.strip():           errors.append("Purpose of Visit is required.")
            if not id_type:                   errors.append("ID Type is required.")
            if not id_number.strip():         errors.append("ID Number is required.")
            if phone and not validate_phone(phone): errors.append("Invalid phone number format.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                # Save photo
                photo_path = ""
                if photo_file:
                    photo_bytes = photo_file.read()
                    photo_path  = save_photo(photo_bytes, visitor_number)

                visitor_data = {
                    "visitor_number": visitor_number,
                    "barcode_id":     barcode_id,
                    "full_name":      full_name.strip(),
                    "phone":          phone.strip(),
                    "email":          email.strip(),
                    "gender":         gender,
                    "company":        company.strip(),
                    "address":        address.strip(),
                    "person_to_visit": person_to_visit,
                    "department":     dept,
                    "purpose":        purpose.strip(),
                    "expected_duration": "",
                    "vehicle_reg":    vehicle_reg.strip(),
                    "id_type":        id_type,
                    "id_number":      id_number.strip(),
                    "photo_path":     photo_path,
                    "items_carried":  items_carried.strip(),
                    "emergency_name": emergency_name.strip(),
                    "emergency_phone": emergency_phone.strip(),
                }
                db.create_visitor(visitor_data)
                db.log_audit(
                    st.session_state.admin["username"] if st.session_state.logged_in else "guest",
                    "VISITOR_REGISTERED",
                    f"Visitor {visitor_number} - {full_name}"
                )
                st.session_state.form_submitted        = True
                st.session_state.last_visitor_number   = visitor_number
                st.session_state.last_barcode_id       = barcode_id
                st.rerun()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: ADMIN DASHBOARD                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_dashboard():
    if not st.session_state.logged_in:
        st.warning("Please log in to access the dashboard.")
        st.session_state.page = "login"
        st.rerun()

    st.markdown('<p class="section-title">📊 Dashboard Overview</p>', unsafe_allow_html=True)

    stats    = db.get_dashboard_stats()
    today_str = lagos_now().strftime("%A, %d %B %Y")
    st.caption(f"📅 Today: {today_str} (WAT)")

    # ── Summary cards ───────────────────────────────────────────────────────
    cols = st.columns(6)
    cards = [
        ("Total Today",    stats["total_today"],  "green",  "👥"),
        ("Inside Building",stats["inside"],        "blue",   "🏢"),
        ("Approved",       stats["approved"],      "green",  "✅"),
        ("Pending",        stats["pending"],        "orange", "⏳"),
        ("Rejected",       stats["rejected"],       "red",    "❌"),
        ("Checked Out",    stats["checked_out"],    "gray",   "🚪"),
    ]
    for col, (label, val, color, icon) in zip(cols, cards):
        with col:
            st.markdown(metric_card(label, val, color, icon), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row ─────────────────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        daily = db.get_daily_visits(30)
        if daily:
            df_daily = pd.DataFrame(daily).sort_values("entry_date")
            fig = px.area(df_daily, x="entry_date", y="count",
                          title="📈 Daily Visits (Last 30 Days)",
                          labels={"entry_date": "Date", "count": "Visitors"},
                          color_discrete_sequence=["#22c55e"])
            fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                              title_font_size=14, margin=dict(t=40, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No visit data yet to chart.")

    with chart_col2:
        dept_data = db.get_department_visits()
        if dept_data:
            df_dept = pd.DataFrame(dept_data)
            fig = px.bar(df_dept, x="count", y="department", orientation="h",
                         title="🏛️ Visits by Department",
                         labels={"count": "Visitors", "department": ""},
                         color="count",
                         color_continuous_scale=["#dbeafe", "#1a2744"])
            fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                              title_font_size=14, margin=dict(t=40, b=20, l=20, r=20),
                              showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No department data yet.")

    # ── Hourly distribution ─────────────────────────────────────────────────
    hourly = db.get_hourly_visits()
    if hourly:
        df_hour = pd.DataFrame(hourly)
        df_hour["hour_label"] = df_hour["hour"].apply(
            lambda h: f"{int(h):02d}:00" if h.strip() else "Unknown")
        fig_h = px.bar(df_hour, x="hour_label", y="count",
                       title="🕐 Peak Visit Hours (Today)",
                       labels={"hour_label": "Hour", "count": "Visitors"},
                       color_discrete_sequence=["#3b82f6"])
        fig_h.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                             title_font_size=14, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig_h, use_container_width=True)

    # ── Recent visitors table ───────────────────────────────────────────────
    st.markdown('<p class="section-title">Recent Visitors</p>', unsafe_allow_html=True)
    recent = db.get_visitors()[:10]
    if recent:
        df_r = pd.DataFrame(recent)[["visitor_number", "full_name", "department",
                                      "person_to_visit", "status", "entry_date", "entry_time"]]
        df_r.columns = ["Visitor #", "Name", "Department", "Host", "Status", "Date", "Time"]
        st.dataframe(df_r, use_container_width=True, hide_index=True)
    else:
        st.info("No visitors registered yet.")

    if st.button("🔄 Refresh Dashboard"):
        st.rerun()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: APPROVAL CENTER                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_approvals():
    if not st.session_state.logged_in:
        st.warning("Admin access required.")
        return

    admin = st.session_state.admin
    st.markdown('<p class="section-title">✅ Approval Center</p>', unsafe_allow_html=True)

    tab_pending, tab_all = st.tabs(["⏳ Pending Approvals", "📋 All Visitors"])

    with tab_pending:
        pending = db.get_visitors(status="Pending")
        if not pending:
            st.success("✅ No pending approvals at this time.")
        else:
            st.info(f"**{len(pending)}** visitor(s) awaiting approval.")
            for v in pending:
                with st.container():
                    card_cls = "pending"
                    st.markdown(f"""
                    <div class="visitor-card {card_cls}">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start">
                            <div>
                                <strong style="font-size:1rem;color:#1a2744">{v['full_name']}</strong>
                                <span style="margin-left:10px">{status_badge(v['status'])}</span><br>
                                <span style="color:#64748b;font-size:.85rem">
                                    {v['visitor_number']} &bull; {v['phone']} &bull; {v['company'] or 'N/A'}
                                </span>
                            </div>
                            <div style="text-align:right;font-size:.8rem;color:#64748b">
                                {v['entry_date']} {v['entry_time']}
                            </div>
                        </div>
                        <div style="margin-top:8px;font-size:.85rem;color:#475569">
                            🏛️ <strong>{v['department']}</strong> &rarr; {v['person_to_visit']} &bull;
                            📋 {v['purpose']} &bull;
                            🪪 {v['id_type']}: {v['id_number']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    with st.expander(f"Actions for {v['visitor_number']} — {v['full_name']}"):
                        action_col, form_col = st.columns([1, 2])
                        with action_col:
                            # Show photo
                            if v.get("photo_path") and os.path.exists(v["photo_path"]):
                                st.image(v["photo_path"], width=120, caption="Visitor Photo")
                            else:
                                st.markdown("🖼️ No photo")
                            # QR preview
                            qr_bytes = qru.generate_qr_code(v["barcode_id"])
                            st.image(qr_bytes, width=100, caption="Visitor QR")

                        with form_col:
                            with st.form(f"approve_form_{v['id']}"):
                                comments = st.text_area("Comments / Notes", height=80,
                                                        placeholder="Add approval notes or reason for rejection...")
                                a_col, r_col, i_col = st.columns(3)
                                with a_col:
                                    approve = st.form_submit_button("✅ Approve", type="primary",
                                                                    use_container_width=True)
                                with r_col:
                                    reject  = st.form_submit_button("❌ Reject",
                                                                    use_container_width=True)
                                with i_col:
                                    more_info = st.form_submit_button("ℹ️ More Info",
                                                                       use_container_width=True)

                                if approve or reject or more_info:
                                    action = "Approved" if approve else ("Rejected" if reject else "More Info Requested")
                                    db.update_visitor_status(v["id"], action)
                                    db.create_approval({
                                        "visitor_id":    v["id"],
                                        "visitor_number": v["visitor_number"],
                                        "approver_name": admin["full_name"],
                                        "approver_role": admin["role"],
                                        "action":        action,
                                        "comments":      comments,
                                    })
                                    db.log_audit(admin["username"], action,
                                                 f"Visitor {v['visitor_number']} — {v['full_name']}")
                                    st.success(f"Visitor {action.lower()} successfully.")
                                    st.rerun()

    with tab_all:
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Filter by Status",
                ["All", "Pending", "Approved", "Rejected", "Checked Out"])
        with col2:
            dept_filter = st.selectbox("Filter by Department", ["All"] + db.get_departments())
        with col3:
            search = st.text_input("🔍 Search", placeholder="Name, number, or phone")

        visitors = db.get_visitors(
            status=None if status_filter == "All" else status_filter,
            department=None if dept_filter == "All" else dept_filter,
            search=search or None
        )

        if visitors:
            df = pd.DataFrame(visitors)[[
                "visitor_number", "full_name", "phone", "department",
                "person_to_visit", "status", "entry_date", "entry_time",
                "exit_time", "visit_duration"
            ]]
            df.columns = ["#", "Name", "Phone", "Dept", "Host",
                          "Status", "Date", "Entry", "Exit", "Duration"]
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(visitors)} records")
        else:
            st.info("No records match the filter.")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: VISITOR TRACKING                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_tracking():
    if not st.session_state.logged_in:
        st.warning("Admin access required.")
        return

    st.markdown('<p class="section-title">📍 Visitor Tracking</p>', unsafe_allow_html=True)

    search = st.text_input("🔍 Search visitor by name, number, phone, or barcode",
                            placeholder="Type to search...")
    visitors = db.get_visitors(search=search or None)

    # Color-coded status grid
    today = lagos_now().strftime("%Y-%m-%d")
    today_visitors = [v for v in visitors if v["entry_date"] == today]

    if today_visitors:
        st.markdown(f"**Today's visitors: {len(today_visitors)}**")
        for v in today_visitors:
            cls_map = {
                "Approved": "approved", "Pending": "pending",
                "Rejected": "rejected", "Checked Out": "checked"
            }
            cls = cls_map.get(v["status"], "pending")
            icon = {"Approved": "🟢", "Pending": "🟡",
                    "Rejected": "🔴", "Checked Out": "🔵"}.get(v["status"], "⚪")

            st.markdown(f"""
            <div class="visitor-card {cls}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div>
                        {icon} <strong>{v['full_name']}</strong>
                        &nbsp;{status_badge(v['status'])}&nbsp;
                        <span style="color:#64748b;font-size:.85rem">
                            {v['visitor_number']} &bull; {v['department']} &bull; ➡️ {v['person_to_visit']}
                        </span>
                    </div>
                    <div style="font-size:.8rem;color:#64748b">
                        In: {v['entry_time']} &nbsp;|&nbsp;
                        Out: {v['exit_time'] or '—'} &nbsp;|&nbsp;
                        Duration: {v['visit_duration'] or '—'}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No visitors found for today." if not search else "No visitors match your search.")

    if not today_visitors and visitors:
        st.markdown("**All Historical Visitors**")
        df = pd.DataFrame(visitors)[[
            "visitor_number", "full_name", "department", "status",
            "entry_date", "entry_time", "exit_time", "visit_duration"
        ]]
        st.dataframe(df, use_container_width=True, hide_index=True)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: VISITOR TRACK (PUBLIC)                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_track_public():
    st.markdown('<p class="section-title">🔍 Track My Visit</p>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        vn = st.text_input("Enter your Visitor Number", placeholder="e.g. VIS-00001")
        if st.button("🔍 Track", type="primary", use_container_width=True):
            if vn.strip():
                visitor = db.get_visitor_by_number(vn.strip())
                if visitor:
                    status = visitor["status"]
                    icon_map = {"Approved": "🟢", "Pending": "🟡",
                                "Rejected": "🔴", "Checked Out": "🔵"}
                    st.markdown(f"""
                    <div class="form-panel">
                        <h3 style="color:#1a2744;margin:0 0 16px">
                            {icon_map.get(status,'⚪')} {visitor['full_name']}
                        </h3>
                        {status_badge(status)}
                        <br><br>
                        <table style="width:100%;font-size:.9rem">
                            <tr><td style="color:#64748b;padding:4px 0">Visitor Number</td>
                                <td><strong>{visitor['visitor_number']}</strong></td></tr>
                            <tr><td style="color:#64748b;padding:4px 0">Department</td>
                                <td>{visitor['department']}</td></tr>
                            <tr><td style="color:#64748b;padding:4px 0">Host</td>
                                <td>{visitor['person_to_visit']}</td></tr>
                            <tr><td style="color:#64748b;padding:4px 0">Entry</td>
                                <td>{visitor['entry_date']} at {visitor['entry_time']}</td></tr>
                            <tr><td style="color:#64748b;padding:4px 0">Exit</td>
                                <td>{visitor['exit_date'] or '—'} at {visitor['exit_time'] or '—'}</td></tr>
                            <tr><td style="color:#64748b;padding:4px 0">Duration</td>
                                <td>{visitor['visit_duration'] or '—'}</td></tr>
                        </table>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("Visitor not found. Please check the number and try again.")
            else:
                st.warning("Please enter a visitor number.")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: CHECK-OUT                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_checkout():
    st.markdown('<p class="section-title">🚪 Visitor Check-Out</p>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("""
        <div class="form-panel">
            <p style="color:#64748b;margin:0 0 16px">
                Scan the QR code from your visitor pass or enter your Visitor Number to check out.
            </p>
        """, unsafe_allow_html=True)

        # QR Upload for checkout
        uploaded_qr = st.file_uploader("📷 Upload QR Code Image", type=["png", "jpg", "jpeg"],
                                        key="checkout_qr")
        barcode_val = ""
        if uploaded_qr:
            decoded = qru.decode_qr_from_image(uploaded_qr.read())
            if decoded:
                barcode_val = decoded
                st.success(f"QR Decoded: **{decoded}**")
            else:
                st.warning("Could not decode QR. Please enter manually.")

        st.markdown("**— or —**")
        manual_input = st.text_input("Enter Visitor Number or Barcode ID",
                                      value=barcode_val,
                                      placeholder="VIS-00001 or VMS-XXXXXXXXXX")

        checkout_btn = st.button("🚪 Process Check-Out", type="primary", use_container_width=True)

        if checkout_btn and manual_input.strip():
            identifier = manual_input.strip()
            # Try barcode first, then visitor number
            visitor = db.get_visitor_by_barcode(identifier)
            if not visitor:
                visitor = db.get_visitor_by_number(identifier)

            if not visitor:
                st.error("❌ Visitor not found. Please check the ID and try again.")
            elif visitor["status"] == "Checked Out":
                st.warning("⚠️ This visitor has already checked out.")
                st.info(f"Exit recorded at: {visitor['exit_date']} {visitor['exit_time']} | Duration: {visitor['visit_duration']}")
            elif visitor["status"] == "Pending":
                st.error("❌ This visitor has not been approved yet. Cannot check out.")
            elif visitor["status"] == "Rejected":
                st.error("❌ This visitor's request was rejected.")
            else:
                duration = db.record_exit(visitor["id"])
                db.log_audit(
                    st.session_state.admin["username"] if st.session_state.logged_in else "security",
                    "VISITOR_CHECKOUT",
                    f"{visitor['visitor_number']} — {visitor['full_name']} | Duration: {duration}"
                )
                now = lagos_now()
                st.success("✅ Exit Successfully Recorded!")
                st.markdown(f"""
                <div class="form-panel" style="border-left:4px solid #3b82f6">
                    <h3 style="color:#1a2744;margin:0 0 12px">🚪 {visitor['full_name']}</h3>
                    <table style="width:100%;font-size:.9rem;border-collapse:collapse">
                        <tr><td style="color:#64748b;padding:5px 0;width:140px">Visitor No</td>
                            <td><strong>{visitor['visitor_number']}</strong></td></tr>
                        <tr><td style="color:#64748b;padding:5px 0">Department</td>
                            <td>{visitor['department']} &rarr; {visitor['person_to_visit']}</td></tr>
                        <tr><td style="color:#64748b;padding:5px 0">Entry</td>
                            <td>{visitor['entry_date']} at {visitor['entry_time']}</td></tr>
                        <tr><td style="color:#64748b;padding:5px 0">Exit</td>
                            <td>{now.strftime('%Y-%m-%d')} at {now.strftime('%H:%M:%S')}</td></tr>
                    </table>
                    <div style="margin-top:14px;padding:12px 16px;background:#dbeafe;border-radius:8px;text-align:center">
                        <span style="color:#64748b;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em">Total Visit Duration (Auto-Calculated)</span><br>
                        <span style="color:#1d4ed8;font-size:1.6rem;font-weight:700">{duration}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        elif checkout_btn:
            st.warning("Please enter a visitor number or scan a QR code.")

        st.markdown("</div>", unsafe_allow_html=True)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: REPORTS                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_reports():
    if not st.session_state.logged_in:
        st.warning("Admin access required.")
        return

    admin = st.session_state.admin
    st.markdown('<p class="section-title">📄 Reports</p>', unsafe_allow_html=True)

    # ── Filters ────────────────────────────────────────────────────────────
    with st.expander("🔧 Report Filters", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            report_type = st.selectbox("Report Period",
                ["Today", "This Week", "This Month", "Custom Range"])
        with c2:
            status_f = st.selectbox("Status", ["All", "Pending", "Approved", "Rejected", "Checked Out"])
        with c3:
            dept_f = st.selectbox("Department", ["All"] + db.get_departments())
        with c4:
            fmt = st.selectbox("Export Format", ["Excel (.xlsx)", "CSV", "PDF"])

        if report_type == "Custom Range":
            dc1, dc2 = st.columns(2)
            with dc1:
                date_from = st.date_input("From Date")
            with dc2:
                date_to   = st.date_input("To Date")

    # ── Fetch data ─────────────────────────────────────────────────────────
    today = lagos_now()
    if report_type == "Today":
        visitors = db.get_visitors(date=today.strftime("%Y-%m-%d"))
        report_title = f"Daily Report — {today.strftime('%d %B %Y')}"
    elif report_type == "This Week":
        start = today - timedelta(days=today.weekday())
        all_v = db.get_visitors()
        visitors = [v for v in all_v if v.get("entry_date", "") >= start.strftime("%Y-%m-%d")]
        report_title = f"Weekly Report — Week of {start.strftime('%d %b %Y')}"
    elif report_type == "This Month":
        month_str = today.strftime("%Y-%m")
        all_v = db.get_visitors()
        visitors = [v for v in all_v if v.get("entry_date", "").startswith(month_str)]
        report_title = f"Monthly Report — {today.strftime('%B %Y')}"
    else:
        all_v = db.get_visitors()
        visitors = [v for v in all_v if
                    date_from.strftime("%Y-%m-%d") <= v.get("entry_date","") <= date_to.strftime("%Y-%m-%d")]
        report_title = f"Custom Report: {date_from} to {date_to}"

    # Apply additional filters
    if status_f != "All":
        visitors = [v for v in visitors if v["status"] == status_f]
    if dept_f != "All":
        visitors = [v for v in visitors if v["department"] == dept_f]

    # ── Preview ─────────────────────────────────────────────────────────────
    st.markdown(f"### {report_title}")
    st.caption(f"**{len(visitors)}** records found")

    if visitors:
        df = pd.DataFrame(visitors)[[
            "visitor_number", "full_name", "phone", "department",
            "person_to_visit", "purpose", "status",
            "entry_date", "entry_time", "exit_date", "exit_time", "visit_duration"
        ]]
        df.columns = ["Visitor #", "Name", "Phone", "Dept", "Host", "Purpose", "Status",
                      "Entry Date", "Entry Time", "Exit Date", "Exit Time", "Duration"]
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Export ──────────────────────────────────────────────────────────────
    col_exp, _ = st.columns([1, 3])
    with col_exp:
        if st.button("📥 Generate & Download Report", type="primary", use_container_width=True):
            if not visitors:
                st.warning("No data to export.")
            else:
                if fmt == "Excel (.xlsx)":
                    data = reports.generate_excel_report(visitors, report_title)
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    fname = f"VMS_Report_{today.strftime('%Y%m%d')}.xlsx"
                elif fmt == "CSV":
                    data = reports.generate_csv_report(visitors)
                    mime = "text/csv"
                    fname = f"VMS_Report_{today.strftime('%Y%m%d')}.csv"
                else:
                    data = reports.generate_pdf_report(visitors, report_title)
                    mime = "application/pdf"
                    fname = f"VMS_Report_{today.strftime('%Y%m%d')}.pdf"

                st.download_button(
                    label=f"⬇️ Download {fmt}",
                    data=data,
                    file_name=fname,
                    mime=mime,
                    use_container_width=True
                )
                db.log_audit(admin["username"], "REPORT_DOWNLOADED",
                             f"{report_title} | {len(visitors)} records | {fmt}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: SETTINGS                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def page_settings():
    if not st.session_state.logged_in:
        st.warning("Admin access required.")
        return

    admin = st.session_state.admin
    st.markdown('<p class="section-title">⚙️ Settings</p>', unsafe_allow_html=True)

    tab_pw, tab_admins, tab_dept, tab_audit = st.tabs(
        ["🔑 Change Password", "👥 Admin Accounts", "🏛️ Departments", "📋 Audit Log"])

    # ── Change password ──────────────────────────────────────────────────
    with tab_pw:
        st.markdown("### Change Your Password")
        with st.form("settings_pw_form"):
            current_pw  = st.text_input("Current Password", type="password")
            new_pw      = st.text_input("New Password",     type="password")
            confirm_pw  = st.text_input("Confirm New Password", type="password")
            upd         = st.form_submit_button("Update Password", type="primary")

        if upd:
            verified = db.verify_admin(admin["username"], current_pw)
            if not verified:
                st.error("Current password is incorrect.")
            elif len(new_pw) < 8:
                st.error("New password must be at least 8 characters.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            else:
                db.update_admin_password(admin["username"], new_pw)
                db.log_audit(admin["username"], "PASSWORD_CHANGED", "Self-service change")
                st.success("Password updated successfully!")

    # ── Admin accounts ───────────────────────────────────────────────────
    with tab_admins:
        if admin["role"] == "Super Admin":
            st.markdown("### Admin Accounts")
            admins_list = db.get_admins()
            if admins_list:
                df_a = pd.DataFrame(admins_list)[
                    ["username", "full_name", "role", "email", "is_active", "last_login"]]
                df_a.columns = ["Username", "Full Name", "Role", "Email", "Active", "Last Login"]
                st.dataframe(df_a, use_container_width=True, hide_index=True)

            st.markdown("### Add New Admin")
            with st.form("add_admin_form"):
                c1, c2 = st.columns(2)
                with c1:
                    new_uname = st.text_input("Username")
                    new_full  = st.text_input("Full Name")
                    new_role  = st.selectbox("Role", ["Super Admin", "Security Officer", "Receptionist"])
                with c2:
                    new_email = st.text_input("Email")
                    new_pw_a  = st.text_input("Password", type="password")
                add_btn = st.form_submit_button("➕ Add Admin", type="primary")

            if add_btn:
                if not new_uname or not new_pw_a or not new_full:
                    st.error("Username, full name and password are required.")
                else:
                    ok = db.add_admin(new_uname, new_pw_a, new_full, new_role, new_email)
                    if ok:
                        db.log_audit(admin["username"], "ADMIN_CREATED", f"New admin: {new_uname}")
                        st.success(f"Admin '{new_uname}' created successfully.")
                        st.rerun()
                    else:
                        st.error("Username already exists.")
        else:
            st.info("Only Super Admins can manage admin accounts.")

    # ── Departments ──────────────────────────────────────────────────────
    with tab_dept:
        st.markdown("### Departments")
        depts = db.get_departments()
        for d in depts:
            st.markdown(f"- {d}")

        st.markdown("### Add Department")
        with st.form("add_dept_form"):
            new_dept = st.text_input("Department Name")
            add_d    = st.form_submit_button("➕ Add", type="primary")
        if add_d and new_dept.strip():
            from modules.database import get_connection
            conn = get_connection()
            try:
                conn.execute("INSERT INTO departments(name) VALUES (?)", (new_dept.strip(),))
                conn.commit()
                db.log_audit(admin["username"], "DEPT_ADDED", new_dept.strip())
                st.success(f"Department '{new_dept}' added.")
                st.rerun()
            except Exception:
                st.error("Department already exists.")
            finally:
                conn.close()

    # ── Audit log ────────────────────────────────────────────────────────
    with tab_audit:
        st.markdown("### Audit Trail")
        if admin["role"] in ["Super Admin", "Security Officer"]:
            logs = db.get_audit_logs(200)
            if logs:
                df_log = pd.DataFrame(logs)[["created_at", "username", "action", "details", "ip_address"]]
                df_log.columns = ["Timestamp", "User", "Action", "Details", "IP"]
                st.dataframe(df_log, use_container_width=True, hide_index=True)
            else:
                st.info("No audit logs yet.")
        else:
            st.info("Audit log access requires Super Admin or Security Officer role.")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  MAIN ROUTER                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def main():
    render_sidebar()

    page = st.session_state.page

    if page == "login":
        page_login()
    elif page == "change_password":
        page_change_password()
    elif page == "dashboard":
        if st.session_state.logged_in:
            page_dashboard()
        else:
            page_register()
    elif page == "register":
        page_register()
    elif page == "approvals":
        page_approvals()
    elif page == "tracking":
        page_tracking()
    elif page == "track":
        page_track_public()
    elif page == "checkout":
        page_checkout()
    elif page == "reports":
        page_reports()
    elif page == "settings":
        page_settings()
    else:
        page_register()


if __name__ == "__main__":
    main()

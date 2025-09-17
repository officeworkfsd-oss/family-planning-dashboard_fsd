# Fixed streamlit_client_app_v2.py
# Improvements made:
# - Robust Excel reading (supports path or uploaded BytesIO)
# - Normalizes CNIC values (removes non-digits, .0 etc.) and uses normalized CNIC for matching
# - More resilient column detection (looks for AX/AY and common keywords)
# - Fallback UI to let user pick follow-up columns if auto-detection fails
# - Minor bugfixes for pandas warnings and safe indexing
# - Integrated Admin vs User logic (upload allowed only in Admin mode, server copy maintained)

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date
from dateutil.relativedelta import relativedelta
import io
import re
import os

st.set_page_config(page_title="Client Follow-Up Dashboard (Fixed)", layout="wide")

st.title("Individual Client Search")
st.markdown("Upload your workbook (Admin only) or use the saved server copy. This version improves CNIC matching and follow-up column detection.")

# ab file project ke andar save hogi
DEFAULT_PATH = "Client_Follow-Up_Data.xlsx"

# ---------- Helpers ----------

def load_sheets(filelike):
    try:
        if isinstance(filelike, (str,)):
            x = pd.read_excel(filelike, sheet_name=None)
        else:
            filelike.seek(0)
            x = pd.read_excel(filelike, sheet_name=None)
        sheets = {}
        for name, df in x.items():
            df = df.copy()
            df.columns = [str(c).strip() for c in df.columns.tolist()]
            sheets[name] = df
        return sheets
    except Exception as e:
        raise

def find_column(df, keywords, prefer_contains=True):
    if df is None:
        return None
    cols = df.columns.tolist()
    lowcols = [str(c).lower() for c in cols]
    for kw in keywords:
        kwl = kw.lower()
        for i, c in enumerate(lowcols):
            if c == kwl:
                return cols[i]
    for kw in keywords:
        kwl = kw.lower()
        for i, c in enumerate(lowcols):
            if kwl in c:
                return cols[i]
    for kw in keywords:
        kwl = kw.lower()
        for i, c in enumerate(lowcols):
            if c.startswith(kwl):
                return cols[i]
    return None

def normalize_cnic(val):
    if pd.isna(val):
        return ""
    s = str(val)
    s = re.sub(r"\.0$", "", s)
    s = re.sub(r"[^0-9]", "", s)
    return s.strip()

def safe_get_first(df, col):
    if col is None or col not in df.columns:
        return None
    s = df[col].dropna()
    return s.iloc[0] if not s.empty else None

def parse_date(x):
    try:
        return pd.to_datetime(x)
    except:
        return pd.NaT

def add_months(dt, months):
    if pd.isna(dt):
        return pd.NaT
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime().date()
    if isinstance(dt, (date,)):
        r = dt + relativedelta(months=months)
        return pd.Timestamp(r)
    try:
        d = pd.to_datetime(dt).date()
        r = d + relativedelta(months=months)
        return pd.Timestamp(r)
    except:
        return pd.NaT

def normalize_phone(val):
    """Ensure phone is 11-digit string like 03001234567"""
    if pd.isna(val):
        return "-"
    s = str(val).strip()
    s = re.sub(r"\.0$", "", s)  # remove trailing .0
    s = re.sub(r"\D", "", s)    # keep only digits
    if len(s) == 11:
        return s
    elif len(s) > 11:
        return s[-11:]  # take last 11 digits (in case country code included)
    else:
        return s  # return as-is if shorter

# ---------- Admin vs User ----------
st.sidebar.header("Login Mode")
password = st.sidebar.text_input("Enter Admin Password:", type="password")

is_admin = (password == "admin123")   # apna password set karo

if is_admin:
    st.sidebar.success("✅ Admin Mode Active")
    uploaded = st.file_uploader(
        "Upload Excel workbook (.xlsx)", 
        type=["xlsx"], 
        key="admin_uploader"
    )

    if uploaded is not None:
        try:
            # Save uploaded file as permanent server copy
            with open(DEFAULT_PATH, "wb") as f:
                f.write(uploaded.getbuffer())
            sheets = load_sheets(DEFAULT_PATH)
            st.success("✅ Workbook uploaded and saved as server copy.")
        except Exception as e:
            st.error(f"Failed to save uploaded file: {e}")
            sheets = {}
    else:
        # If no new upload, try loading existing server copy
        if os.path.exists(DEFAULT_PATH):
            sheets = load_sheets(DEFAULT_PATH)
            st.info("Using previously saved server workbook.")
        else:
            st.warning("No server workbook found. Please upload a file.")
            sheets = {}

else:
    st.sidebar.info("👥 User Mode (Upload disabled)")
    if os.path.exists(DEFAULT_PATH):
        try:
            sheets = load_sheets(DEFAULT_PATH)
            st.success("Loaded saved server workbook.")
        except Exception as e:
            st.error(f"❌ Error loading saved server workbook: {e}")
            sheets = {}
    else:
        st.error("❌ No server workbook found. Please ask Admin to upload Excel file.")
        sheets = {}

if not sheets:
    st.stop()

# ---------- Let user pick master & follow-up sheets ----------
st.sidebar.header("Detected sheets")
for name, df in sheets.items():
    st.sidebar.write(f"- {name}: {df.shape[0]} rows × {df.shape[1]} cols")

# auto-detect probable sheets
possible_master = None
possible_follow = None
for name, df in sheets.items():
    cols = [c.lower() for c in df.columns]
    if 'cnic' in cols and 'name' in cols and possible_master is None:
        possible_master = name
    if any('service date' in c for c in cols) and possible_follow is None:
        possible_follow = name

master_name = st.sidebar.selectbox(
    "Master (sheet1) — clients", 
    options=list(sheets.keys()), 
    index=list(sheets.keys()).index(possible_master) if possible_master else 0
)
follow_name = st.sidebar.selectbox(
    "Follow-up (sheet2) — services", 
    options=list(sheets.keys()), 
    index=list(sheets.keys()).index(possible_follow) if possible_follow else 0
)

df_master = sheets[master_name].copy()
df_follow = sheets[follow_name].copy()


# ---------- Normalize CNIC columns and create normalized cnic fields ----------
# ... (rest of your CNIC, alert, MWRA info, service/follow-up history, display code remains same as you pasted earlier) ...


# ---------- Normalize CNIC columns and create normalized cnic fields ----------
# detect CNIC column names
master_cnic_col = find_column(df_master, ['CNIC','cnic','Cnic','National ID'])
follow_cnic_col = find_column(df_follow, ['CNIC','cnic','Cnic','P','P:P','Client CNIC','CNIC No','CNIC_NO'])

# create normalized CNIC columns
if master_cnic_col:
    df_master['__cnic_norm'] = df_master[master_cnic_col].apply(normalize_cnic)
else:
    df_master['__cnic_norm'] = ""

if follow_cnic_col:
    df_follow['__cnic_norm'] = df_follow[follow_cnic_col].apply(normalize_cnic)
else:
    df_follow['__cnic_norm'] = ""

# also normalize any CNIC-like columns that are named strangely (helpful for MATCH on column P in Excel)
# keep a list of potential CNIC columns (normalized)
potential_cnic_cols = []
for c in df_follow.columns:
    if re.search(r'cnic|id|national', str(c), re.I) or str(c).strip().upper() in ['P','P:P']:
        potential_cnic_cols.append(c)

# if follow_cnic_col missing but potential exists, pick first
if not follow_cnic_col and potential_cnic_cols:
    follow_cnic_col = potential_cnic_cols[0]
    df_follow['__cnic_norm'] = df_follow[follow_cnic_col].apply(normalize_cnic)

# ---------- Column detection (keywords driven) ----------
master_cols = {
    'cnic': master_cnic_col,
    'name': find_column(df_master, ['Name','name','Client Name','Full Name']),
    'address': find_column(df_master, ['Address','ADDRESS','Home Address']),
    'phone': find_column(df_master, ['Phone','Phone NO','MOBILE','Mobile','Mobile_NO','Contact']),
    'age': find_column(df_master, ['Age','AGE','DOB','Date of Birth']),
    'marital': find_column(df_master, ['Marital Status','Marital','Marital_Status'])  # <-- new
}

follow_cols = {
    'cnic': follow_cnic_col,
    'date_of_registration': find_column(df_follow, ['Date of Registration','Registration Date','Date of Registration ']),
    'bisp': find_column(df_follow, ['BISP','BISP_STATUS','BISP BENF','BISP BENF/NON BISP','BISP Beneficiary']),
    'fpc_name': find_column(df_follow, ['Name of FPC','FPC Name','FPC','Provider FPC']),
    'provider': find_column(df_follow, ['Provider','Clinic','Provider /Clinic Name','Provider / Clinic Name','Clinic Name']),
    'method_visit1': find_column(df_follow, ['Method Provided on First Visit','Method Visit 1','Method Provided','Method','B17']),
    'service_date_1': find_column(df_follow, ['Service Date','Service Date 1','Service Date .1']),
    'fp_user': find_column(df_follow, ["Client Type", "FP User", "User Status"]),
    'marital': find_column(df_follow, ["Marital", "Marital Status", "Status"]),    # <-- new
    # follow-up columns - try keywords, visit-specific headers and also column-letters AX/AY
    'follow_service_1': find_column(df_follow, [
        'Follow-Up Service','Follow Up Service','1st Follow-Up Service',
        'Method Provided on 4th Visit','Method Provided on 4th Visit (Aug-Follow Up)','Aug-Follow Up',
        'Method Provided on .* Visit','AX','ax'
    ]),
    'follow_service_date_1': find_column(df_follow, [
        'Follow-Up Service Date','Follow Up Service Date','1st Follow-Up Service Date',
        'Service Date .3','4th Visit Service Date','Service Date','AY','ay'
    ]),
    'method_visit2': find_column(df_follow, ['Method Provided on 2nd Visit','Method Visit 2']),
    'service_date_2': find_column(df_follow, ['Service Date .1','Service Date 2']),
    'service_date_3': find_column(df_follow, ['Service Date .2','Service Date 3']),
    'service_date_4': find_column(df_follow, ['Service Date .3','Service Date 4']),
    'service_date_5': find_column(df_follow, ['Service Date .4','Service Date 5']),
}

# If follow-up columns still not found, allow user to pick them manually from sidebar (helpful for AX/AY etc.)
if follow_cols['follow_service_1'] is None:
    st.sidebar.markdown("**Auto-detection couldn't find 1st Follow-Up Service column. Pick it manually (optional):**")
    picked = st.sidebar.selectbox("1st Follow-Up Service column (optional)", options=[None] + list(df_follow.columns), index=0)
    if picked:
        follow_cols['follow_service_1'] = picked

if follow_cols['follow_service_date_1'] is None:
    st.sidebar.markdown("**Auto-detection couldn't find 1st Follow-Up Service Date column. Pick it manually (optional):**")
    picked = st.sidebar.selectbox("1st Follow-Up Service Date column (optional)", options=[None] + list(df_follow.columns), index=0, key='fu_date_pick')
    if picked:
        follow_cols['follow_service_date_1'] = picked

# ---------- UI: CNIC input ----------
st.subheader("Dashboard (Enter CNIC)")
# use session state so button can set value
if 'cnic_input' not in st.session_state:
    st.session_state['cnic_input'] = ""

cnic_input = st.text_input("Search CNIC:", value=st.session_state['cnic_input'], key='cnic_widget')
if st.button("Pick example CNIC from follow-up"):
    # pick first non-empty normalized CNIC from follow sheet if available else master
    ex = ""
    if '__cnic_norm' in df_follow.columns and df_follow['__cnic_norm'].astype(str).str.strip().ne('').any():
        ex = df_follow.loc[df_follow['__cnic_norm'].astype(str).str.strip() != '', '__cnic_norm'].iloc[0]
    elif '__cnic_norm' in df_master.columns and df_master['__cnic_norm'].astype(str).str.strip().ne('').any():
        ex = df_master.loc[df_master['__cnic_norm'].astype(str).str.strip() != '', '__cnic_norm'].iloc[0]
    if ex:
        st.session_state['cnic_input'] = ex
        st.experimental_rerun()

if not cnic_input:
    st.info("Enter CNIC to compute Dashboard values (BISP, Registration, Alerts, MWRA info, Service & Follow-up history).")
    st.stop()

cnic = normalize_cnic(cnic_input)

# ---------- Implement formulas (replicated) ----------
# BISP Beneficiaries:
bisp_status = ""
if cnic == "":
    bisp_status = ""
else:
    # check existence in sheet1 normalized CNIC column
    if '__cnic_norm' in df_master.columns and cnic in df_master['__cnic_norm'].astype(str).tolist():
        bisp_status = "YES"
    else:
        bisp_status = "NO"

# Registration:
reg_status = ""
if cnic == "":
    reg_status = ""
else:
    if '__cnic_norm' in df_follow.columns and cnic in df_follow['__cnic_norm'].astype(str).tolist():
        reg_status = "Registered"
    else:
        reg_status = "Not Registered"

# For later lookups: subset of follow rows for this normalized CNIC
follow_rows = pd.DataFrame()
if '__cnic_norm' in df_follow.columns and cnic in df_follow['__cnic_norm'].astype(str).tolist():
    follow_rows = df_follow[df_follow['__cnic_norm'].astype(str) == cnic].copy()

# find last service date (search service_date_1..5 or any column that contains 'service date')
sdate_candidates = []
for c in df_follow.columns:
    if 'service date' in str(c).lower() or re.search(r'service\s*date', str(c), re.I):
        sdate_candidates.append(c)
for key in ['service_date_1','service_date_2','service_date_3','service_date_4','service_date_5']:
    col = follow_cols.get(key)
    if col and col not in sdate_candidates:
        sdate_candidates.append(col)

last_service = pd.NaT
service_count = 0
if not follow_rows.empty and sdate_candidates:
    for c in sdate_candidates:
        # coerce errors
        follow_rows[c] = pd.to_datetime(follow_rows.get(c), errors='coerce')
    try:
        last_service = follow_rows[sdate_candidates].max(axis=1).max()
    except Exception:
        last_service = pd.NaT
    try:
        service_count = int(follow_rows[sdate_candidates].notna().sum(axis=1).sum())
    except Exception:
        service_count = 0

# Alert logic
alert_msg = ""
primary_service_method_col = follow_cols.get('method_visit1')
primary_service_method_value = None
if primary_service_method_col and not follow_rows.empty:
    primary_service_method_value = safe_get_first(follow_rows, primary_service_method_col)

if last_service is not pd.NaT and not pd.isna(last_service):
    alert_msg = "Ye Khatoon Register bhi Ho Chuki Hai or Service bhi Le Chuki"
else:
    if bisp_status == "NO":
        alert_msg = "Is Khatoon Ko Register Karny ya Service Denay Ki Zaroorat Nahi Kyun k Ye BISP Beneficiary Nahi Hai"
    elif bisp_status == "YES" and reg_status == "Registered":
        alert_msg = "FP-Champion Ko Is Khatoon Ko Dubara Register Karnay Ki Zaroorat Nahi, Kyun K Ye Khatoon 1 dafa Register Ho Chuki Hai"
    elif bisp_status == "YES" and reg_status == "Not Registered":
        alert_msg = "Ye Khatoon BISP Beneficiary hai Isko FP-Champion Register Kar Sakti Hai"
    else:
        alert_msg = ""

# --- same imports, helpers, admin/user logic as in your fixed code above ---
# (no change till MWRA Information section)

# ---------- MWRA Information ----------
mwra_name = ""
mwra_cnic = ""
mwra_phone = ""
mwra_address = ""
mwra_fpc = ""
mwra_age = ""
mwra_marital = ""   # ✅ sirf ye use karna hai
mwra_fp_user = ""
mwra_reg_date = ""

if bisp_status == "NO":
    mwra_name = mwra_cnic = mwra_phone = mwra_address = mwra_fpc = "-"
    mwra_age = mwra_marital = mwra_fp_user = mwra_reg_date = "-"
else:
    # From Master (Sheet1)
    row_master = df_master[df_master['__cnic_norm'] == cnic]
    if not row_master.empty:
        r1 = row_master.iloc[0]
        mwra_name = str(r1.get(master_cols['name'], "-"))
        mwra_cnic = str(r1.get(master_cols['cnic'], cnic))
        mwra_phone = normalize_phone(r1.get(master_cols['phone'], "-"))
        mwra_address = str(r1.get(master_cols['address'], "-"))

        # ✅ Marital Status direct set
        mwra_marital = str(r1.get(master_cols['marital'], "-"))

        # DOB se Age calculate
        dob_raw = r1.get(master_cols['age'], "-")
        dob = parse_date(dob_raw)
        if pd.notna(dob):
            today = pd.to_datetime("today")
            mwra_age = str(int((today - dob).days / 365.25))
        else:
            mwra_age = "-"

    # From Follow-ups (Sheet2) — only FPC, FP User, Registration Date
    row_fu = df_follow[df_follow['__cnic_norm'] == cnic]
    fpc_col = follow_cols.get('fpc_name')
    reg_col = follow_cols.get('date_of_registration')
    fp_user_col = follow_cols.get('fp_user')

    if not row_fu.empty:
        r2 = row_fu.iloc[0]
        mwra_fpc = str(r2.get(fpc_col, "-")) if fpc_col else "-"
        mwra_reg_date = r2.get(reg_col, "-") if reg_col else "-"
        mwra_fp_user = str(r2.get(fp_user_col, "-")) if fp_user_col else "-"
    else:
        mwra_fpc = "-"
        mwra_reg_date = "-"
        mwra_fp_user = "-"


# ---------- Service History ----------
service_availed = ""
service_date = pd.NaT
followup_due_date = ""
provider_name = ""

if reg_status == "Registered" and not follow_rows.empty:
    method_col = follow_cols.get('method_visit1') or find_column(df_follow, ['Method Provided on First Visit','Method Visit 1','Method'])
    if method_col and method_col in follow_rows.columns:
        service_availed = safe_get_first(follow_rows, method_col) or ""
        if str(service_availed).strip() in ['0','0.0']:
            service_availed = ""
    svc_date_col = follow_cols.get('service_date_1') or (sdate_candidates[0] if sdate_candidates else None)
    if svc_date_col and svc_date_col in follow_rows.columns:
        sd = safe_get_first(follow_rows, svc_date_col)
        service_date = parse_date(sd)
    if isinstance(service_availed, str) and service_availed.strip().upper().startswith('IUCD'):
        followup_due_date = "Is Client Nay IUCD ki Service Li Hui Hai Is Ko Follow-Up ki Zaroorat Nahi"
    else:
        if pd.notna(service_date):
            fdate = add_months(service_date, 3)
            followup_due_date = fdate.date().isoformat() if pd.notna(fdate) else ""
        else:
            followup_due_date = ""
    prov_col = follow_cols.get('provider') or find_column(df_follow, ['Provider','Clinic','Provider /Clinic Name'])
    if prov_col:
        provider_name = safe_get_first(follow_rows, prov_col) or ""
    else:
        provider_name = "-"
else:
    service_availed = ""
    service_date = pd.NaT
    followup_due_date = ""
    provider_name = "-" if reg_status == "Not Registered" else ""

# ---------- Follow-Up History ----------
fu_service_1 = ""
fu_service_date_1 = pd.NaT
fu_due_2 = ""

if bisp_status == "YES" and reg_status == "Registered":
    fu_col = follow_cols.get('follow_service_1') or find_column(df_follow, [
        'Method Provided on 4th Visit',
        'Method Provided on 4th Visit (Aug-Follow Up)',
        'Aug-Follow Up',
        'Method Provided on .* Visit',
        'Follow-Up Service',
        'AX',
        'ax'
    ])

    if fu_col and fu_col in follow_rows.columns and not follow_rows.empty:
        fu_service_1 = safe_get_first(follow_rows, fu_col) or ""

    # ✅ IUCD case: koi follow-up na ho
    if service_availed.strip().upper().startswith("IUCD"):
        fu_service_date_1 = pd.NaT
        fu_due_2 = ""
    else:
        if pd.notna(service_date):
            # 👉 Service History ka Follow-Up Due Date
            service_fu_due = add_months(service_date, 3)

            if pd.notna(service_fu_due):
                # 👉 Follow-Up History ka 1st Follow-Up Service Date
                fu_service_date_1 = service_fu_due

                # 👉 Follow-Up History ka 2nd Follow-Up Due Date = 1st + 3 months
                fu_due_2 = add_months(fu_service_date_1, 3)
                fu_due_2 = fu_due_2.date().isoformat()
            else:
                fu_service_date_1 = pd.NaT
                fu_due_2 = ""
        else:
            fu_service_date_1 = pd.NaT
            fu_due_2 = ""
else:
    fu_service_1 = ""
    fu_service_date_1 = pd.NaT
    fu_due_2 = ""



# ---------- Display (mimic your Dashboard layout) ----------
st.markdown("### Summary")
cols = st.columns([2,2,2,4])
cols[0].write("**BISP Beneficiaries**")
cols[0].write(bisp_status or "")
cols[1].write("**Registration**")
cols[1].write(reg_status or "")
cols[2].write("**Alert**")
cols[2].info(alert_msg or "")

st.markdown("---")
st.markdown("## MWRA Information")
info_table = {
    "Name": [mwra_name],
    "CNIC": [mwra_cnic],
    "Phone NO.": [mwra_phone],
    "Address": [mwra_address],
    "Age": [mwra_age],
    "Marital Status": [mwra_marital],
    "FP User (Current/Ever/Never)": [mwra_fp_user],
    "FPC Name": [mwra_fpc],
    "Registration Date": [mwra_reg_date]
}
info_df = pd.DataFrame(info_table)
st.dataframe(info_df.T, use_container_width=True)

st.markdown("## Service History")
svc_table = {
    "1st Service Availed": [service_availed],
    "Service Date": [service_date.date().isoformat() if pd.notna(service_date) else ""],
    "Follow-Up Due Date": [followup_due_date],
    "Provider/Clinic Name": [provider_name]
}
st.table(pd.DataFrame(svc_table))

st.markdown("## Follow Up History")
fu_table = {
    "1st Follow-Up Service": [fu_service_1],
    "1st Follow-Up Service Date": [fu_service_date_1.date().isoformat() if pd.notna(fu_service_date_1) else ""],
    "2nd Follow-Up Due Date": [fu_due_2]
}
st.table(pd.DataFrame(fu_table))

st.markdown("---")
st.write("### Raw follow-up rows matched (from follow-up sheet):")
if not follow_rows.empty:
    st.dataframe(follow_rows)
    st.download_button("Download matched follow-up rows as CSV", data=follow_rows.to_csv(index=False).encode('utf-8'), file_name=f"{cnic}_followups.csv", mime='text/csv')
else:
    st.write("No follow-up rows found for this CNIC.")

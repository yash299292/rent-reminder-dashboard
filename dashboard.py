import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import matplotlib.pyplot as plt
import os
import subprocess
import json

# ✅ Use official rerun for Streamlit v1.40+
do_rerun = st.rerun

# 🔐 Password protection
password = st.text_input("Enter admin password", type="password")
if password != "Rent2025":
    st.warning("Access Denied")
    st.stop()

# ✅ Google Sheets auth using Streamlit secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(st.secrets["GOOGLE_CREDS"]),
    scope
)
client = gspread.authorize(creds)
sheet = client.open("Rent Reminder Sheet").worksheet("RentBills")
headers = sheet.row_values(1)

# 🔄 Manual refresh
if st.button("🔄 Refresh"):
    do_rerun()

# 📨 Trigger rent reminder script (for local use only)
if st.button("📨 Send Rent Reminders Now"):
    with st.spinner("Sending reminders via rent_reminder_pdf.py..."):
        try:
            subprocess.run(["python3", "rent_reminder_pdf.py"], check=True)
            st.success("✅ Reminders sent successfully!")
            do_rerun()
        except Exception as e:
            st.error(f"❌ Failed to send reminders: {e}")

# 📊 Load and filter tenant data
records = sheet.get_all_records()
st.title("🏠 Rent Reminder Dashboard")

# 📅 Filter by month
months_available = sorted(set(r["bill_month"] for r in records if r.get("bill_month")))
selected_month = st.selectbox("📅 Filter by Month", ["All"] + months_available)

# 🔍 Filter by paid/unpaid
status = st.selectbox("Filter by status", ["All", "PAID", "UNPAID"])

# 📊 Pie chart
paid = sum(1 for r in records if r.get("paid", "").strip().upper() == "PAID")
unpaid = len(records) - paid
fig, ax = plt.subplots()
ax.pie([paid, unpaid], labels=["Paid", "Unpaid"], autopct="%1.1f%%", colors=["green", "red"])
st.pyplot(fig)

# Apply filters
filtered = [
    r for r in records
    if (status == "All" or r.get("paid", "").strip().upper() == status)
    and (selected_month == "All" or r.get("bill_month") == selected_month)
]

st.write(f"Showing {len(filtered)} tenants")

# 🧾 Table View
for tenant in filtered:
    col1, col2, col3 = st.columns([3, 3, 2])
    current_status = tenant.get("paid", "").strip().upper()
    status_icon = "✅" if current_status == "PAID" else "❌"

    col1.write(f"{status_icon} {tenant['tenant_name']}")
    col2.write(f"📅 {tenant['due_date']}  |  💰 Rs. {tenant['rent_amount']}")

    row_index = records.index(tenant) + 2
    paid_col_index = headers.index("paid") + 1

    if current_status == "PAID":
        if col3.button("❌ Mark as UNPAID", key=tenant['tenant_name'] + "_unpaid"):
            sheet.update_cell(row_index, paid_col_index, "UNPAID")
            st.success(f"{tenant['tenant_name']} marked as UNPAID")
            do_rerun()
    else:
        if col3.button("✅ Mark as PAID", key=tenant['tenant_name'] + "_paid"):
            sheet.update_cell(row_index, paid_col_index, "PAID")
            st.success(f"{tenant['tenant_name']} marked as PAID")
            do_rerun()

    # 📄 Invoice PDF (only works if available on deployment server)
    try:
        month_year = datetime.strptime(tenant['bill_month'], "%B %Y").strftime("%Y-%m")
        pdf_folder = f"receipts/{month_year}"
        pdf_name = f"Rent_Bill_{tenant['tenant_name'].replace(' ', '_')}_{tenant['bill_month'].replace(' ', '_')}.pdf"
        pdf_path = os.path.join(pdf_folder, pdf_name)

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                col3.download_button(label="📄 Invoice", data=f, file_name=pdf_name)
        else:
            col3.warning("📄 No PDF found")
    except Exception:
        col3.warning("📄 Invalid bill_month format")

st.markdown("---")

# 📋 Log Viewer (optional)
try:
    st.subheader("📋 Reminder Log")
    log_sheet = client.open("Rent Reminder Sheet").worksheet("Log")
    log_data = log_sheet.get_all_records()
    st.dataframe(log_data[::-1])  # Show latest first
except Exception as e:
    st.warning("⚠️ Unable to load Log sheet.")
    st.text(str(e))

st.caption(f"Updated at {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}")

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dateutil.parser import parse
import matplotlib.pyplot as plt
import os
import json
from fpdf import FPDF
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# ✅ Use official rerun for Streamlit v1.40+
do_rerun = st.rerun

# 🔐 Password protection
password = st.text_input("Enter admin password", type="password")
if password != "Rent2025":
    st.warning("Access Denied")
    st.stop()

# ✅ Google Sheets auth using Streamlit secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Rent Reminder Sheet").worksheet("RentBills")
headers = sheet.row_values(1)

# 📄 PDF Generator
def generate_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(190, 10, data['company_name'], ln=True, align='C')
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 8, f"RENT INVOICE - {data['bill_month']}", ln=True, align='C')
    pdf.ln(8)

    pdf.set_font("Arial", "", 11)
    pdf.cell(25, 8, "To:", border=0)
    pdf.cell(100, 8, data['tenant_name'], ln=True)
    pdf.cell(25, 8, "Email:", border=0)
    pdf.cell(100, 8, data['email'], ln=True)
    pdf.ln(8)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(80, 8, "Description", border=0)
    pdf.cell(50, 8, "Due Date", border=0)
    pdf.cell(50, 8, "Amount (INR)", border=0, ln=True)

    pdf.set_font("Arial", "", 11)
    pdf.cell(80, 8, "Monthly Rent", border=0)
    pdf.cell(50, 8, data['due_date'], border=0)
    pdf.cell(50, 8, f"Rs. {data['rent_amount']}", border=0, ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(190, 8, f"Notes: {data['notes']}", border=0)
    pdf.ln(8)
    pdf.set_font("Arial", "I", 10)
    pdf.cell(190, 8, "Please pay before the due date. Thank you!", ln=True, align='C')

    folder = f"/tmp/receipts/{datetime.now().strftime('%Y-%m')}"
    os.makedirs(folder, exist_ok=True)
    file_path = f"{folder}/Rent_Bill_{data['tenant_name'].replace(' ', '_')}_{data['bill_month'].replace(' ', '_')}.pdf"
    pdf.output(file_path)
    return file_path

# 📧 Email Sender
def send_email(data, pdf_path, is_follow_up=False):
    msg = MIMEMultipart()
    msg['From'] = st.secrets['EMAIL']
    msg['To'] = data['email']
    msg['Subject'] = f"{'⚠️ Follow-Up: ' if is_follow_up else ''}Rent Bill - {data['bill_month']}"

    body = f"""Hi {data['tenant_name']},\n\nPlease find attached your rent bill for {data['bill_month']}.\nAmount Due: Rs. {data['rent_amount']}\nDue Date: {data['due_date']}\n\nNotes: {data['notes']}\n\nThank you,\n{data['company_name']}"""
    msg.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as f:
        part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
        msg.attach(part)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(st.secrets['EMAIL'], st.secrets['EMAIL_PASS'])
            server.sendmail(st.secrets['EMAIL'], data['email'], msg.as_string())
        print(f"Reminder successfully sent to {data['email']}")
    except Exception as e:
        print(f"Error sending email to {data['email']}: {e}")
        st.warning(f"Failed to send email to {data['email']}: {e}")

# 🔄 Manual refresh
if st.button("🔄 Refresh"):
    do_rerun()

# 📨 Trigger logic inline
if st.button("📨 Send Rent Reminders Now"):
    with st.spinner("Sending reminders and generating PDFs..."):
        records = sheet.get_all_records(expected_headers=headers)
        today = datetime.now().date()
        for row in records:
            try:
                if row.get("paid", "").strip().upper() == "PAID":
                    continue

                due_str = row.get("due_date", "").strip()
                due_date = parse(due_str, dayfirst=True).replace(year=today.year).date()
                days_from_due = (today - due_date).days
                days_before_due = (due_date - today).days

                if days_before_due not in [7, 1] and days_from_due != 3:
                    continue

                sent_on_str = row.get("sent_on", "").strip()
                if sent_on_str == today.strftime("%Y-%m-%d"):
                    continue

                pdf = generate_pdf(row)
                send_email(row, pdf, is_follow_up=(days_from_due == 3))

                row_index = records.index(row) + 2
                sent_col = headers.index("sent_on") + 1
                sheet.update_cell(row_index, sent_col, today.strftime("%Y-%m-%d"))
                print(f"Updated sent_on for {row['tenant_name']} to {today.strftime('%Y-%m-%d')}")
            except Exception as e:
                st.warning(f"Failed for {row['tenant_name']}: {e}")
        st.success("✅ All applicable reminders sent!")
        do_rerun()

# 📊 Load and filter tenant data
records = sheet.get_all_records()
st.title("🏠 Rent Reminder Dashboard")

months_available = sorted(set(r["bill_month"] for r in records if r.get("bill_month")))
selected_month = st.selectbox("📅 Filter by Month", ["All"] + months_available)
status = st.selectbox("Filter by status", ["All", "PAID", "UNPAID"])

paid = sum(1 for r in records if r.get("paid", "").strip().upper() == "PAID")
unpaid = len(records) - paid
fig, ax = plt.subplots()
ax.pie([paid, unpaid], labels=["Paid", "Unpaid"], autopct="%1.1f%%", colors=["green", "red"])
st.pyplot(fig)

filtered = [
    r for r in records
    if (status == "All" or r.get("paid", "").strip().upper() == status)
    and (selected_month == "All" or r.get("bill_month") == selected_month)
]

st.write(f"Showing {len(filtered)} tenants")

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
            do_rerun()
    else:
        if col3.button("✅ Mark as PAID", key=tenant['tenant_name'] + "_paid"):
            sheet.update_cell(row_index, paid_col_index, "PAID")
            do_rerun()

    try:
        month_year = datetime.strptime(tenant['bill_month'], "%B %Y").strftime("%Y-%m")
        pdf_path = f"/tmp/receipts/{month_year}/Rent_Bill_{tenant['tenant_name'].replace(' ', '_')}_{tenant['bill_month'].replace(' ', '_')}.pdf"
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                col3.download_button(label="📄 Invoice", data=f, file_name=os.path.basename(pdf_path))
        else:
            col3.caption("📄 Not available")
    except Exception:
        col3.caption("📄 Invalid date format")

st.markdown("---")

try:
    st.subheader("📋 Reminder Log")
    log_sheet = client.open("Rent Reminder Sheet").worksheet("Log")
    log_data = log_sheet.get_all_records()
    st.dataframe(log_data[::-1])
except Exception as e:
    st.warning("⚠️ Log sheet not found")
    st.text(str(e))

st.caption(f"Updated at {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}")

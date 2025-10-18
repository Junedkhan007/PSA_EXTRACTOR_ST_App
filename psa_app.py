import streamlit as st
import paramiko
import io
from datetime import datetime
import pandas as pd

# ---------------------------------------------
# App Configuration
# ---------------------------------------------
st.set_page_config(
    page_title="DELTEK REPLICON - PSA FILE EXTRACTOR",
    page_icon="📊",
    layout="wide"
)

VERSION = "v1.4"

# --- Read SFTP credentials from secrets.toml ---
try:
    SFTP_HOST = st.secrets["sftp"]["host"]
    SFTP_USERNAME = st.secrets["sftp"]["username"]
    SFTP_PASSWORD = st.secrets["sftp"]["password"]
    SFTP_PORT = int(st.secrets["sftp"].get("port", 22))
except Exception as e:
    st.error("❌ Missing or invalid SFTP credentials in `.streamlit/secrets.toml`.")
    st.stop()

# --- ERP Configuration ---
ERP_CONFIG = {
    "COMPASS": {
        "input_dir": "/Production/Inbound/C1CP Resource Assignments/Archives",
        "log_dir":   "/Production/Inbound/C1CP Resource Assignments/Logs/Archive",
        "pattern":   "PSA-Assignment-CP"
    },
    "C1": {
        "input_dir": "/Production/Inbound/C1CP Resource Assignments/Archives",
        "log_dir":   "/Production/Inbound/C1CP Resource Assignments/Logs/Archive",
        "pattern":   "PSA-Assignment-C1"
    },
    "GSAP": {
        "input_dir": "/Production/Inbound/Resource Assignments/Archive",
        "log_dir":   "/Production/Inbound/Resource Assignments/Logs/Archive",
        "pattern":   None
    }
}


# ---------------------------------------------
# Helper Function
# ---------------------------------------------
def generate_report(selected_erp, target_date):
    cfg = ERP_CONFIG[selected_erp]
    input_dir = cfg["input_dir"]
    log_dir = cfg["log_dir"]
    pattern = cfg["pattern"]

    report_data = []

    try:
        # --- Connect to SFTP ---
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # --- Collect input files ---
        input_files = {}
        for f in sftp.listdir_attr(input_dir):
            if not f.filename.endswith(".pgp"):
                continue
            if pattern and (pattern not in f.filename):
                continue
            file_date = datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d')
            if file_date == target_date:
                input_files[f.filename] = f.st_mtime

        # --- Collect log files and calculate times ---
        for f in sftp.listdir_attr(log_dir):
            if not f.filename.endswith(".csv"):
                continue
            if pattern and (pattern not in f.filename):
                continue
            file_date = datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d')
            if file_date != target_date:
                continue

            file_path = f"{log_dir}/{f.filename}"
            size = f.st_size

            # Count rows
            try:
                with sftp.file(file_path, 'r') as remote_file:
                    content = io.TextIOWrapper(remote_file, encoding='utf-8')
                    row_count = sum(1 for _ in content) - 1
            except Exception:
                row_count = 0

            # Match with input file
            base_id = None
            parts = f.filename.split("_")
            if len(parts) > 1:
                base_id = parts[1]

            input_file = None
            if base_id:
                input_file = next((k for k in input_files if k.startswith(base_id)), None)

            # Calculate processing time
            processing_time = ""
            if input_file:
                input_time = datetime.fromtimestamp(input_files[input_file])
                log_time = datetime.fromtimestamp(f.st_mtime)
                diff = log_time - input_time

                total_seconds = int(diff.total_seconds())
                days, remainder = divmod(total_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)

                if days > 0:
                    processing_time = f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    processing_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            if processing_time:
                report_data.append({
                    "File Name": f.filename,
                    "Record Count": row_count,
                    "File Size (Bytes)": size,
                    "Processing Time": processing_time
                })

        sftp.close()
        transport.close()

    except Exception as e:
        st.error(f"❌ Failed to connect or process: {e}")

    return report_data


# ---------------------------------------------
# Streamlit UI (Left Sidebar Layout)
# ---------------------------------------------
st.title("📊 DELTEK REPLICON - PSA FILE EXTRACTOR")
st.caption(f"Developed by Juned Khan | Version {VERSION}")

with st.sidebar:
    st.header("⚙️ Configuration")
    selected_erp = st.selectbox("Select ERP", list(ERP_CONFIG.keys()))
    target_date = st.date_input("Select Date", datetime.now())
    run_report = st.button("🚀 Generate Report", type="primary")

# --- Main Area ---
if run_report:
    with st.spinner("🔄 Generating report, please wait..."):
        report = generate_report(selected_erp, target_date.strftime("%Y-%m-%d"))

    if report:
        df = pd.DataFrame(report)
        st.success(f"✅ Report generated for {selected_erp} on {target_date.strftime('%Y-%m-%d')}")
        st.dataframe(df, use_container_width=True)

        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download CSV",
            data=csv_data,
            file_name=f"{selected_erp}_report_{target_date}.csv",
            mime="text/csv"
        )
    else:
        st.info(f"No matching files found for {selected_erp} on {target_date.strftime('%Y-%m-%d')}.")

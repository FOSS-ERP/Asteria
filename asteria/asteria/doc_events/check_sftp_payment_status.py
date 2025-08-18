import paramiko
import csv
import os
import frappe
from frappe.utils import today

@frappe.whitelist()
def check_status():
    # Get SFTP credentials from Doctype
    cred_doc = frappe.get_doc("H2H Settings", "H2H Settings")
    SFTP_HOST = cred_doc.public_ip
    SFTP_PORT = cred_doc.port
    SFTP_PASSWORD = cred_doc.get_password("password")
    SFTP_USERNAME = cred_doc.username

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SFTP_HOST,
        port=SFTP_PORT,
        username=SFTP_USERNAME,
        password=SFTP_PASSWORD,
        allow_agent=False,
        look_for_keys=False
    )
    sftp = client.open_sftp()

    # Navigate to /Out
    sftp.chdir("/Out")

    # Path to site’s private files
    site_path = frappe.get_site_path("private", "files")

    for file_attr in sftp.listdir_attr():
        if file_attr.filename.endswith(".csv"):
            filename = file_attr.filename
            remote_file = file_attr.filename
            local_file = os.path.join(site_path, remote_file)

            # Download file into private/files
            sftp.get(remote_file, local_file)
            h2h_log = frappe.new_doc("H2H Log")
            # Process CSV
            with open(local_file, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                Failded_Submit = []
                for row in reader:
                    try:
                        # Example mapping: row[2] = Payment Entry, row[3] = Status, row[5] = UTR
                        if row[3] == "Paid":
                            status =  row[3]
                            payment_entry = row[2]
                            utr_no = row[5]
                            payment_doc = frappe.get_doc("Payment Entry", payment_entry)
                            try:
                                payment_doc.submit()
                            except:
                                Failded_Submit.append(payment_entry)
                            
                            h2h_log.append('vendor_payment_processor', {
                                "payment_entry" : payment_entry,
                                "document_type" : payment_doc.party_type,
                                "document" : payment_entry.party,
                                "status" : "Successful" if status == 'Paid' else "Failed"
                            })
                            
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), "CSV Processing Failed")
            
            h2h_log.posting_date = today()
            h2h_log.user=frappe.session.user
            h2h_log.icici_return_csv_file = local_file
            h2h_log.insert(ignore_permissions=True)

    
    sftp.close()
    client.close()

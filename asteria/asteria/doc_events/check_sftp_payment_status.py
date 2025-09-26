import paramiko
import csv
import os
import frappe
from frappe.utils import today, now, flt
from asteria.asteria.page.h2h_payment_transfer import connect_sftp

@frappe.whitelist()
def check_status():
    # Get SFTP credentials from Doctype
    sftp, client = connect_sftp()
    sftp.chdir("/Out")

    # Path to site’s private files
    site_path = frappe.get_site_path("private", "files")

    downloaded_files = []
    for file_attr in sftp.listdir_attr():
        if file_attr.filename.endswith(".csv"):
            remote_file = file_attr.filename
            local_file = os.path.join(site_path, remote_file)
            sftp.get(remote_file, local_file)  # download
            downloaded_files.append(local_file)

    sftp.close()
    client.close()
    if not downloaded_files:
        frappe.msgprint("No Return File Found")
    total_paid_amount  = 0
    for local_file in downloaded_files:
        # ✅ Create and insert H2H Log first
        h2h_log = frappe.new_doc("H2H Log")
        h2h_log.posting_date = today()
        h2h_log.user = frappe.session.user
        relative_path = local_file.replace(frappe.get_site_path(), "")
        h2h_log.icici_return_csv_file = relative_path
        h2h_log.custom_posting_date_and_time = now()
        h2h_log.log_type = "Return"
        h2h_log.insert(ignore_permissions=True)

        failed_submit = []
        
        with open(local_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header

            for row in reader:
                try:
                    if row[3] == "Paid":
                        status = row[3]
                        payment_entry = row[2]
                        utr_no = row[5]
                        upload_file_name = row[22].replace(".enc", '')
                        upload_file_path = f"/file/{upload_file_name}"
                        payment_doc = frappe.get_doc("Payment Entry", payment_entry)

                        try:
                            payment_doc.reference_no = utr_no
                            payment_doc.save()
                            payment_doc.submit()
                        except Exception:
                            failed_submit.append(payment_entry)

                        if payment_doc.party_type == "Employee":
                            document_type = "Expense Claim"
                        else:
                            document_type = "Purchase Order"
                        h2h_log.custom_status = status
                        total_paid_amount += flt(row[9])

                        for pay in payment_doc.references:
                            h2h_log.append(
                                'vendor_payment_processor',
                                {
                                    "payment_entry": payment_entry,
                                    "document_type" : pay.reference_doctype,
                                    "document" : pay.reference_name,
                                    "status": "Successful" if status == "Paid" else "Failed",
                                    "custom_utr_no" : utr_no,
                                    "posting_date" : payment_doc.posting_date,
                                    "amount" : flt(row[9])
                                }
                            )
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "CSV Processing Failed")

    # ✅ Save log again after processing rows
    h2h_log.total_paid_amount = total_paid_amount
    h2h_log.save(ignore_permissions=True)

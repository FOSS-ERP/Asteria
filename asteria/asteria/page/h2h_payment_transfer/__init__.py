import frappe
from frappe.utils import getdate
from frappe import _
from openpyxl import load_workbook
import os
import json
from frappe.utils.file_manager import save_file
from frappe.utils import get_datetime, get_link_to_form
from io import BytesIO
from io import StringIO
from frappe.model.naming import make_autoname
import csv
import re
import paramiko
import datetime

@frappe.whitelist()
def get_vendor_payments(document_type):
    results = frappe.db.sql(
        f""" 
            Select 
                pe.name as payment_entry, 
                pe.posting_date,
                pe.party_type, 
                pe.party, 
                pe.party_name, 
                pe.paid_amount, 
                pe.paid_to_account_currency,
                pe.total_allocated_amount,
                per.reference_doctype , per.reference_name
            From `tabPayment Entry` as pe
            Left Join `tabPayment Entry Reference`  as per ON per.parent = pe.name
            Where pe.docstatus = 0 and pe.h2h_transfered = 0 and per.reference_doctype = '{document_type}'
        """, as_dict = 1
    )

    for row in results:
        row.update({
            "total_allocated_amount" : frappe.utils.fmt_money(row.total_allocated_amount, currency=row.currency),
        })

    return {"data" : results}




import csv
import json
from io import StringIO, BytesIO
from frappe.utils import get_datetime, getdate, today, formatdate
from frappe.utils.file_manager import save_file
import frappe

@frappe.whitelist()
def process_dummy_csv_and_create_updated_csv(invoices, document_type, scheduled_date):
    # Get file path from Accounts Settings
    file_path = frappe.db.get_value("Accounts Settings", "Accounts Settings", "payment_file")

    if "private" in file_path:
        file_path = frappe.get_site_path() + file_path
    else:
        file_path = frappe.get_site_path() + "/public" + file_path

    # Parse invoices
    if isinstance(invoices, str):
        invoices = json.loads(invoices)

    if not invoices:
        return frappe._("No invoices provided")

    # Read original CSV
    with open(file_path, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header_row_index = 3
    data_start_index = 4
    j_index = 9

    headers = reader[header_row_index][:j_index] + ["j_value"]

    processed_rows = reader[:header_row_index]  
    processed_rows.append(headers)
    
    date_obj = datetime.datetime.strptime(scheduled_date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%B %d, %Y")  
    processed_rows[1][4] = formatted_date

    grand_totals = []
    correct_data_only = True
    for row in range(300):
        reader.append(["","","","","","","","","",""])
    payment_process =[]
    for i, row in enumerate(reader[data_start_index:]):
        if i >= len(invoices):
            break

        invoice = invoices[i]
        if party_bank_account := frappe.db.get_value("Payment Entry", invoice, "party_bank_account"):
            bank_account = party_bank_account
        else:
            bank_account = frappe.db.exists("Bank Account", {
                "party_type": frappe.db.get_value("Payment Entry", invoice, "party_type"),
                "party": frappe.db.get_value("Payment Entry", invoice, "party"),
            })
            if not bank_account:
                continue

        bank_account = frappe.get_doc("Bank Account", bank_account)
        if not bank_account.branch_code:
            frappe.throw("Branch Code is missing in Bank Account Details {0}".format(get_link_to_form("Bank Account", bank_account.name)))
        if not bank_account.bank_account_no:
            frappe.throw("Account Number is missing in Bank Account Details {0}".format(get_link_to_form("Bank Account", bank_account.name)))
        if not bank_account.account_name:
            frappe.throw("Account Name is missing in Bank Account Details {0}".format(get_link_to_form("Bank Account", bank_account.name)))

        payment_amount = frappe.db.get_value("Payment Entry", invoice, "total_allocated_amount")

        if payment_amount < 200000:
            A = "NFT"
        elif bank_account.bank == "ICICI":
            A = "WIB"
        else:
            A = "RTG"
            
        B = "054105000849"
        C = bank_account.branch_code
        D = bank_account.bank_account_no
        E = re.sub(r'[^A-Za-z0-9 ]+', ' ', bank_account.account_name)
        F = payment_amount
        G = f"{invoice}"
        H = G

        # Validate and generate j_value
        try:
            valid = (
                A in ["WIB", "NFT", "RTG", "IFC"] and
                len(str(B)) == 12 and str(B).isdigit() and
                (
                    (A == "WIB" and not C) or
                    (A != "WIB" and len(C) == 11 and C[4] == "0")
                ) and
                (
                    (A == "WIB" and len(D) == 12 and str(D).isdigit()) or
                    (A != "WIB" and len(D) < 35)
                ) and
                isinstance(F, (int, float)) and len(str(round(F, 2))) < 16 and
                len(G) < 31 and
                (
                    (A == "WIB" and 6 <= sum(bool(x) for x in [A, B, C, D, E, F, G]) <= 7) or
                    (A != "WIB" and sum(bool(x) for x in [A, B, C, D, E, F, G]) == 7)
                )
            )
        except Exception as e:
            frappe.log_error("Validation error", e)
            valid = False

        if valid:
            j_value = "{}|{}|{}|INR|{}|0011|{}|{}|0011|{}|{}|{}^".format(
                "APW" if A == "WIB" else "APO",
                A,
                round(F, 2),
                B,
                "ICIC0000011" if A == "WIB" else C,
                D,
                E,
                G,
                H
            )
            grand_totals.append(round(F, 2))
        else:
            j_value = "Please correct data"
            correct_data_only = False

        updated_row = [
            A,
            B,
            C,
            D,
            E,
            round(F, 2),
            G,
            H,
            "",  # You can keep this or adjust as needed
            j_value
        ]
        processed_rows.append(updated_row)
        payment_process.append(invoice)
    
    if not payment_process:
        frappe.throw("Please validate the Bank details for selected payment entry")


    # Summary Row - J4
    sum_total = sum(grand_totals)
    count_valid = len(grand_totals)
    e1 = reader[0][4].strip() if len(reader[0]) > 4 else "000000000000"
    g1 = reader[0][6].strip() if len(reader[0]) > 6 else "REF001"
    e2 = scheduled_date
    if not (e1 and len(str(e1)) == 12):
        frappe.throw("1")
    if not (str(e1).isdigit()):
        frappe.throw("2")
    if not correct_data_only:
        frappe.throw("3")
    if not (g1 and len(str(g1)) < 11):
        frappe.throw("4")
    if not (len(str(sum_total)) < 16):
        frappe.throw("5")
    try:
        valid_j4 = (
            e1 and len(str(e1)) == 12 and str(e1).isdigit() and
            correct_data_only and
            getdate(e2) >= getdate(today()) and
            g1 and len(str(g1)) < 11 and
            len(str(sum_total)) < 16
        )
    except Exception as e:
        frappe.log_error("J4 Validation Error", e)
        valid_j4 = False

    j4_value = (
        f"FHR|0011|{e1}|INR|{sum_total}|{count_valid}|{formatdate(e2, 'mm/dd/yyyy')}|{g1}^"
        if valid_j4 else
        "Please correct data"
    )

    processed_rows[header_row_index] = processed_rows[header_row_index][:j_index] + [j4_value]

    # Save as CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(processed_rows)
    buffer = BytesIO(output.getvalue().encode())
    buffer.seek(0)

    file_naming = make_autoname(f"ASTERIPAY_ASTERIAUPLOAD_{str(getdate().strftime('%d%m%Y'))}.###")

    filename = f"{file_naming}.csv"

    saved_file = save_file(filename, buffer.read(), is_private=1, dt=None, dn=None)

    local_file_path = frappe.get_site_path() + saved_file.file_url

    upload_file(local_file_path)
    message = "Payment successfully transfer for bellow entries.<br>"

    for row in payment_process:
        frappe.db.set_value("Payment Entry", row, "h2h_transfered", 1)
        message += "<ul>"
        message += f"<li><b>{get_link_to_form('Payment Entry',row)}</b></li>"
        message += "</ul>"


    frappe.msgprint(frappe._(message))

    return {
        "file_url": saved_file.file_url,
        "file_name": saved_file.file_name
    }



def connect_sftp():
    cred_doc = frappe.get_doc("H2H Settings", "H2H Settings")
    SFTP_HOST = cred_doc.public_ip
    SFTP_PORT = cred_doc.port
    SFTP_PASSWORD = cred_doc.get_password("password")
    SFTP_USERNAME = cred_doc.username


    """Establish SFTP connection and return sftp client"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # <-- disables host key checking
    client.connect(
        hostname=SFTP_HOST,
        port=SFTP_PORT,
        username=SFTP_USERNAME,
        password=SFTP_PASSWORD,
        allow_agent=False,
        look_for_keys=False
    )
    sftp = client.open_sftp()
    return sftp, client
    return sftp, transport


def upload_file(local_file_path, remote_file_name=None):
    sftp, client = connect_sftp()
    UPLOAD_PATH = "/In"
    try:
        remote_path = f"{UPLOAD_PATH}/{remote_file_name or os.path.basename(local_file_path)}"
        sftp.put(local_file_path, remote_path)
        frappe.msgprint(f"Uploaded file to {remote_path}")
    finally:
        sftp.close()
        client.close()

def download_file(remote_file_name, local_download_dir):
    """Download a file from the SFTP server"""
    sftp, transport = connect_sftp()
    try:
        local_path = os.path.join(local_download_dir, remote_file_name)
        remote_path = f"{DOWNLOAD_PATH}/{remote_file_name}"
        sftp.get(remote_path, local_path)
        frappe.msgprint(f"Downloaded file to {local_path}")
    finally:
        sftp.close()
        transport.close()


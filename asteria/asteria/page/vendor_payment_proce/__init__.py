import frappe
from frappe.utils import getdate
from frappe import _
from openpyxl import load_workbook
import os
import json
from frappe.utils.file_manager import save_file
from frappe.utils import get_datetime
from io import BytesIO
from io import StringIO
import csv

@frappe.whitelist()
def get_vendor_payments(due_date):
    if not due_date:
        return []

    transaction_date = getdate(due_date)

    results = frappe.db.get_all("Purchase Invoice",
        filters={
            "due_date": due_date,
            "docstatus": 1
        },
        fields=["name as purchase_invoice_no", "supplier as supplier_name", "posting_date as date", "grand_total as amount"]
    )
    
    return {"data" : results}




import csv
import json
from io import StringIO, BytesIO
from frappe.utils import get_datetime, getdate, today, formatdate
from frappe.utils.file_manager import save_file
import frappe

@frappe.whitelist()
def process_dummy_csv_and_create_updated_csv(invoices):
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

    processed_rows = reader[:header_row_index]  # Preserve metadata (first 3 rows)
    processed_rows.append(headers)

    grand_totals = []
    correct_data_only = True
    for row in range(300):
        reader.append(["","","","","","","","","",""])
        
    for i, row in enumerate(reader[data_start_index:]):
        if i >= len(invoices):
            break

        invoice = invoices[i]
        supplier = frappe.db.get_value("Purchase Invoice", invoice, "supplier")
        if not supplier:
            continue

        bank_details = frappe.db.exists("Bank Account", {
            "party_type": "Supplier",
            "party": supplier
        })
        if not bank_details:
            continue

        bank_account = frappe.get_doc("Bank Account", bank_details)

        A = "NFT"
        B = "054105000849"
        C = bank_account.branch_code
        D = bank_account.bank_account_no
        E = bank_account.account_name
        F = frappe.db.get_value("Purchase Invoice", invoice, "grand_total")
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

    # Summary Row - J4
    sum_total = sum(grand_totals)
    count_valid = len(grand_totals)
    e1 = reader[0][4].strip() if len(reader[0]) > 4 else "000000000000"
    g1 = reader[0][6].strip() if len(reader[0]) > 6 else "REF001"
    e2 = reader[1][4].strip() if len(reader[1]) > 4 else formatdate(today())

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

    filename = f"Updated_Payment_{get_datetime().strftime('%Y%m%d_%H%M%S')}.csv"

    saved_file = save_file(filename, buffer.read(), is_private=0, dt=None, dn=None)

    return {
        "file_url": saved_file.file_url,
        "file_name": saved_file.file_name
    }


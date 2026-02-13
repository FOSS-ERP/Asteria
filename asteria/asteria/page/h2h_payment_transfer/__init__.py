import frappe
from frappe.utils import getdate, flt
from frappe import _
from openpyxl import load_workbook
import os
import json
from frappe.utils.file_manager import save_file
from frappe.utils import get_datetime, get_link_to_form, getdate, today, formatdate
from io import BytesIO
from io import StringIO
from frappe.model.naming import make_autoname
import csv
import re
import ast
import paramiko
from datetime import datetime
from erpnext.selling.report.address_and_contacts.address_and_contacts import get_party_addresses_and_contact

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
            and pe.paid_from_account_currency = 'INR' and pe.paid_to_account_currency = 'INR'
        """, as_dict = 1
    )
    duplicate_row = []
    for row in results:
        if row.payment_entry in duplicate_row:
            row.update({
                "is_exists" : 1
            })
        else:
            duplicate_row.append(row.payment_entry)

        row.update({
            "total_allocated_amount" : frappe.utils.fmt_money(row.total_allocated_amount, currency=row.currency),
        })

    return {"data" : results}


@frappe.whitelist()
def process_dummy_csv_and_create_updated_csv(invoices, document_type, scheduled_date):
    scheduled_date = datetime.strptime(scheduled_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    # Header rows
    header1 = [
        "Record Identifier", "Payment Indicator", "Unique Cust Ref No", "Vendor / Beneficiary Code",
        "Name of Beneficiary", "Instrument Amount", "Payment Date", "Cheque Number", "Debit Account No",
        "Beneficiary Bank A/c No", "Beneficiary Bank IFSC Code", "Beneficiary Bank Name",
        "Beneficiary Mailing Address 1", "Beneficiary Mailing Address 2", "Beneficiary Mailing Address 3",
        "Beneficiary City", "Beneficiary Zip", "Debit Narration", "Print Location", "Payable Location",
        "Fiscal Year", "Company Code", "Email id", "Beneficiary Mobile No", "AADHAR Number"
    ]

    header2 = [
        "Record Identifier", "Unique Cust Ref No", "Invoice No", "Invoice Date",
        "Gross Amount", "Deductions", "Net Amount"
    ]

    final_payment_data = []
    h2h_log = frappe.new_doc("H2H Log")
    total_paid_amount = 0
    for row in ast.literal_eval(invoices):
        # Fetch Bank Account
        pe_doc = frappe.get_doc("Payment Entry", row)
        total_paid_amount += pe_doc.paid_amount
        party_bank_account = frappe.db.get_value("Payment Entry", row, "party_bank_account")
        if not party_bank_account:
            bank_account = frappe.db.exists("Bank Account", {
                "party_type": frappe.db.get_value("Payment Entry", row, "party_type"),
                "party": frappe.db.get_value("Payment Entry", row, "party"),
            })
            if not bank_account:
                frappe.throw(frappe._("Bank Details are not available for {0}".format(
                    get_link_to_form(frappe.db.get_value("Payment Entry", row, "party_type"), frappe.db.get_value("Payment Entry", row, "party"))
                )))
        else:
            bank_account = pe_doc.party_bank_account

        bank_account = frappe.get_doc("Bank Account", bank_account)

        if not bank_account.bank_account_no:
            frappe.throw(f"Bank Account number is not available {get_link_to_form('Bank Account', bank_account.name)}, <br> <strong>Payment Entry : {get_link_to_form('Payment Entry', row)}</strong>")
        
        if not bank_account.branch_code:
            frappe.throw(f"Branch Code is not available {get_link_to_form('Bank Account', bank_account.name)}, <br> <strong>Payment Entry : {get_link_to_form('Payment Entry', row)}</strong>")
        
        

        # First row: "I" type
        data_row = ["I"]

        # Payment Indicator
        payment_amount = frappe.db.get_value("Payment Entry", row, "paid_amount")
        if bank_account.bank == "ICICI":
            data_row.append("I")
        elif payment_amount <= 200000:
            data_row.append("N")
        else:
            data_row.append("R")

        # Party info
        if document_type in ["Purchase Invoice", "Purchase Order"]:
            party_type = "Supplier"
            party_group = frappe.db.get_value("Supplier", pe_doc.party, "supplier_group")
        else:
            party_type = "Employee"
            party_group = "Employee"

        # Address & contact
        address_contact_details = get_address_contact_details(pe_doc.party, party_type)
        address = address_contact_details.get("address", {})
        contact = address_contact_details.get("contact", {})
        if document_type == "Expense Claim" and not contact:
            if email_id := frappe.db.get_value("Employee", pe_doc.party, "personal_email"):
                email_id = email_id
            elif email_id := frappe.db.get_value("Employee", pe_doc.party, "company_email"):
                email_id = email_id
            else:
                frappe.throw("Email Id is not available for Employee {0}".format(get_link_to_form(
                    "Employee", pe_doc.party
                )))
            if mobile_no := frappe.db.get_value("Employee", pe_doc.party, "cell_number"):
                mobile_no = mobile_no
            else:
                frappe.throw("Mobile No id not available for Employee {0}".format(get_link_to_form(
                    "Employee", pe_doc.party
                )))
            contact = {
                "mobile_no" : mobile_no,
                "email_id" : email_id 
            }

        if not contact:
            frappe.throw(f"Contact Details Not available for {get_link_to_form(party_type, pe_doc.party)}")

        if not address and document_type == "Expense Claim":
            city = frappe.db.get_value("Employee", pe_doc.party, "city")
            if not city:
                frappe.throw(f"City is not updated in Employee Master <b>{pe_doc.party}</b>")
            pincode = frappe.db.get_value("Employee", pe_doc.party, "pincode")
            if not pincode:
                frappe.throw(f"Pincode is not updated in Employee Master <b>{pe_doc.party}</b>")
            
            address = {
                "pincode" : pincode,
                "city" : city,
                "email_id" : contact.get("email_id") or email_id,
                "mobile_no" : contact.get("mobile_no") or mobile_no
            }
        if not address:
            frappe.throw(f"Address Details Not available for {get_link_to_form(party_type, pe_doc.party)}")
        
        email_id = (
            address.get("email_id")
            or contact.get("email_id")
            or (contact.get("email_ids")[0].email_id if contact.get("email_ids") else None)
        )

        phone = (
            address.get("phone")
            or contact.get("mobile_no")
            or contact.get("phone")
            or (contact.get("phone_nos")[0].phone if contact.get('phone_nos') else '')
        )

        if not email_id:
            frappe.throw(f"Email ID is not available for {get_link_to_form(party_type, pe_doc.party)}")
        if not phone:
            frappe.throw(f"Phone no is not available for {get_link_to_form(party_type, pe_doc.party)}")
        if not address.get("pincode"):
            frappe.throw(f"Pincode is missing in address details of supplier {get_link_to_form(party_type, pe_doc.party)}")
        

        # Identifier details
        details = [
            row, pe_doc.party, pe_doc.party_name, pe_doc.paid_amount,
            scheduled_date, "", str("054105000849"), bank_account.bank_account_no,
            bank_account.branch_code, bank_account.bank or '', email_id, '', '',
            address.get("city"), address.get("pincode"),'', '','', getdate().year,
            '', email_id, phone, ''
        ]

        data_row += details

        final_payment_data.append(data_row)
        
        # Second row(s): "A" type for each reference
        frappe.db.set_value("Payment Entry", pe_doc.name, "h2h_transfered", 1)
        for ad in pe_doc.references:
            data_row = ["A"]

            if document_type == 'Purchase Order':
                posting_date = frappe.db.get_value("Purchase Order", ad.reference_name, "transaction_date")
            elif document_type == 'Purchase Invoice':
                posting_date = frappe.db.get_value("Purchase Invoice", ad.reference_name, "posting_date")
            else:
                posting_date = frappe.db.get_value("Expense Claim", ad.reference_name, "posting_date")
            deduction = 0

            if (document_type == "Purchase Order" or document_type == 'Purchase Invoice'):
                purchase_doc = frappe.get_doc(document_type, ad.reference_name)
                for tax in purchase_doc.taxes:
                    if tax.get("is_tax_withholding_account"):
                        deduction = tax.tax_amount

            data_row += [
                ad.reference_name, ad.reference_name, getdate(posting_date).strftime("%d/%m/%Y"),
                ad.allocated_amount + deduction, deduction, ad.allocated_amount
            ]
            final_payment_data.append(data_row)


    # Get the site's public folder path
    site_path = frappe.get_site_path()
    public_path = os.path.join(site_path, 'public', 'files')
    
    # Create the files directory if it doesn't exist
    os.makedirs(public_path, exist_ok=True)
    
    file_naming = make_autoname(f"ASTERIAPAY_ASTERIAUPLOAD_{str(getdate().strftime('%d%m%Y'))}.###")
    filename = f"{file_naming}.csv"

    # Full file path
    file_path = os.path.join(public_path, filename)

    # Create and write to the CSV file
    with open(file_path, mode='w', newline='') as file:
        writer = csv.writer(file, delimiter='|')
        writer.writerow(header1)
        writer.writerow(header2)
        for row in final_payment_data:
            writer.writerow(row)
    
    # Create a File document in Frappe
    file_doc = frappe.get_doc({
        'doctype': 'File',
        'file_name': filename,
        'attached_to_doctype': None,
        'attached_to_name': None,
        'folder': 'Home/Attachments',
        'file_url': f'/files/{filename}',
        'is_private': 0  
    })

    h2h_log.transferred_csv_file = f"/files/{filename}"
    h2h_log.total_no_of_payments = len(final_payment_data) - len(ast.literal_eval(invoices))
    h2h_log.total_paid_amount = pe_doc.paid_amount
    h2h_log.log_type = "Upload"
    total_amount = 0
    for row in final_payment_data:
        if(row[0] == 'A'):
            continue

        pedoc = frappe.get_doc("Payment Entry", row[2])
        for d in pedoc.references:
            h2h_log.append("vendor_payment_processor", {
                "payment_entry" : pedoc.name,
                "document_type" : d.reference_doctype,
                "document" : d.reference_name,
                "due_date" : d.get("due_date"),
                "status" : "File Created",
                "amount" : d.allocated_amount
            })
            total_amount += flt(d.allocated_amount)

    h2h_log.total_paid_amount = total_amount  
    h2h_log.insert(ignore_permissions=True)
    
    file_doc.insert(ignore_permissions=True)
    upload_file(file_path)
    
    frappe.msgprint(f"CSV file created successfully at {file_path}")

import os
import frappe
import paramiko

UPLOAD_PATH = "/In"
DOWNLOAD_PATH = "/Out"   # ICICI usually provides /Out for downloads

import frappe
import paramiko

def connect_sftp():
    cred_doc = frappe.get_doc("H2H Settings", "H2H Settings")
    SFTP_HOST = cred_doc.public_ip or "host2host.icicibank.com"
    SFTP_PORT = int(cred_doc.port or 4446)
    SFTP_USERNAME = cred_doc.username
    SFTP_PASSWORD = cred_doc.get_password('password')  # assuming 'password' field is encrypted in Frappe

    """Establish SFTP connection and return sftp + ssh client"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Connect using username and password
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


def upload_file(local_file_path, remote_file_name=None):
    sftp, client = connect_sftp()
    try:
        remote_path = f"{UPLOAD_PATH}/{remote_file_name or os.path.basename(local_file_path)}"
        sftp.put(local_file_path, remote_path)
        frappe.msgprint(f"✅ Uploaded file to {remote_path}")
    finally:
        sftp.close()
        client.close()


def download_file(remote_file_name, local_download_dir):
    sftp, client = connect_sftp()
    try:
        local_path = os.path.join(local_download_dir, remote_file_name)
        remote_path = f"{DOWNLOAD_PATH}/{remote_file_name}"
        sftp.get(remote_path, local_path)
        frappe.msgprint(f"✅ Downloaded file to {local_path}")
    finally:
        sftp.close()
        client.close()


def get_address_contact_details(party, party_type):
    address = frappe.db.sql(
        f""" 
            Select ad.name
            From `tabAddress` as ad
            Left join `tabDynamic Link` as dl ON dl.parent=ad.name
            Where dl.link_name = "{party}" and dl.link_doctype = "{party_type}"
            LIMIT 1
        """, as_dict=1
    )
    if address:
        address = frappe.get_doc("Address", address[0].name)
    contact = frappe.db.sql(
        f"""
            Select co.name
            From `tabContact` as co
            Left Join `tabDynamic Link` as dl ON dl.parent=co.name
            Where dl.link_name = "{party}" and dl.link_doctype = "{party_type}"
            LIMIT 1
        """, as_dict=1
    )
    if contact:
        contact = frappe.get_doc("Contact", contact[0].name)

    return {
        "address" : address,
        "contact" : contact
    }
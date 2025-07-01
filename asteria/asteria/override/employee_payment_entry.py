import frappe
from hrms.overrides.employee_payment_entry import get_party_account, get_grand_total_and_outstanding_amount, get_paid_amount_and_received_amount
from erpnext.accounts.utils import get_account_currency
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    PaymentEntry,
    get_bank_cash_account,
    get_reference_details,
)
from frappe.utils import flt, nowdate

@frappe.whitelist()
def get_payment_entry_for_employee(dt, dn, party_amount=None, bank_account=None, bank_amount=None):
    """Function to make Payment Entry for Employee Advance, Gratuity, Expense Claim, Leave Encashment"""
    doc = frappe.get_doc(dt, dn)

    party_account = get_party_account(doc)
    party_account_currency = get_account_currency(party_account)
    payment_type = "Pay"
    grand_total, outstanding_amount = get_grand_total_and_outstanding_amount(
        doc, party_amount, party_account_currency
    )

    # bank or cash
    bank = get_bank_cash_account(doc, bank_account)

    paid_amount, received_amount = get_paid_amount_and_received_amount(
        doc, party_account_currency, bank, outstanding_amount, payment_type, bank_amount
    )

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = payment_type
    pe.company = doc.company
    pe.cost_center = doc.get("cost_center")
    pe.posting_date = nowdate()
    pe.mode_of_payment = doc.get("mode_of_payment")
    pe.party_type = "Employee"
    pe.party = doc.get("employee")
    pe.contact_person = doc.get("contact_person")
    pe.contact_email = doc.get("contact_email")
    pe.letter_head = doc.get("letter_head")
    pe.paid_from = bank.account
    pe.paid_to = party_account
    pe.paid_from_account_currency = bank.account_currency
    pe.paid_to_account_currency = party_account_currency
    pe.paid_amount = paid_amount
    pe.received_amount = received_amount
    pe.project = doc.get("project")
    pe.business_unit = doc.get("business_unit")

    pe.append(
        "references",
        {
            "reference_doctype": dt,
            "reference_name": dn,
            "bill_no": doc.get("bill_no"),
            "due_date": doc.get("due_date"),
            "total_amount": grand_total,
            "outstanding_amount": outstanding_amount,
            "allocated_amount": outstanding_amount,
        },
    )

    pe.setup_party_account_field()
    pe.set_missing_values()
    pe.set_missing_ref_details()

    if party_account and bank:
        reference_doc = None
        if dt == "Employee Advance":
            reference_doc = doc
        pe.set_exchange_rate(ref_doc=reference_doc)
        pe.set_amounts()

    return pe
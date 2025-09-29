import frappe
import json
from frappe import _
from frappe.utils import flt, nowdate, getdate
from frappe.utils.background_jobs import enqueue

from erpnext import get_company_currency
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)
from erpnext.accounts.doctype.payment_entry.payment_entry import (
	get_payment_entry,
)
from erpnext.accounts.doctype.payment_entry.payment_entry import (
	PaymentEntry,
	get_bank_cash_account,
	get_reference_details,
)
from erpnext.accounts.party import get_party_account, get_party_bank_account
from erpnext.accounts.utils import get_account_currency, get_currency_precision
from erpnext.utilities import payment_app_import_guard
from frappe.core.doctype.session_default_settings.session_default_settings import get_session_default_values

@frappe.whitelist()
def get_entries(document_type, due_date=None, from_date=None, to_date=None, supplier=None, orderby=None, employee=None):
	if not orderby or orderby == None or orderby == '':
		orderby = "DESC"

	condition = ''
	if employee:
		condition = f" and ec.employee = '{employee}'"
	if document_type == "Expense Claim":
		data = frappe.db.sql(f"""
				Select 
					ec.name as document_name, ec.grand_total, ec.posting_date, ec.expense_approver, ec.approval_status, ec.employee, ec.employee_name
				From 
					`tabExpense Claim` as ec
				Where (ec.workflow_state = 'Approved' or ec.approval_status = 'Approved') and ec.is_paid = 0 and ec.status != 'Paid' and ec.docstatus = 1 {condition} AND NOT EXISTS (
					SELECT name 
						FROM `tabPayment Entry Reference` per
						WHERE 
							per.reference_name = ec.name
							AND per.docstatus = 0
					)
				Order By ec.posting_date {orderby}
		""", as_dict=1)
		for row in data:
			row.update({
				"grand_total" : frappe.utils.fmt_money(row.grand_total, currency=row.currency),
			})
		return { "data" : data , "document_type" : document_type }
	
	filter = ''
	if due_date:
		filter += f" and pi.posting_date <= '{due_date}'"
	if from_date:
		filter += f" and pi.posting_date >= '{from_date}'"
	if to_date:
		filter += f" and pi.posting_date <= '{to_date}'"
	if supplier:
		filter += f" and pi.supplier = '{supplier}'"
	

	if document_type == "Purchase Invoice":		
		data = frappe.db.sql(f""" 
				Select pi.name as document_name, pi.grand_total, pi.supplier, pi.supplier_name, pi.posting_date, pi.status, pi.outstanding_amount, pi.currency, pi.due_date
				From `tabPurchase Invoice` as pi
				Where pi.docstatus = 1 and pi.status != 'Paid' and pi.is_return != 1 {filter} AND NOT EXISTS (
					SELECT per.name 
						FROM `tabPayment Entry Reference` per
						WHERE 
							per.reference_name = pi.name
							AND per.docstatus = 0
							
					)
				Order By pi.posting_date {orderby}
		""",as_dict=1)
		for row in data:
			row.update({
				"outstanding_amount" : frappe.utils.fmt_money(row.outstanding_amount, currency=row.currency),
				"grand_total" : frappe.utils.fmt_money(row.grand_total, currency=row.currency)
			})
		return { "data" : data , "document_type" : document_type }

	filter = ''
	if from_date:
		filter += f" and transaction_date >= '{from_date}'"
	if to_date:
		filter += f" and transaction_date <= '{to_date}'"

	if document_type == "Purchase Order":
		data = frappe.db.sql(f""" 
				Select po.name as document_name, po.grand_total, po.supplier, po.supplier_name, po.transaction_date as posting_date, po.status, po.advance_paid, po.currency
				From `tabPurchase Order` as po
				Where po.docstatus = 1 and po.status not in ('Completed', 'Closed') and po.grand_total > po.advance_paid and (po.grand_total - po.advance_paid) > 1 
				and po.per_billed = 0
				{filter} AND NOT EXISTS (
					SELECT per.name 
						FROM `tabPayment Entry Reference` per
						WHERE 
							per.reference_name = po.name
							AND per.docstatus = 0
					)
				Order By po.transaction_date {orderby}
		""",as_dict=1)
		for row in data:
			row.update({
				"grand_total" : frappe.utils.fmt_money(row.grand_total, currency=row.currency),
				"advance_paid" : frappe.utils.fmt_money(row.advance_paid, currency=row.currency)
			})

		return { "data" : data , "document_type" : document_type }


@frappe.whitelist()
def create_payment_entry_(document_type, invoices, bank_account):
	selected_invoices = json.loads(invoices)
	if document_type == "Purchase Order" or document_type == "Purchase Invoice":
		for row in selected_invoices:
			create_payment_entry(document_type, row, bank_account = bank_account)
	if document_type == 'Expense Claim':
		for row in selected_invoices:
			get_payment_entry_for_employee(document_type, row)
	return "Created"



def create_payment_entry(reference_doctype, reference_name, bank_account, submit=False):
	"""create entry"""
	frappe.flags.ignore_account_permission = True

	ref_doc = frappe.get_doc(reference_doctype, reference_name)

	if reference_doctype in ["Sales Invoice", "POS Invoice"]:
		party_account = ref_doc.debit_to
	elif reference_doctype == "Purchase Invoice":
		party_account = ref_doc.credit_to
	else:
		party_account = get_party_account("Customer", ref_doc.get("customer"), ref_doc.company)

	party_account_currency = (
		ref_doc.get("party_account_currency")
		or get_account_currency(party_account)
	)
	if reference_doctype == "Purchase Invoice":
		party_amount = bank_amount = ref_doc.outstanding_amount
	if reference_doctype == "Purchase Order":
		party_amount = bank_amount = ref_doc.grand_total - ref_doc.advance_paid

	if party_account_currency == ref_doc.company_currency and party_account_currency != ref_doc.currency:
		exchange_rate = ref_doc.get("conversion_rate")
		if reference_doctype == "Purchase Invoice":
			bank_amount = flt(ref_doc.outstanding_amount / exchange_rate, ref_doc.precision("grand_total"))
		if reference_doctype == "Purchase Order":
			bank_amount = flt((ref_doc.grand_total - ref_doc.advance_paid) / exchange_rate, ref_doc.precision("grand_total"))

	# outstanding amount is already in Part's account currency
	payment_entry = get_payment_entry(
		reference_doctype,
		reference_name,
		party_amount=party_amount,
		bank_account=bank_account,
		bank_amount=bank_amount,
		created_from_payment_request=True,
	)


	payment_entry.update(
		{
			"mode_of_payment": "Bank Draft",
			"reference_no": "Payment Run",  # to prevent validation error
			"reference_date": nowdate(),
			"remarks": "Payment Entry against {} {} via Payment Run".format(
				reference_doctype, reference_name
			),
			"business_unit" : ref_doc.get("business_unit"),
		}
	)

	# Update dimensions
	payment_entry.update(
		{
			"cost_center": ref_doc.get("cost_center"),
			"project": ref_doc.get("project"),
		}
	)

	# # Update 'Paid Amount' on Forex transactions
	# if self.currency != ref_doc.company_currency:
	# 	if (
	# 		payment_entry.paid_from_account_currency == ref_doc.company_currency
	# 		and payment_entry.paid_from_account_currency != payment_entry.paid_to_account_currency
	# 	):
	# 		payment_entry.paid_amount = payment_entry.base_paid_amount = (
	# 			payment_entry.target_exchange_rate * payment_entry.received_amount
	# 		)

	if reference_doctype in ("Purchase Invoice", "Purchase Order"):
		supplier = payment_entry.party
		party_bank_account = frappe.db.get_value("Bank Account", {
			'party_type' : "Supplier",
			'party' : supplier
		}, "name")
		if party_bank_account:
			payment_entry.party_bank_account = party_bank_account

	payment_entry.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.commit()

	return payment_entry



@frappe.whitelist()
def get_payment_entry_for_employee(dt, dn, party_amount=None, bank_account=None, bank_amount=None):
	from hrms.overrides.employee_payment_entry import (
		get_grand_total_and_outstanding_amount, 
		get_paid_amount_and_received_amount,
		get_party_account
	)
	session_default = get_session_default_values()

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
	pe.business_unit = doc.business_unit
	pe.cost_center = doc.cost_center
	pe.project = doc.project
	pe.paid_from_account_currency = bank.account_currency
	pe.paid_to_account_currency = party_account_currency
	pe.paid_amount = paid_amount
	pe.received_amount = received_amount

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

	pe.reference_no = "Waiting From Bank"
	pe.reference_date = getdate()
	pe.insert(ignore_mandatory=True, ignore_permissions=True)
	frappe.db.commit()
	return pe
# Copyright (c) 2026, Viral and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, today


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	return columns, data


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------

def get_data(filters):
	report_date = getdate(filters.get("to_date") or today())
	company = filters.get("company")

	# 1. PLE-based outstanding  –  single source of truth (matches Accounts Payable)
	outstanding_map = _get_outstanding_from_ple(filters)

	# 2. Purchase Invoices (exclude returns / debit notes)
	purchase_invoices = _get_purchase_invoices(filters)

	# 3. Journal Entries linked to Purchase Invoices (via reference_type)
	je_linked_map = _get_linked_journal_entries(company)

	# 4. Direct supplier Journal Entries (NOT linked to any PI)
	je_direct = _get_unlinked_journal_entries(filters)

	# 5. Tax breakdown per PI
	tax_map = _get_tax_details()

	# ------------------------------------------------------------------
	# Build final rows
	# ------------------------------------------------------------------
	data = []
	seen_pi = set()

	# -- Purchase Invoice rows  (one row per PI, no duplicates) --
	for pi in purchase_invoices:
		if pi.name in seen_pi:
			continue
		seen_pi.add(pi.name)

		# Outstanding from PLE (company currency)
		pi_outstanding = flt(
			outstanding_map.get(("Purchase Invoice", pi.name), 0), 2
		)

		# Paid = invoice amount – outstanding  (both in company currency)
		pi_paid = flt(pi.base_grand_total, 2) - pi_outstanding

		# Delay logic (based on report to_date, not today)
		is_delay = (
			pi_outstanding > 0
			and pi.due_date
			and getdate(pi.due_date) < report_date
		)

		# Payment-status filter
		if filters.get("payment_status") == "Delay" and not is_delay:
			continue
		if filters.get("payment_status") == "On Time" and is_delay:
			continue

		overdue_amount = pi_outstanding if is_delay else 0

		# Linked JE (first one)
		jv = ""
		jv_list = je_linked_map.get(pi.name) or []
		if jv_list:
			jv = list(set(jv_list))[0]

		taxes = tax_map.get(pi.name, {})

		data.append(
			_build_pi_row(
				pi, taxes, jv, is_delay,
				overdue_amount, pi_outstanding, pi_paid,
			)
		)

	# -- Journal Entry (Direct) rows --
	for je in je_direct:
		je_outstanding = flt(
			outstanding_map.get(("Journal Entry", je.journal_entry), 0), 2
		)
		je_invoice_amount = flt(je.credit, 2) - flt(je.debit, 2)
		je_paid = flt(je_invoice_amount, 2) - je_outstanding

		data.append({
			"Transaction Type": "Journal Entry (Direct)",
			"PINV Date": je.posting_date,
			"Purchase Invoice": None,
			"Purchase Invoice Status": None,
			"Supplier ID": je.supplier,
			"Supplier Name": je.supplier_name,

			"Purchase Receipt": None,
			"Purchase Receipt Date": None,

			"Due Date": None,
			"MSME": None,

			"Payment Delay in Days": None,
			"Payment Status": None,

			"Supplier Invoice No": je.bill_no,
			"Supplier Invoice Date": je.bill_date,

			"GST Category": None,
			"GST": None,

			"Amount (Credit)": flt(je.credit, 2) if je.credit > 0 else 0,
			"Amount (Debit)": flt(je.debit, 2) if je.debit > 0 else 0,

			"Invoice Amount": je_invoice_amount,
			"Paid Amount": je_paid,
			"Unpaid Amount": je_outstanding,
			"Overdue Amount": 0,

			"Payable Amount": flt(je.credit, 2) if je.credit > 0 else 0,
			"Receivable Amount": flt(je.debit, 2) if je.debit > 0 else 0,

			"Taxable Amount": 0,
			"CGST Amount": 0,
			"SGST Amount": 0,
			"IGST Amount": 0,
			"TDS Amount": 0,
			"TDS Account": None,

			"Currency": je.currency,
			"Journal Entry": je.journal_entry,
		})

	# Sort by date
	data.sort(
		key=lambda x: x.get("PINV Date") or getdate("1900-01-01")
	)
	return data


# ---------------------------------------------------------------------------
# PLE OUTSTANDING  –  the single source of truth
# ---------------------------------------------------------------------------
# The Accounts Payable report computes outstanding by summing PLE.amount
# (grouped by against_voucher_type + against_voucher_no) where:
#   • account_type = 'Payable'
#   • delinked       = 0
#   • posting_date  <= report_date
# We replicate that exact logic here so numbers always match.
# ---------------------------------------------------------------------------

def _get_outstanding_from_ple(filters):
	"""
	Return dict  { (against_voucher_type, against_voucher_no): outstanding }
	outstanding = SUM(ple.amount)  — positive means still owed.
	"""
	conditions = [
		"ple.delinked = 0",
		"ple.account_type = 'Payable'",
		"ple.party_type = 'Supplier'",
	]
	values = {}

	if filters.get("company"):
		conditions.append("ple.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("to_date"):
		conditions.append("ple.posting_date <= %(to_date)s")
		values["to_date"] = getdate(filters.get("to_date"))

	if filters.get("supplier"):
		conditions.append("ple.party = %(supplier)s")
		values["supplier"] = filters.get("supplier")

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			ple.against_voucher_type,
			ple.against_voucher_no,
			SUM(ple.amount) AS outstanding
		FROM `tabPayment Ledger Entry` ple
		WHERE {where}
		GROUP BY ple.against_voucher_type, ple.against_voucher_no
		""",
		values,
		as_dict=True,
	)

	result = {}
	for r in rows:
		result[(r.against_voucher_type, r.against_voucher_no)] = flt(r.outstanding, 2)
	return result


# ---------------------------------------------------------------------------
# PURCHASE INVOICES
# ---------------------------------------------------------------------------

def _get_purchase_invoices(filters):
	conditions = [
		"pi.docstatus = 1",
		"pi.is_return = 0",          # exclude return / debit-note invoices
	]
	values = {}

	if filters.get("company"):
		conditions.append("pi.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("from_date"):
		conditions.append("pi.posting_date >= %(from_date)s")
		values["from_date"] = getdate(filters.get("from_date"))

	if filters.get("to_date"):
		conditions.append("pi.posting_date <= %(to_date)s")
		values["to_date"] = getdate(filters.get("to_date"))

	if filters.get("supplier"):
		conditions.append("pi.supplier = %(supplier)s")
		values["supplier"] = filters.get("supplier")

	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			pi.name,
			pi.posting_date,
			pi.bill_no,
			pi.bill_date,
			pi.supplier,
			pi.supplier_name,
			pi.due_date,
			pi.base_net_total,
			pi.base_grand_total,
			pi.status,
			pi.currency,
			s.msme,
			s.gst_category,
			s.tax_id,
			pii.purchase_receipt,
			pr.posting_date AS purchase_receipt_date
		FROM `tabPurchase Invoice` pi
		LEFT JOIN `tabSupplier` s ON s.name = pi.supplier
		LEFT JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pii.purchase_receipt
		WHERE {where}
		GROUP BY pi.name
		""",
		values,
		as_dict=True,
	)


# ---------------------------------------------------------------------------
# JOURNAL ENTRIES  –  linked to Purchase Invoices
# ---------------------------------------------------------------------------

def _get_linked_journal_entries(company=None):
	conditions = [
		"je.docstatus = 1",
		"jea.reference_type = 'Purchase Invoice'",
		"je.is_system_generated = 0",
		"je.voucher_type != 'Exchange Gain Or Loss'",
	]
	values = {}

	if company:
		conditions.append("je.company = %(company)s")
		values["company"] = company

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			je.name   AS journal_entry,
			jea.reference_name AS purchase_invoice
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE {where}
		""",
		values,
		as_dict=True,
	)

	result = {}
	for r in rows:
		result.setdefault(r.purchase_invoice, []).append(r.journal_entry)
	return result


# ---------------------------------------------------------------------------
# JOURNAL ENTRIES  –  direct supplier transactions (no PI reference)
# ---------------------------------------------------------------------------

def _get_unlinked_journal_entries(filters):
	conditions = [
		"je.docstatus = 1",
		"jea.party_type = 'Supplier'",
		"IFNULL(jea.reference_type, '') = ''",    # handles both NULL and ''
		"IFNULL(jea.reference_name, '') = ''",
		"je.is_system_generated = 0",
		"je.voucher_type != 'Exchange Gain Or Loss'",
	]
	values = {}

	if filters.get("company"):
		conditions.append("je.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("from_date"):
		conditions.append("je.posting_date >= %(from_date)s")
		values["from_date"] = getdate(filters.get("from_date"))

	if filters.get("to_date"):
		conditions.append("je.posting_date <= %(to_date)s")
		values["to_date"] = getdate(filters.get("to_date"))

	if filters.get("supplier"):
		conditions.append("jea.party = %(supplier)s")
		values["supplier"] = filters.get("supplier")

	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			je.name AS journal_entry,
			je.posting_date,
			je.cheque_no  AS bill_no,
			je.cheque_date AS bill_date,
			jea.party      AS supplier,
			jea.party      AS supplier_name,
			jea.debit,
			jea.credit,
			jea.account_currency AS currency,
			je.voucher_type
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE {where}
		GROUP BY je.name, jea.name
		""",
		values,
		as_dict=True,
	)


# ---------------------------------------------------------------------------
# TAX BREAKDOWN  (per Purchase Invoice)
# ---------------------------------------------------------------------------

def _get_tax_details():
	rows = frappe.db.sql(
		"""
		SELECT
			parent,
			SUM(CASE WHEN account_head LIKE '%%CGST%%'
				THEN base_tax_amount_after_discount_amount ELSE 0 END) AS cgst,
			SUM(CASE WHEN account_head LIKE '%%SGST%%'
				THEN base_tax_amount_after_discount_amount ELSE 0 END) AS sgst,
			SUM(CASE WHEN account_head LIKE '%%IGST%%'
				THEN base_tax_amount_after_discount_amount ELSE 0 END) AS igst,
			SUM(CASE WHEN account_head LIKE '%%TDS%%'
				THEN base_tax_amount_after_discount_amount ELSE 0 END) AS tds,
			GROUP_CONCAT(DISTINCT CASE WHEN account_head LIKE '%%TDS%%'
				THEN account_head END) AS tds_account
		FROM `tabPurchase Taxes and Charges`
		GROUP BY parent
		""",
		as_dict=True,
	)
	return {t.parent: t for t in rows}


# ---------------------------------------------------------------------------
# ROW BUILDER  –  Purchase Invoice
# ---------------------------------------------------------------------------

def _build_pi_row(pi, taxes, jv, is_delay, overdue_amount, pi_outstanding, pi_paid):
	"""Build one report row for a Purchase Invoice.  One row per PI."""
	return {
		"Transaction Type": "Purchase Invoice",
		"PINV Date": pi.posting_date,
		"Purchase Invoice": pi.name,
		"Purchase Invoice Status": pi.status,
		"Supplier ID": pi.supplier,
		"Supplier Name": pi.supplier_name,

		"Purchase Receipt": pi.purchase_receipt,
		"Purchase Receipt Date": pi.purchase_receipt_date,

		"Due Date": pi.due_date,
		"MSME": pi.msme,

		"Payment Delay in Days": None,
		"Payment Status": "Delay" if is_delay else "On Time",

		"Supplier Invoice No": pi.bill_no,
		"Supplier Invoice Date": pi.bill_date,

		"GST Category": pi.gst_category,
		"GST": pi.tax_id,

		"Amount (Credit)": flt(pi.base_grand_total, 2),
		"Amount (Debit)": flt(pi_paid, 2),

		"Invoice Amount": flt(pi.base_grand_total, 2),
		"Paid Amount": flt(pi_paid, 2),
		"Unpaid Amount": pi_outstanding,
		"Overdue Amount": overdue_amount,

		"Payable Amount": flt(pi_paid, 2) if pi_paid > 0 else 0,
		"Receivable Amount": 0,

		"Taxable Amount": flt(pi.base_net_total, 2),
		"CGST Amount": flt(taxes.get("cgst", 0), 2),
		"SGST Amount": flt(taxes.get("sgst", 0), 2),
		"IGST Amount": flt(taxes.get("igst", 0), 2),
		"TDS Amount": flt(taxes.get("tds", 0), 2),
		"TDS Account": taxes.get("tds_account"),

		"Currency": pi.currency,
		"Journal Entry": jv,
	}


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns():
	return [
		{"label": "Transaction Type", "fieldname": "Transaction Type",
		 "fieldtype": "Data", "width": 150},

		{"label": "PINV Date", "fieldname": "PINV Date",
		 "fieldtype": "Date", "width": 100},

		{"label": "Purchase Invoice", "fieldname": "Purchase Invoice",
		 "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},

		{"label": "Purchase Invoice Status", "fieldname": "Purchase Invoice Status",
		 "fieldtype": "Data", "width": 120},

		{"label": "Supplier ID", "fieldname": "Supplier ID",
		 "fieldtype": "Link", "options": "Supplier", "width": 120},

		{"label": "Supplier Name", "fieldname": "Supplier Name",
		 "fieldtype": "Data", "width": 150},

		{"label": "Purchase Receipt", "fieldname": "Purchase Receipt",
		 "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},

		{"label": "Purchase Receipt Date", "fieldname": "Purchase Receipt Date",
		 "fieldtype": "Date", "width": 120},

		{"label": "Journal Entry", "fieldname": "Journal Entry",
		 "fieldtype": "Link", "options": "Journal Entry", "width": 150},

		{"label": "Due Date", "fieldname": "Due Date",
		 "fieldtype": "Date", "width": 100},

		{"label": "MSME", "fieldname": "MSME",
		 "fieldtype": "Select", "width": 80},

		{"label": "Payment Delay in Days", "fieldname": "Payment Delay in Days",
		 "fieldtype": "Int", "width": 100},

		{"label": "Payment Status", "fieldname": "Payment Status",
		 "fieldtype": "Select", "options": "On Time\nDelay", "width": 100},

		{"label": "Supplier Invoice No", "fieldname": "Supplier Invoice No",
		 "fieldtype": "Data", "width": 120},

		{"label": "Supplier Invoice Date", "fieldname": "Supplier Invoice Date",
		 "fieldtype": "Date", "width": 120},

		{"label": "GST Category", "fieldname": "GST Category",
		 "fieldtype": "Select", "width": 100},

		{"label": "GST", "fieldname": "GST",
		 "fieldtype": "Data", "width": 120},

		# Credit / Debit
		{"label": "Amount (Credit)", "fieldname": "Amount (Credit)",
		 "fieldtype": "Currency", "width": 130},

		{"label": "Amount (Debit)", "fieldname": "Amount (Debit)",
		 "fieldtype": "Currency", "width": 130},

		# Original amount columns
		{"label": "Invoice Amount", "fieldname": "Invoice Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "Paid Amount", "fieldname": "Paid Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "Unpaid Amount", "fieldname": "Unpaid Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "Overdue Amount", "fieldname": "Overdue Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "Payable Amount", "fieldname": "Payable Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "Receivable Amount", "fieldname": "Receivable Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "Taxable Amount", "fieldname": "Taxable Amount",
		 "fieldtype": "Currency", "width": 120},

		{"label": "CGST Amount", "fieldname": "CGST Amount",
		 "fieldtype": "Currency", "width": 100},

		{"label": "SGST Amount", "fieldname": "SGST Amount",
		 "fieldtype": "Currency", "width": 100},

		{"label": "IGST Amount", "fieldname": "IGST Amount",
		 "fieldtype": "Currency", "width": 100},

		{"label": "TDS Amount", "fieldname": "TDS Amount",
		 "fieldtype": "Currency", "width": 100},

		{"label": "TDS Account", "fieldname": "TDS Account",
		 "fieldtype": "Data", "width": 120},

		{"label": "Currency", "fieldname": "Currency",
		 "fieldtype": "Data", "width": 80},
	]

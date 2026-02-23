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

	# 1. GL Entry debit/credit – matches General Ledger report
	gl_map = _get_gl_debit_credit_by_voucher(filters)

	# 2. PLE-based outstanding – matches Accounts Payable report
	outstanding_map = _get_outstanding_from_ple(filters)

	# 3. Purchase Invoices (exclude returns / debit notes)
	purchase_invoices = _get_purchase_invoices(filters)

	# 3. Journal Entries linked to Purchase Invoices (as separate rows, each with own debit/credit)
	je_linked_list = _get_linked_journal_entries_data(filters)

	# 4. Direct supplier Journal Entries (NOT linked to any PI)
	je_direct = _get_unlinked_journal_entries(filters)

	# 5. Get linked PO/PR to exclude them (avoid duplicates)
	linked_po_set, linked_pr_set = _get_linked_po_pr(purchase_invoices)

	# 6. Purchase Orders (only standalone, not linked to PI)
	purchase_orders = _get_purchase_orders(filters, exclude_list=linked_po_set)

	# 7. Purchase Receipts (only standalone, not linked to PI)
	purchase_receipts = _get_purchase_receipts(filters, exclude_list=linked_pr_set)

	# 8. Payment Entries (advances) – from outstanding_map to match Accounts Payable
	payment_entries = _get_payment_entries_from_outstanding(filters, outstanding_map)

	# 9. Tax breakdown per PI
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

		# Outstanding from PLE (matches Accounts Payable)
		pi_outstanding = flt(
			outstanding_map.get(("Purchase Invoice", pi.name), 0), 2
		)

		# Credit/Debit from GL Entry (matches General Ledger)
		gl_pi = gl_map.get(("Purchase Invoice", pi.name), {})
		pi_credit = gl_pi.get("credit") or 0
		pi_debit = gl_pi.get("debit") or 0
		# Ensure Credit - Debit = Outstanding. Use GL credit; derive debit from outstanding.
		if pi_credit:
			pi_debit = flt(pi_credit - pi_outstanding, 2)
		else:
			# Fallback: no GL entry (e.g. old data)
			pi_credit = flt(pi.base_grand_total, 2)
			pi_debit = flt(pi_credit - pi_outstanding, 2)
		pi_paid = pi_debit

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

		# Calculate delay days
		delay_days = None
		if is_delay and pi.due_date:
			delay_days = (report_date - getdate(pi.due_date)).days

		taxes = tax_map.get(pi.name, {})

		# Invoice amount: from GL credit (matches General Ledger). Fallback: base_grand_total + TDS
		if pi_credit:
			invoice_amount = pi_credit
		else:
			tds_from_taxes = flt(taxes.get("tds", 0), 2)
			invoice_amount = flt(pi.base_grand_total, 2) + tds_from_taxes

		data.append(
			_build_pi_row(
				pi, taxes, is_delay,
				overdue_amount, pi_outstanding, pi_paid, delay_days,
				invoice_amount, pi_credit, pi_debit,
			)
		)

	# -- Journal Entry (Linked to PI) rows – use GL for debit/credit (matches General Ledger) --
	for je in je_linked_list:
		je_outstanding = flt(
			outstanding_map.get(("Journal Entry", je.journal_entry), 0), 2
		)
		gl_je = gl_map.get(("Journal Entry", je.journal_entry), {})
		je_credit = gl_je.get("credit") or flt(je.credit, 2) or 0
		je_debit = gl_je.get("debit") or flt(je.debit, 2) or 0
		# JV can be invoice (credit) or payment (debit). Paid = net - outstanding
		je_net = je_credit - je_debit
		je_paid = flt(je_net - je_outstanding, 2)

		data.append(_build_je_linked_row(je, je_credit, je_debit, je_outstanding, je_paid))

	# Aggregate je_direct by journal_entry (query returns one row per jea)
	je_direct_agg = {}
	for je in je_direct:
		key = je.journal_entry
		if key not in je_direct_agg:
			je_direct_agg[key] = frappe._dict(je)
			je_direct_agg[key].debit = flt(je.debit, 2)
			je_direct_agg[key].credit = flt(je.credit, 2)
		else:
			je_direct_agg[key].debit += flt(je.debit, 2)
			je_direct_agg[key].credit += flt(je.credit, 2)
	je_direct = list(je_direct_agg.values())

	# Get TDS for all direct JVs in one query
	je_direct_names = [je.journal_entry for je in je_direct]
	je_direct_tds_map = {}
	if je_direct_names:
		in_placeholders = ", ".join(["%s"] * len(je_direct_names))
		tds_rows = frappe.db.sql(
			f"""
			SELECT jea.parent AS journal_entry,
				SUM(jea.credit) AS tds_amount,
				GROUP_CONCAT(jea.account) AS tds_account
			FROM `tabJournal Entry Account` jea
			WHERE jea.parent IN ({in_placeholders})
				AND (jea.is_tax_withholding_account = 1 OR jea.account LIKE %s)
			GROUP BY jea.parent
			""",
			tuple(je_direct_names) + ("%TDS%",),
			as_dict=True,
		)
		je_direct_tds_map = {x.journal_entry: x for x in tds_rows}

	# -- Journal Entry (Direct) rows – use GL for debit/credit (matches General Ledger) --
	for je in je_direct:
		je_outstanding = flt(
			outstanding_map.get(("Journal Entry", je.journal_entry), 0), 2
		)
		gl_je = gl_map.get(("Journal Entry", je.journal_entry), {})
		je_credit = gl_je.get("credit") or flt(je.credit, 2) or 0
		je_debit = gl_je.get("debit") or flt(je.debit, 2) or 0
		# JV can be invoice (credit) or payment (debit). Paid = net - outstanding
		je_net = je_credit - je_debit
		je_paid = flt(je_net - je_outstanding, 2)

		tds_info = je_direct_tds_map.get(je.journal_entry, {})
		je_tds = flt(tds_info.get("tds_amount"), 2) if tds_info else 0
		je_tds_account = tds_info.get("tds_account") if tds_info else None

		data.append(_build_je_direct_row(je, je_credit, je_debit, je_outstanding, je_paid, je_tds, je_tds_account))

	# -- Purchase Order rows – use GL if available (PO rarely has GL), else document amount --
	for po in purchase_orders:
		po_outstanding = flt(
			outstanding_map.get(("Purchase Order", po.name), 0), 2
		)
		gl_po = gl_map.get(("Purchase Order", po.name), {})
		po_credit = gl_po.get("credit") or flt(po.base_grand_total, 2)
		po_debit = gl_po.get("debit") or 0
		if po_credit:
			po_debit = flt(po_credit - po_outstanding, 2)
		po_paid = po_debit

		data.append({
			"Transaction Type": "Purchase Order",
			"PINV Date": po.transaction_date,
			"Purchase Invoice Status": po.status,
			"Supplier ID": po.supplier,
			"Supplier Name": po.supplier_name,
			"Purchase Receipt Date": None,
			"Due Date": None,
			"MSME": po.msme,
			"Payment Delay in Days": None,
			"Payment Status": None,
			"Supplier Invoice No": None,
			"Supplier Invoice Date": None,
			"GST Category": po.gst_category,
			"GST": po.tax_id,
			"Amount (Credit)": po_credit,
			"Amount (Debit)": po_debit,
			"Invoice Amount": po_credit,
			"Paid Amount": po_paid,
			"Unpaid Amount": po_outstanding,
			"Overdue Amount": 0,
			"Payable Amount": po_paid if po_paid > 0 else 0,
			"Receivable Amount": 0,
			"Taxable Amount": flt(po.base_net_total, 2),
			"CGST Amount": 0,
			"SGST Amount": 0,
			"IGST Amount": 0,
			"TDS Amount": 0,
			"TDS Account": None,
			"Currency": po.currency,
			"Reference": po.name,
			"Credit Amount": po_credit,
			"Debit Amount": po_debit,
			"Outstanding Amount": po_outstanding,
		})

	# -- Purchase Receipt rows – use GL if available (PR rarely has GL), else document amount --
	for pr in purchase_receipts:
		pr_outstanding = flt(
			outstanding_map.get(("Purchase Receipt", pr.name), 0), 2
		)
		gl_pr = gl_map.get(("Purchase Receipt", pr.name), {})
		pr_credit = gl_pr.get("credit") or flt(pr.base_grand_total, 2)
		pr_debit = gl_pr.get("debit") or 0
		if pr_credit:
			pr_debit = flt(pr_credit - pr_outstanding, 2)
		pr_paid = pr_debit

		data.append({
			"Transaction Type": "Purchase Receipt",
			"PINV Date": pr.posting_date,
			"Purchase Invoice Status": pr.status,
			"Supplier ID": pr.supplier,
			"Supplier Name": pr.supplier_name,
			"Purchase Receipt Date": pr.posting_date,
			"Due Date": None,
			"MSME": pr.msme,
			"Payment Delay in Days": None,
			"Payment Status": None,
			"Supplier Invoice No": None,
			"Supplier Invoice Date": None,
			"GST Category": pr.gst_category,
			"GST": pr.tax_id,
			"Amount (Credit)": pr_credit,
			"Amount (Debit)": pr_debit,
			"Invoice Amount": pr_credit,
			"Paid Amount": pr_paid,
			"Unpaid Amount": pr_outstanding,
			"Overdue Amount": 0,
			"Payable Amount": pr_paid if pr_paid > 0 else 0,
			"Receivable Amount": 0,
			"Taxable Amount": flt(pr.base_net_total, 2),
			"CGST Amount": 0,
			"SGST Amount": 0,
			"IGST Amount": 0,
			"TDS Amount": 0,
			"TDS Account": None,
			"Currency": pr.currency,
			"Reference": pr.name,
			"Credit Amount": pr_credit,
			"Debit Amount": pr_debit,
			"Outstanding Amount": pr_outstanding,
		})

	# -- Payment Entry rows (advances) – from outstanding_map to match Accounts Payable --
	for pe in payment_entries:
		pe_outstanding = flt(
			outstanding_map.get(("Payment Entry", pe.name), 0), 2
		)
		gl_pe = gl_map.get(("Payment Entry", pe.name), {})
		pe_credit = gl_pe.get("credit") or 0
		pe_debit = gl_pe.get("debit") or flt(pe.base_paid_amount, 2)
		# For advance: outstanding is negative. Debit = paid
		if pe_outstanding:
			pe_debit = flt(pe_credit - pe_outstanding, 2)
		elif not pe_debit:
			pe_debit = flt(pe.base_paid_amount, 2)
		pe_paid = pe_debit

		data.append({
			"Transaction Type": "Payment Entry",
			"PINV Date": pe.posting_date,
			"Purchase Invoice Status": None,
			"Supplier ID": pe.supplier,
			"Supplier Name": pe.supplier_name,
			"Purchase Receipt Date": None,
			"Due Date": None,
			"MSME": pe.msme,
			"Payment Delay in Days": None,
			"Payment Status": None,
			"Supplier Invoice No": pe.bill_no,
			"Supplier Invoice Date": pe.bill_date,
			"GST Category": pe.gst_category,
			"GST": pe.tax_id,
			"Amount (Credit)": pe_credit,
			"Amount (Debit)": pe_debit,
			"Invoice Amount": pe_credit - pe_debit,
			"Paid Amount": pe_paid,
			"Unpaid Amount": pe_outstanding,
			"Overdue Amount": 0,
			"Payable Amount": 0,
			"Receivable Amount": abs(pe_outstanding) if pe_outstanding < 0 else 0,
			"Taxable Amount": 0,
			"CGST Amount": 0,
			"SGST Amount": 0,
			"IGST Amount": 0,
			"TDS Amount": 0,
			"TDS Account": None,
			"Currency": pe.currency,
			"Reference": pe.name,
			"Credit Amount": pe_credit,
			"Debit Amount": pe_debit,
			"Outstanding Amount": pe_outstanding,
		})

	# Sort by date
	data.sort(
		key=lambda x: x.get("PINV Date") or getdate("1900-01-01")
	)
	return data


# ---------------------------------------------------------------------------
# GL ENTRY  –  debit/credit to match General Ledger
# ---------------------------------------------------------------------------
# General Ledger shows debit and credit from GL Entry. For supplier (Payable)
# accounts: Credit = invoiced, Debit = paid. We sum GL Entry debit/credit
# per voucher where party_type='Supplier' to match General Ledger report.
# ---------------------------------------------------------------------------

def _get_gl_debit_credit_by_voucher(filters):
	"""
	Return dict { (voucher_type, voucher_no): {'debit': x, 'credit': y} }
	from GL Entry where party_type='Supplier'. Matches General Ledger report.
	"""
	conditions = [
		"gle.is_cancelled = 0",
		"gle.party_type = 'Supplier'",
		"gle.party IS NOT NULL",
		"gle.party != ''",
	]
	values = {}

	if filters.get("company"):
		conditions.append("gle.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("from_date"):
		conditions.append("gle.posting_date >= %(from_date)s")
		values["from_date"] = getdate(filters.get("from_date"))

	if filters.get("to_date"):
		conditions.append("gle.posting_date <= %(to_date)s")
		values["to_date"] = getdate(filters.get("to_date"))

	if filters.get("supplier"):
		conditions.append("gle.party = %(supplier)s")
		values["supplier"] = filters.get("supplier")

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			gle.voucher_type,
			gle.voucher_no,
			SUM(gle.debit) AS debit,
			SUM(gle.credit) AS credit
		FROM `tabGL Entry` gle
		WHERE {where}
		GROUP BY gle.voucher_type, gle.voucher_no
		""",
		values,
		as_dict=True,
	)

	return {(r.voucher_type, r.voucher_no): {"debit": flt(r.debit, 2), "credit": flt(r.credit, 2)} for r in rows}


# ---------------------------------------------------------------------------
# PLE OUTSTANDING  –  single source of truth (matches Accounts Payable)
# ---------------------------------------------------------------------------
# The Accounts Payable report computes outstanding by summing PLE.amount
# (grouped by against_voucher_type + against_voucher_no + party) where:
#   • account_type = 'Payable'
#   • delinked       = 0
#   • posting_date  <= report_date
# We replicate that exact logic here so numbers always match.
# ---------------------------------------------------------------------------

def _get_outstanding_from_ple(filters):
	"""
	Return dict  { (voucher_type, voucher_no): outstanding }
	outstanding = SUM(ple.amount) where ple is linked to the voucher
	This matches the Accounts Payable report calculation.
	The Accounts Payable report sums all PLE amounts for a voucher by looking at
	both entries where voucher = against_voucher (invoice) and where they differ (payments).
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

	# Calculate outstanding by summing all PLE amounts for each voucher
	# This matches Accounts Payable: outstanding = SUM(ple.amount) for all entries
	# where the voucher appears as either voucher or against_voucher
	rows = frappe.db.sql(
		f"""
		SELECT
			ple.against_voucher_type AS voucher_type,
			ple.against_voucher_no AS voucher_no,
			SUM(ple.amount) AS outstanding
		FROM `tabPayment Ledger Entry` ple
		WHERE {where}
			AND ple.against_voucher_type IS NOT NULL
			AND ple.against_voucher_no IS NOT NULL
		GROUP BY ple.against_voucher_type, ple.against_voucher_no, ple.party
		""",
		values,
		as_dict=True,
	)

	result = {}
	for r in rows:
		key = (r.voucher_type, r.voucher_no)
		# For same voucher with different parties, sum them
		if key in result:
			result[key] += flt(r.outstanding, 2)
		else:
			result[key] = flt(r.outstanding, 2)
	
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
# JOURNAL ENTRIES  –  linked to Purchase Invoices (full details for separate rows)
# ---------------------------------------------------------------------------

def _get_linked_journal_entries_data(filters):
	"""
	Get JVs linked to Purchase Invoices with full debit/credit details.
	Each JV gets its own row (journal ledger style). Also fetches TDS if JV has TDS deduction.
	"""
	conditions = [
		"je.docstatus = 1",
		"jea.reference_type = 'Purchase Invoice'",
		"jea.reference_name IS NOT NULL",
		"jea.reference_name != ''",
		"jea.party_type = 'Supplier'",
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

	rows = frappe.db.sql(
		f"""
		SELECT
			je.name AS journal_entry,
			je.posting_date,
			je.cheque_no AS bill_no,
			je.cheque_date AS bill_date,
			jea.reference_name,
			jea.party AS supplier,
			jea.debit,
			jea.credit,
			jea.account_currency AS currency,
			je.voucher_type
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE {where}
			AND jea.party_type = 'Supplier'
			AND jea.reference_type = 'Purchase Invoice'
		""",
		values,
		as_dict=True,
	)

	# Aggregate by JV and get TDS
	je_names = list(set(r.journal_entry for r in rows))
	tds_map = {}
	if je_names:
		in_placeholders = ", ".join(["%s"] * len(je_names))
		tds_rows = frappe.db.sql(
			f"""
			SELECT jea.parent AS journal_entry,
				SUM(jea.credit) AS tds_amount,
				GROUP_CONCAT(jea.account) AS tds_account
			FROM `tabJournal Entry Account` jea
			WHERE jea.parent IN ({in_placeholders})
				AND (jea.is_tax_withholding_account = 1 OR jea.account LIKE %s)
			GROUP BY jea.parent
			""",
			tuple(je_names) + ("%TDS%",),
			as_dict=True,
		)
		tds_map = {x.journal_entry: x for x in tds_rows}

	result = []
	seen_je = {}

	for r in rows:
		if r.journal_entry in seen_je:
			idx = seen_je[r.journal_entry]
			result[idx].debit = flt(result[idx].debit, 2) + flt(r.debit, 2)
			result[idx].credit = flt(result[idx].credit, 2) + flt(r.credit, 2)
			continue
		seen_je[r.journal_entry] = len(result)
		tds_info = tds_map.get(r.journal_entry, {})
		r.tds_amount = flt(tds_info.get("tds_amount"), 2) if tds_info else 0
		r.tds_account = tds_info.get("tds_account") if tds_info else None
		result.append(r)

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
# GET LINKED PO/PR (to exclude from separate rows)
# ---------------------------------------------------------------------------

def _get_linked_po_pr(purchase_invoices):
	"""Get sets of PO and PR names that are linked to Purchase Invoices"""
	linked_po_set = set()
	linked_pr_set = set()
	
	if not purchase_invoices:
		return linked_po_set, linked_pr_set
	
	pi_names = [pi.name for pi in purchase_invoices]
	
	# Get Purchase Orders linked via Purchase Invoice Items
	po_list = frappe.db.sql(
		"""
		SELECT DISTINCT pii.purchase_order
		FROM `tabPurchase Invoice Item` pii
		WHERE pii.parent IN (%s)
			AND pii.purchase_order IS NOT NULL
			AND pii.purchase_order != ''
		""" % ", ".join(["%s"] * len(pi_names)),
		tuple(pi_names),
		as_dict=True,
	)
	linked_po_set = {po.purchase_order for po in po_list if po.purchase_order}
	
	# Get Purchase Receipts linked via Purchase Invoice Items
	pr_list = frappe.db.sql(
		"""
		SELECT DISTINCT pii.purchase_receipt
		FROM `tabPurchase Invoice Item` pii
		WHERE pii.parent IN (%s)
			AND pii.purchase_receipt IS NOT NULL
			AND pii.purchase_receipt != ''
		""" % ", ".join(["%s"] * len(pi_names)),
		tuple(pi_names),
		as_dict=True,
	)
	linked_pr_set = {pr.purchase_receipt for pr in pr_list if pr.purchase_receipt}
	
	return linked_po_set, linked_pr_set


# ---------------------------------------------------------------------------
# PAYMENT ENTRIES (advances) – from PLE outstanding_map
# ---------------------------------------------------------------------------

def _get_payment_entries_from_outstanding(filters, outstanding_map):
	"""
	Get Payment Entry details for vouchers in outstanding_map with voucher_type='Payment Entry'.
	These are advance payments that reduce total payable (negative outstanding).
	"""
	pe_names = [
		voucher_no
		for (voucher_type, voucher_no) in outstanding_map
		if voucher_type == "Payment Entry"
	]
	if not pe_names:
		return []

	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Pay'",
		"pe.party_type = 'Supplier'",
	]
	values = []
	placeholders = ", ".join(["%s"] * len(pe_names))
	conditions.append(f"pe.name IN ({placeholders})")
	values.extend(pe_names)

	if filters.get("company"):
		conditions.append("pe.company = %s")
		values.append(filters.get("company"))

	# No date filter - include all PEs from outstanding_map (matches AP report scope)
	if filters.get("supplier"):
		conditions.append("pe.party = %s")
		values.append(filters.get("supplier"))

	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			pe.name,
			pe.posting_date,
			pe.party AS supplier,
			pe.party_name AS supplier_name,
			pe.base_paid_amount,
			pe.paid_amount,
			pe.paid_from_account_currency AS currency,
			pe.reference_no AS bill_no,
			pe.reference_date AS bill_date,
			s.msme,
			s.gst_category,
			s.tax_id
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabSupplier` s ON s.name = pe.party
		WHERE {where}
		""",
		values,
		as_dict=True,
	)


# ---------------------------------------------------------------------------
# PURCHASE ORDERS
# ---------------------------------------------------------------------------

def _get_purchase_orders(filters, exclude_list=None):
	conditions = []
	values = []

	if filters.get("company"):
		conditions.append("po.company = %s")
		values.append(filters.get("company"))

	if filters.get("from_date"):
		conditions.append("po.transaction_date >= %s")
		values.append(getdate(filters.get("from_date")))

	if filters.get("to_date"):
		conditions.append("po.transaction_date <= %s")
		values.append(getdate(filters.get("to_date")))

	if filters.get("supplier"):
		conditions.append("po.supplier = %s")
		values.append(filters.get("supplier"))

	# Always add docstatus condition
	conditions.insert(0, "po.docstatus = 1")

	# Build query with exclude list if provided
	if exclude_list and exclude_list:
		placeholders = ", ".join(["%s"] * len(exclude_list))
		conditions.append(f"po.name NOT IN ({placeholders})")
		values.extend(list(exclude_list))

	where = " AND ".join(conditions)

	query = f"""
		SELECT
			po.name,
			po.transaction_date,
			po.supplier,
			po.supplier_name,
			po.base_net_total,
			po.base_grand_total,
			po.status,
			po.currency,
			s.msme,
			s.gst_category,
			s.tax_id
		FROM `tabPurchase Order` po
		LEFT JOIN `tabSupplier` s ON s.name = po.supplier
		WHERE {where}
		GROUP BY po.name
	"""
	
	return frappe.db.sql(query, tuple(values), as_dict=True)


# ---------------------------------------------------------------------------
# PURCHASE RECEIPTS
# ---------------------------------------------------------------------------

def _get_purchase_receipts(filters, exclude_list=None):
	conditions = []
	values = []

	if filters.get("company"):
		conditions.append("pr.company = %s")
		values.append(filters.get("company"))

	if filters.get("from_date"):
		conditions.append("pr.posting_date >= %s")
		values.append(getdate(filters.get("from_date")))

	if filters.get("to_date"):
		conditions.append("pr.posting_date <= %s")
		values.append(getdate(filters.get("to_date")))

	if filters.get("supplier"):
		conditions.append("pr.supplier = %s")
		values.append(filters.get("supplier"))

	# Always add docstatus and is_return conditions
	conditions.insert(0, "pr.docstatus = 1")
	conditions.insert(1, "pr.is_return = 0")

	# Build query with exclude list if provided
	if exclude_list and exclude_list:
		placeholders = ", ".join(["%s"] * len(exclude_list))
		conditions.append(f"pr.name NOT IN ({placeholders})")
		values.extend(list(exclude_list))

	where = " AND ".join(conditions)

	query = f"""
		SELECT
			pr.name,
			pr.posting_date,
			pr.supplier,
			pr.supplier_name,
			pr.base_net_total,
			pr.base_grand_total,
			pr.status,
			pr.currency,
			s.msme,
			s.gst_category,
			s.tax_id
		FROM `tabPurchase Receipt` pr
		LEFT JOIN `tabSupplier` s ON s.name = pr.supplier
		WHERE {where}
		GROUP BY pr.name
	"""
	
	return frappe.db.sql(query, tuple(values), as_dict=True)


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

def _build_pi_row(pi, taxes, is_delay, overdue_amount, pi_outstanding, pi_paid, delay_days, invoice_amount, pi_credit, pi_debit):
	"""Build one report row for a Purchase Invoice. Credit/Debit from GL, Outstanding from PLE."""
	tds_amount = flt(taxes.get("tds", 0), 2)
	return {
		"Transaction Type": "Purchase Invoice",
		"PINV Date": pi.posting_date,
		"Purchase Invoice Status": pi.status,
		"Supplier ID": pi.supplier,
		"Supplier Name": pi.supplier_name,

		"Purchase Receipt Date": pi.purchase_receipt_date,

		"Due Date": pi.due_date,
		"MSME": pi.msme,

		"Payment Delay in Days": delay_days,
		"Payment Status": "Delay" if is_delay else "On Time",

		"Supplier Invoice No": pi.bill_no,
		"Supplier Invoice Date": pi.bill_date,

		"GST Category": pi.gst_category,
		"GST": pi.tax_id,

		# From GL Entry (matches General Ledger). Credit - Debit = Outstanding (from PLE)
		"Amount (Credit)": flt(pi_credit, 2),
		"Amount (Debit)": flt(pi_debit, 2),

		"Invoice Amount": flt(invoice_amount, 2),
		"Paid Amount": flt(pi_paid, 2),
		"Unpaid Amount": pi_outstanding,
		"Overdue Amount": overdue_amount,

		"Payable Amount": flt(pi_paid, 2) if pi_paid > 0 else 0,
		"Receivable Amount": 0,

		"Taxable Amount": flt(pi.base_net_total, 2),
		"CGST Amount": flt(taxes.get("cgst", 0), 2),
		"SGST Amount": flt(taxes.get("sgst", 0), 2),
		"IGST Amount": flt(taxes.get("igst", 0), 2),
		"TDS Amount": tds_amount,
		"TDS Account": taxes.get("tds_account"),

		"Currency": pi.currency,

		"Reference": pi.name,
		"Credit Amount": flt(pi_credit, 2),
		"Debit Amount": flt(pi_debit, 2),
		"Outstanding Amount": pi_outstanding,
	}


# ---------------------------------------------------------------------------
# ROW BUILDER  –  Journal Entry (Linked to PI)
# ---------------------------------------------------------------------------

def _build_je_linked_row(je, je_credit, je_debit, je_outstanding, je_paid):
	"""Build one report row for JV linked to PI. Journal ledger style - JV reduces amount (debit)."""
	return {
		"Transaction Type": "Journal Entry (Linked)",
		"PINV Date": je.posting_date,
		"Purchase Invoice Status": None,
		"Supplier ID": je.supplier,
		"Supplier Name": je.supplier_name or je.supplier,

		"Purchase Receipt Date": None,

		"Due Date": None,
		"MSME": None,

		"Payment Delay in Days": None,
		"Payment Status": None,

		"Supplier Invoice No": je.bill_no,
		"Supplier Invoice Date": je.bill_date,

		"GST Category": None,
		"GST": None,

		# Journal ledger: Credit/Debit from JV
		"Amount (Credit)": je_credit,
		"Amount (Debit)": je_debit,

		"Invoice Amount": je_credit - je_debit,
		"Paid Amount": je_paid,
		"Unpaid Amount": je_outstanding,
		"Overdue Amount": 0,

		"Payable Amount": je_credit if je_credit > 0 else 0,
		"Receivable Amount": je_debit if je_debit > 0 else 0,

		"Taxable Amount": 0,
		"CGST Amount": 0,
		"SGST Amount": 0,
		"IGST Amount": 0,
		"TDS Amount": flt(je.tds_amount, 2) if getattr(je, "tds_amount", None) else 0,
		"TDS Account": getattr(je, "tds_account", None),

		"Currency": je.currency,

		"Reference": je.journal_entry,
		"Credit Amount": je_credit,
		"Debit Amount": je_debit,
		"Outstanding Amount": je_outstanding,
	}


# ---------------------------------------------------------------------------
# ROW BUILDER  –  Journal Entry (Direct)
# ---------------------------------------------------------------------------

def _build_je_direct_row(je, je_credit, je_debit, je_outstanding, je_paid, je_tds, je_tds_account):
	"""Build one report row for direct JV. Journal ledger style."""
	return {
		"Transaction Type": "Journal Entry (Direct)",
		"PINV Date": je.posting_date,
		"Purchase Invoice Status": None,
		"Supplier ID": je.supplier,
		"Supplier Name": je.supplier_name,

		"Purchase Receipt Date": None,

		"Due Date": None,
		"MSME": None,

		"Payment Delay in Days": None,
		"Payment Status": None,

		"Supplier Invoice No": je.bill_no,
		"Supplier Invoice Date": je.bill_date,

		"GST Category": None,
		"GST": None,

		"Amount (Credit)": je_credit,
		"Amount (Debit)": je_debit,

		"Invoice Amount": je_credit - je_debit,
		"Paid Amount": je_paid,
		"Unpaid Amount": je_outstanding,
		"Overdue Amount": 0,

		"Payable Amount": je_credit if je_credit > 0 else 0,
		"Receivable Amount": je_debit if je_debit > 0 else 0,

		"Taxable Amount": 0,
		"CGST Amount": 0,
		"SGST Amount": 0,
		"IGST Amount": 0,
		"TDS Amount": je_tds,
		"TDS Account": je_tds_account,

		"Currency": je.currency,

		"Reference": je.journal_entry,
		"Credit Amount": je_credit,
		"Debit Amount": je_debit,
		"Outstanding Amount": je_outstanding,
	}


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns():
	return [
		{"label": "Transaction Type", "fieldname": "Transaction Type",
		 "fieldtype": "Data", "width": 150},

		{"label": "Reference", "fieldname": "Reference",
		 "fieldtype": "Data", "width": 180},

		{"label": "PINV Date", "fieldname": "PINV Date",
		 "fieldtype": "Date", "width": 100},

		{"label": "Purchase Invoice Status", "fieldname": "Purchase Invoice Status",
		 "fieldtype": "Data", "width": 120},

		{"label": "Supplier ID", "fieldname": "Supplier ID",
		 "fieldtype": "Link", "options": "Supplier", "width": 120},

		{"label": "Supplier Name", "fieldname": "Supplier Name",
		 "fieldtype": "Data", "width": 150},

		{"label": "Purchase Receipt Date", "fieldname": "Purchase Receipt Date",
		 "fieldtype": "Date", "width": 120},

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

		{"label": "Credit Amount", "fieldname": "Credit Amount",
		 "fieldtype": "Currency", "width": 130},

		{"label": "Debit Amount", "fieldname": "Debit Amount",
		 "fieldtype": "Currency", "width": 130},

		{"label": "Outstanding Amount", "fieldname": "Outstanding Amount",
		 "fieldtype": "Currency", "width": 130},
	]

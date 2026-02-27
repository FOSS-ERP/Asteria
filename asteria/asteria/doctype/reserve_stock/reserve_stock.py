# Copyright (c) 2026, Viral and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt


class ReserveStock(Document):
	def validate(self):
		validate_child_row_warehouses(self)
		validate_batch_reservation_availability(self)

	def before_submit(self):
		# Default row status to "Reserved" if not explicitly set
		for row in getattr(self, "items", []) or []:
			if not cstr(row.get("status")).strip():
				row.status = "Reserved"

		validate_batch_reservation_availability(self)

	def on_update_after_submit(self):
		# Re-validate whenever a submitted Reserve Stock is edited (e.g. row status changed)
		validate_child_row_warehouses(self)
		validate_batch_reservation_availability(self)


def validate_child_row_warehouses(doc):
	"""Warehouse is mandatory in every Stock Reservation Items row."""
	for row in getattr(doc, "items", []) or []:
		warehouse = cstr(row.get("warehouse")).strip()
		if not warehouse:
			frappe.throw(
				_("Row #{0}: Please select Warehouse.").format(row.idx),
				title=_("Warehouse Required"),
			)


def get_reserved_stock_references(serial_nos=None, batch_nos=None):
	"""Return reserved serial and batch references from Reserve Stock doctype."""
	serial_nos = [s for s in (serial_nos or []) if s]
	batch_nos = [b for b in (batch_nos or []) if b]

	reserved_serial_refs = {}
	reserved_batch_refs = {}

	if serial_nos:
		serial_rows = frappe.db.sql(
			"""
			SELECT sri.serial_no, rs.name
			FROM `tabStock Reservation Items` AS sri
			INNER JOIN `tabReserve Stock` AS rs ON rs.name = sri.parent
			WHERE
				sri.parenttype = 'Reserve Stock'
				AND rs.docstatus = 1
				AND sri.status = 'Reserved'
				AND sri.serial_no IN %(serial_nos)s
			""",
			{"serial_nos": tuple(serial_nos)},
			as_dict=True,
		)
		reserved_serial_refs = {row.serial_no: row.name for row in serial_rows}

	if batch_nos:
		batch_rows = frappe.db.sql(
			"""
			SELECT sri.batch_no, rs.name
			FROM `tabStock Reservation Items` AS sri
			INNER JOIN `tabReserve Stock` AS rs ON rs.name = sri.parent
			WHERE
				sri.parenttype = 'Reserve Stock'
				AND rs.docstatus = 1
				AND sri.status = 'Reserved'
				AND sri.batch_no IN %(batch_nos)s
			""",
			{"batch_nos": tuple(batch_nos)},
			as_dict=True,
		)
		reserved_batch_refs = {row.batch_no: row.name for row in batch_rows}

	return {"serial_no": reserved_serial_refs, "batch_no": reserved_batch_refs}


def get_reserved_batch_details(batch_nos=None, warehouses=None, item_code=None, exclude_reserve_stock=None):
	"""Return reserved qty and reserve stock references keyed by (batch_no, warehouse)."""
	batch_nos = [cstr(v).strip() for v in (batch_nos or []) if cstr(v).strip()]
	warehouses = [cstr(v).strip() for v in (warehouses or []) if cstr(v).strip()]

	conditions = [
		"sri.parenttype = 'Reserve Stock'",
		"sri.status = 'Reserved'",
		"rs.docstatus = 1",
		"sri.batch_no IS NOT NULL",
		"sri.batch_no != ''",
		"sri.warehouse IS NOT NULL",
		"sri.warehouse != ''",
	]
	values = {}

	if batch_nos:
		conditions.append("sri.batch_no IN %(batch_nos)s")
		values["batch_nos"] = tuple(set(batch_nos))

	if warehouses:
		conditions.append("sri.warehouse IN %(warehouses)s")
		values["warehouses"] = tuple(set(warehouses))

	if item_code:
		conditions.append("sri.item_code = %(item_code)s")
		values["item_code"] = item_code

	if exclude_reserve_stock:
		conditions.append("rs.name != %(exclude_reserve_stock)s")
		values["exclude_reserve_stock"] = exclude_reserve_stock

	rows = frappe.db.sql(
		f"""
		SELECT
			sri.batch_no,
			sri.warehouse,
			SUM(ABS(IFNULL(sri.qty, 0))) AS reserved_qty,
			GROUP_CONCAT(DISTINCT rs.name) AS reserve_stocks
		FROM `tabStock Reservation Items` AS sri
		INNER JOIN `tabReserve Stock` AS rs ON rs.name = sri.parent
		WHERE {" AND ".join(conditions)}
		GROUP BY sri.batch_no, sri.warehouse
		""",
		values,
		as_dict=True,
	)

	reserved_batch_details = {}
	for row in rows:
		key = (cstr(row.batch_no).strip(), cstr(row.warehouse).strip())
		reserved_batch_details[key] = {
			"reserved_qty": flt(row.reserved_qty),
			"reserve_stocks": [name for name in cstr(row.reserve_stocks).split(",") if name],
		}

	return reserved_batch_details


@frappe.whitelist()
def get_batch_qty_in_warehouse(batch_no, warehouse, item_code=None):
	"""Return batch qty so it matches Stock Ledger / Batch Balance report.

	Includes both:
	1. Legacy SLE rows (batch_no set directly on SLE)
	2. SBB-based rows (batch in Serial and Batch Entry, SLE has serial_and_batch_bundle)

	ERPNext's get_batch_qty uses only the SBB join and can undercount when some
	stock was received without Serial and Batch Bundle.
	"""
	values = {"batch_no": batch_no, "warehouse": warehouse}
	item_filter = "AND sle.item_code = %(item_code)s" if item_code else ""
	if item_code:
		values["item_code"] = item_code

	# 1. Legacy: SLE with batch_no (no SBB or SBB empty)
	qty_legacy = frappe.db.sql(
		f"""
		SELECT IFNULL(SUM(sle.actual_qty), 0)
		FROM `tabStock Ledger Entry` sle
		WHERE sle.batch_no = %(batch_no)s
		  AND sle.warehouse = %(warehouse)s
		  AND sle.is_cancelled = 0
		  AND (sle.serial_and_batch_bundle IS NULL OR sle.serial_and_batch_bundle = '')
		  {item_filter}
		""",
		values,
	)
	legacy = flt(qty_legacy[0][0]) if qty_legacy else 0

	# 2. SBB-based: batch qty from Serial and Batch Entry (SLE has SBB, no batch_no on SLE)
	qty_sbb = frappe.db.sql(
		f"""
		SELECT IFNULL(SUM(sbe.qty), 0)
		FROM `tabSerial and Batch Entry` sbe
		INNER JOIN `tabSerial and Batch Bundle` sbb ON sbe.parent = sbb.name
		INNER JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
		WHERE sbe.batch_no = %(batch_no)s
		  AND sbe.warehouse = %(warehouse)s
		  AND sle.is_cancelled = 0
		  AND sbb.docstatus = 1
		  AND (sle.batch_no IS NULL OR sle.batch_no = '')
		  {item_filter}
		""",
		values,
	)
	sbb = flt(qty_sbb[0][0]) if qty_sbb else 0

	return legacy + sbb


@frappe.whitelist()
def get_available_warehouses_for_reserve_row(item_code=None, serial_no=None, batch_no=None):
	"""Return list of warehouses where the given serial / batch currently has stock.

	- If serial_no is provided: return its current warehouse (if any and Active).
	- If batch_no is provided: return all warehouses where that batch has positive qty,
	  combining both legacy SLE rows and SBB-based rows.
	"""
	item_code = cstr(item_code).strip() or None
	serial_no = cstr(serial_no).strip() or None
	batch_no = cstr(batch_no).strip() or None

	warehouses = set()

	# 1) Serial No current warehouse
	if serial_no:
		serial_wh = frappe.db.get_value(
			"Serial No",
			{"name": serial_no, "status": "Active"},
			"warehouse",
		)
		if serial_wh:
			warehouses.add(cstr(serial_wh).strip())

	# 2) Batch-wise warehouses with positive qty
	if batch_no:
		values = {"batch_no": batch_no}
		item_filter = ""
		if item_code:
			item_filter = "AND sle.item_code = %(item_code)s"
			values["item_code"] = item_code

		# 2a) Legacy SLE rows with batch_no directly on SLE
		legacy_rows = frappe.db.sql(
			f"""
			SELECT sle.warehouse, SUM(sle.actual_qty) AS qty
			FROM `tabStock Ledger Entry` sle
			WHERE sle.batch_no = %(batch_no)s
			  AND sle.is_cancelled = 0
			  {item_filter}
			GROUP BY sle.warehouse
			HAVING SUM(sle.actual_qty) > 0
			""",
			values,
			as_dict=True,
		)
		for row in legacy_rows:
			if row.warehouse:
				warehouses.add(cstr(row.warehouse).strip())

		# 2b) SBB-based rows where SLE links to Serial and Batch Bundle
		sbb_rows = frappe.db.sql(
			f"""
			SELECT sbe.warehouse, SUM(sbe.qty) AS qty
			FROM `tabSerial and Batch Entry` AS sbe
			INNER JOIN `tabSerial and Batch Bundle` AS sbb ON sbe.parent = sbb.name
			INNER JOIN `tabStock Ledger Entry` AS sle ON sle.serial_and_batch_bundle = sbb.name
			WHERE sbe.batch_no = %(batch_no)s
			  AND sle.is_cancelled = 0
			  AND sbb.docstatus = 1
			  {item_filter}
			GROUP BY sbe.warehouse
			HAVING SUM(sbe.qty) > 0
			""",
			values,
			as_dict=True,
		)
		for row in sbb_rows:
			if row.warehouse:
				warehouses.add(cstr(row.warehouse).strip())

	if not warehouses:
		return []

	# Return sorted unique list
	return sorted(warehouses)


def validate_batch_reservation_availability(doc):
	"""Ensure requested reserved qty is available in selected warehouse for each batch."""
	requested_by_key = {}
	for row in getattr(doc, "items", []) or []:
		# Only validate rows that are (or will be) reserved
		status = cstr(row.get("status")).strip() or "Reserved"
		if status != "Reserved":
			continue

		batch_no = cstr(row.get("batch_no")).strip()
		warehouse = cstr(row.get("warehouse")).strip()
		if not batch_no:
			continue
		if not warehouse:
			frappe.throw(
				_("Row #{0}: Please select Warehouse for batch {1}.").format(
					row.idx,
					frappe.bold(batch_no),
				)
			)

		reserved_qty = flt(row.get("qty"))
		if reserved_qty <= 0:
			frappe.throw(
				_("Row #{0}: Reserved qty must be greater than 0 for batch {1}.").format(
					row.idx,
					frappe.bold(batch_no),
				)
			)

		key = (batch_no, warehouse)
		requested_by_key[key] = requested_by_key.get(key, 0) + reserved_qty

	if not requested_by_key:
		return

	reserved_other = get_reserved_batch_details(
		batch_nos=[k[0] for k in requested_by_key],
		warehouses=[k[1] for k in requested_by_key],
		exclude_reserve_stock=doc.name,
	)

	for (batch_no, warehouse), requested_qty in requested_by_key.items():
		current_qty = get_batch_qty_in_warehouse(batch_no, warehouse)
		already_reserved_qty = flt(reserved_other.get((batch_no, warehouse), {}).get("reserved_qty"))
		available_to_reserve = current_qty - already_reserved_qty

		if requested_qty > available_to_reserve:
			frappe.throw(
				_(
					"Cannot reserve {0} qty for batch {1} in warehouse {2}.<br>"
					"Available to reserve: {3} (Current stock: {4}, Already reserved: {5})."
				).format(
					frappe.bold(requested_qty),
					frappe.bold(batch_no),
					frappe.bold(warehouse),
					frappe.bold(flt(available_to_reserve)),
					frappe.bold(flt(current_qty)),
					frappe.bold(flt(already_reserved_qty)),
				),
				title=_("Insufficient Batch Qty"),
			)


@frappe.whitelist()
def mark_as_unreserved(name: str):
	"""Mark submitted Reserve Stock rows as Unreserved from form button."""
	doc = frappe.get_doc("Reserve Stock", name)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Unreserve is allowed only for submitted Reserve Stock documents."))

	has_reserved_rows = False
	for row in getattr(doc, "items", []) or []:
		if cstr(row.get("status")).strip() != "Unreserved":
			has_reserved_rows = True
			frappe.db.set_value("Stock Reservation Items", row.name, "status", "Unreserved")

	if not has_reserved_rows:
		return {"status": "Unreserved"}

	return {"status": "Unreserved"}

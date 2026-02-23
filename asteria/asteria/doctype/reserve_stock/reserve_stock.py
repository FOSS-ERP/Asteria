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
		if not self.status:
			self.status = "Reserved"
		validate_batch_reservation_availability(self)


def validate_child_row_warehouses(doc):
	"""Warehouse is mandatory in every Serial and Batch Entry row."""
	for row in doc.table_zbqd:
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
			SELECT sbe.serial_no, rs.name
			FROM `tabSerial and Batch Entry` AS sbe
			INNER JOIN `tabReserve Stock` AS rs ON rs.name = sbe.parent
			WHERE
				sbe.parenttype = 'Reserve Stock'
				AND rs.status = 'Reserved'
				AND sbe.serial_no IN %(serial_nos)s
			""",
			{"serial_nos": tuple(serial_nos)},
			as_dict=True,
		)
		reserved_serial_refs = {row.serial_no: row.name for row in serial_rows}

	if batch_nos:
		batch_rows = frappe.db.sql(
			"""
			SELECT sbe.batch_no, rs.name
			FROM `tabSerial and Batch Entry` AS sbe
			INNER JOIN `tabReserve Stock` AS rs ON rs.name = sbe.parent
			WHERE
				sbe.parenttype = 'Reserve Stock'
				AND rs.status = 'Reserved'
				AND sbe.batch_no IN %(batch_nos)s
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
		"sbe.parenttype = 'Reserve Stock'",
		"rs.status = 'Reserved'",
		"rs.docstatus = 1",
		"sbe.batch_no IS NOT NULL",
		"sbe.batch_no != ''",
		"sbe.warehouse IS NOT NULL",
		"sbe.warehouse != ''",
	]
	values = {}

	if batch_nos:
		conditions.append("sbe.batch_no IN %(batch_nos)s")
		values["batch_nos"] = tuple(set(batch_nos))

	if warehouses:
		conditions.append("sbe.warehouse IN %(warehouses)s")
		values["warehouses"] = tuple(set(warehouses))

	if item_code:
		conditions.append("rs.item_code = %(item_code)s")
		values["item_code"] = item_code

	if exclude_reserve_stock:
		conditions.append("rs.name != %(exclude_reserve_stock)s")
		values["exclude_reserve_stock"] = exclude_reserve_stock

	rows = frappe.db.sql(
		f"""
		SELECT
			sbe.batch_no,
			sbe.warehouse,
			SUM(ABS(IFNULL(sbe.qty, 0))) AS reserved_qty,
			GROUP_CONCAT(DISTINCT rs.name) AS reserve_stocks
		FROM `tabSerial and Batch Entry` AS sbe
		INNER JOIN `tabReserve Stock` AS rs ON rs.name = sbe.parent
		WHERE {" AND ".join(conditions)}
		GROUP BY sbe.batch_no, sbe.warehouse
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


def get_batch_qty_in_warehouse(batch_no, warehouse, item_code=None):
	conditions = ["batch_no = %(batch_no)s", "warehouse = %(warehouse)s", "is_cancelled = 0"]
	values = {"batch_no": batch_no, "warehouse": warehouse}

	if item_code:
		conditions.append("item_code = %(item_code)s")
		values["item_code"] = item_code

	qty = frappe.db.sql(
		f"""
		SELECT IFNULL(SUM(actual_qty), 0) AS qty
		FROM `tabStock Ledger Entry`
		WHERE {" AND ".join(conditions)}
		""",
		values,
	)
	batch_balance = flt(qty[0][0]) if qty else 0

	# Fallback for old serial/batch fields flow: balance may be available at item+warehouse level
	# before batch-ledger rows are created during submit.
	if item_code and batch_balance <= 0:
		bin_qty = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"actual_qty",
		)
		if bin_qty is not None:
			return flt(bin_qty)

	return batch_balance


def validate_batch_reservation_availability(doc):
	"""Ensure requested reserved qty is available in selected warehouse for each batch."""
	if cstr(doc.status).strip() == "Unreserved":
		return

	requested_by_key = {}
	for row in doc.table_zbqd:
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
		item_code=doc.item_code,
		exclude_reserve_stock=doc.name,
	)

	for (batch_no, warehouse), requested_qty in requested_by_key.items():
		current_qty = get_batch_qty_in_warehouse(batch_no, warehouse, doc.item_code)
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
	"""Mark submitted Reserve Stock as Unreserved from form button."""
	doc = frappe.get_doc("Reserve Stock", name)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Unreserve is allowed only for submitted Reserve Stock documents."))

	if doc.status == "Unreserved":
		return {"status": doc.status}

	doc.db_set("status", "Unreserved", update_modified=True)
	return {"status": "Unreserved"}

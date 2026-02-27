import frappe
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	get_auto_batch_nos,
	get_reserved_serial_nos,
	get_serial_nos_based_on_posting_date,
	get_non_expired_batches,
	get_serial_nos_based_on_filters
)
from frappe.utils import parse_json, cint, cstr, flt, get_link_to_form
from frappe import _
from asteria.asteria.doctype.reserve_stock.reserve_stock import (
	get_batch_qty_in_warehouse,
	get_reserved_batch_details,
	get_reserved_stock_references,
)


@frappe.whitelist()
def get_auto_data(**kwargs):
	kwargs = frappe._dict(kwargs)
	if cint(kwargs.has_serial_no):
		return get_available_serial_nos(kwargs)

	elif cint(kwargs.has_batch_no):
		return get_auto_batch_nos(kwargs)


def get_available_batches_for_manufacture(kwargs):
	"""Fetch batch numbers from the same work order cycle (Material Transfer for Manufacture).
	If batch B1 was transferred for manufacturing, B1 will be auto-selected.
	Only batches that currently have stock in the WIP warehouse are returned."""
	
	# Check if batch validation is enabled in Stock Settings
	# if not frappe.db.get_single_value("Stock Settings", "enable_batch_validation_for_manufacture", 0):
	# 	return get_auto_batch_nos(kwargs)
	
	if kwargs.get("doc"):
		try:
			doc = frappe._dict(parse_json(kwargs.doc))
		except Exception:
			doc = kwargs.doc

		# Handle both dict and document object
		doctype = doc.get("doctype") if hasattr(doc, "get") else getattr(doc, "doctype", None)
		stock_entry_type = doc.get("stock_entry_type") if hasattr(doc, "get") else getattr(doc, "stock_entry_type", None)
		work_order = doc.get("work_order") if hasattr(doc, "get") else getattr(doc, "work_order", None)

		if doctype == "Stock Entry" and stock_entry_type == "Manufacture" and work_order:
			# Get WIP warehouse from Work Order
			wip_warehouse = frappe.db.get_value("Work Order", work_order, "wip_warehouse")
			if not wip_warehouse:
				return get_auto_batch_nos(kwargs)

			material_transfer_entries = frappe.get_all(
				"Stock Entry",
				{
					"stock_entry_type": "Material Transfer for Manufacture",
					"work_order": work_order,
					"docstatus": 1,
				},
				pluck="name",
			)

			if material_transfer_entries:
				entry_list = ", ".join([f'"{e}"' for e in material_transfer_entries])

				conditions = f" AND sbb.voucher_no IN ({entry_list})"
				sql_params = {}
				if kwargs.item_code:
					# Use parameterized query to prevent SQL injection
					conditions += " AND sbb.item_code = %(item_code)s"
					sql_params["item_code"] = kwargs.item_code

				# Fetch batches from Serial and Batch Bundle entries
				sql_query = f"""
					SELECT
						sbe.batch_no,
						SUM(ABS(sbe.qty)) as qty,
						sbe.warehouse
					FROM `tabSerial and Batch Bundle` AS sbb
					LEFT JOIN `tabSerial and Batch Entry` AS sbe ON sbe.parent = sbb.name
					WHERE
						sbb.docstatus = 1
						AND sbe.batch_no IS NOT NULL
						AND sbb.has_batch_no = 1
						{conditions}
					GROUP BY sbe.batch_no, sbe.warehouse
				"""
				
				batch_data = frappe.db.sql(sql_query, sql_params, as_dict=1)

				# Fallback: check Stock Entry Detail for batch_no (when use_serial_batch_fields is used)
				if not batch_data and kwargs.item_code:
					batch_data = frappe.db.sql(f"""
						SELECT
							sed.batch_no,
							SUM(sed.qty) as qty,
							sed.t_warehouse as warehouse
						FROM `tabStock Entry Detail` AS sed
						WHERE
							sed.parent IN ({entry_list})
							AND sed.item_code = %(item_code)s
							AND sed.batch_no IS NOT NULL
							AND sed.batch_no != ''
						GROUP BY sed.batch_no, sed.t_warehouse
					""", {"item_code": kwargs.item_code}, as_dict=1)

				# If MTfM entries exist, only return batches from those entries
				# Don't fall back to standard selection - force user to pick from MTfM batches
				if batch_data:
					# Filter: only keep batches that have actual stock in the WIP warehouse
					filtered = []
					for bd in batch_data:
						batch_no = cstr(bd.get("batch_no")).strip()
						if not batch_no:
							continue
						wip_qty = frappe.db.sql(
							"""SELECT IFNULL(SUM(actual_qty), 0)
							FROM `tabStock Ledger Entry`
							WHERE batch_no = %s AND warehouse = %s AND is_cancelled = 0""",
							(batch_no, wip_warehouse),
						)
						if wip_qty and flt(wip_qty[0][0]) > 0:
							filtered.append(bd)

					if filtered:
						return filtered
					# If MTfM entries exist but no valid batches found (all rejected), return empty list
					return []
				else:
					# MTfM entries exist but no batches found for this item - return empty list
					return []

	# Fallback to standard batch selection (only if no MTfM entries exist)


def get_available_serial_nos(kwargs):
	# start foss changes
	if kwargs.get("doc"):
		try:
			doc = frappe._dict(parse_json(kwargs.doc))
		except:
			doc = kwargs.doc
		if doc.get("doctype") == "Stock Entry" and doc.get("stock_entry_type") == "Manufacture":
			material_transfer_entry = frappe.get_all("Stock Entry", { 
				"stock_entry_type" : "Material Transfer for Manufacture",
				"work_order" : doc.get("work_order"),
				"docstatus" :  1,
				}, pluck="name")

			conditions = ''
			if material_transfer_entry:
				conditions = " and sbb.voucher_no in {} ".format(
						"(" + ", ".join([f'"{l}"' for l in material_transfer_entry]) + ")")	

			if kwargs.item_code:
				conditions += f"  and sbb.item_code = '{kwargs.item_code}'"

			if kwargs.has_serial_no:
				conditions += f" and sbb.has_serial_no = '{kwargs.has_serial_no}'"
			
			if kwargs.get("warehouse"):
				conditions += f" and serial.warehouse = '{kwargs.warehouse}'"
			limit = ''

			if cint(kwargs.qty):
				limit = f"Limit {cint(kwargs.qty)}"
			else:
				limit = f"Limit 10000000"

			serial_no = frappe.db.sql(f"""
				SELECT *
				FROM (
					SELECT 
						sbe.serial_no,
						serial.warehouse,
						serial.batch_no,
						sbb.type_of_transaction,
						sle.posting_datetime,
						ROW_NUMBER() OVER(
							PARTITION BY sbe.serial_no
							ORDER BY sle.posting_datetime DESC
						) AS rn
					FROM `tabSerial and Batch Bundle` AS sbb
					LEFT JOIN `tabSerial and Batch Entry` AS sbe
						ON sbe.parent = sbb.name
					LEFT JOIN `tabSerial No` AS serial
						ON serial.name = sbe.serial_no
					LEFT JOIN `tabStock Ledger Entry` AS sle 
						ON sle.serial_and_batch_bundle = sbb.name
					WHERE 
						serial.status = "Active"
						AND sle.is_cancelled = 0
						{conditions}
				) t
				WHERE t.rn = 1
				ORDER BY posting_datetime DESC
				{limit}
			""", as_dict=1)

			
			if serial_no:
				return serial_no
	# end changes

	fields = ["name as serial_no", "warehouse"]
	if kwargs.has_batch_no:
		fields.append("batch_no")

	order_by = "creation"
	if kwargs.based_on == "LIFO":
		order_by = "creation desc"
	elif kwargs.based_on == "Expiry":
		order_by = "amc_expiry_date asc"

	filters = {"item_code": kwargs.item_code}

	# ignore_warehouse is used for backdated stock transactions
	# There might be chances that the serial no not exists in the warehouse during backdated stock transactions
	if not kwargs.get("ignore_warehouse"):
		filters["warehouse"] = ("is", "set")
		if kwargs.warehouse:
			filters["warehouse"] = kwargs.warehouse

	# Since SLEs are not present against Reserved Stock [POS invoices, SRE], need to ignore reserved serial nos.
	ignore_serial_nos = get_reserved_serial_nos(kwargs)

	# To ignore serial nos in the same record for the draft state
	if kwargs.get("ignore_serial_nos"):
		ignore_serial_nos.extend(kwargs.get("ignore_serial_nos"))

	if kwargs.get("posting_date"):
		if kwargs.get("posting_time") is None:
			kwargs.posting_time = nowtime()

		time_based_serial_nos = get_serial_nos_based_on_posting_date(kwargs, ignore_serial_nos)

		if not time_based_serial_nos:
			return []

		filters["name"] = ("in", time_based_serial_nos)
	elif ignore_serial_nos:
		filters["name"] = ("not in", ignore_serial_nos)
	elif kwargs.get("serial_nos"):
		filters["name"] = ("in", kwargs.get("serial_nos"))

	if kwargs.get("batches"):
		batches = get_non_expired_batches(kwargs.get("batches"))
		if not batches:
			return []

		filters["batch_no"] = ("in", batches)

	return get_serial_nos_based_on_filters(filters, fields, order_by, kwargs)


def validate(self, method):
	validate_reserved_stock_usage(self)

	if self.voucher_type == "Stock Entry":
		stock_entry_type = frappe.db.get_value("Stock Entry", self.voucher_no, "stock_entry_type")
		
		if stock_entry_type == "Manufacture":
			work_order = frappe.db.get_value("Stock Entry", self.voucher_no, "work_order")

			err_validate= not_validate_finished_item(self, self.voucher_detail_no)

			if self.voucher_detail_no and (err_validate.get("is_finished_item") or err_validate.get("has_serial_no_replaced")):
				return
			material_transfer_entries = frappe.get_all(
				"Stock Entry", 
				{"stock_entry_type": "Material Transfer for Manufacture", "work_order": work_order, "docstatus": 1}, 
				pluck="name"
			)

			# Build conditions for querying serials and batches
			conditions = build_conditions(self, material_transfer_entries)
			
			# SQL to fetch serial numbers and batch numbers
			serial_no_data = get_serial_no_data(conditions, material_transfer_entries)
			batch_no_data = get_batch_no_data(conditions)

			# Prepare the lists for validation
			pre_serial_no = [row.get("serial_no") for row in serial_no_data]
			pre_batch_no = [row.batch_no for row in batch_no_data]

			# Validate each entry in self.entries
			for row in self.entries:
				if row.get("serial_no") and row.get("serial_no") not in pre_serial_no:
					idx = frappe.db.sql(f"Select idx From `tabStock Entry Detail` Where name = '{self.voucher_detail_no}'", as_dict=1)
					message = _(f"Row #{idx[0].idx}: Selected Serial No '{frappe.bold(get_link_to_form('Serial No', row.get('serial_no')))}' is not from previous material transfer entries.<br>")
					message += _(f"Serial No should be from related work order process {frappe.bold(get_link_to_form('Work Order', work_order))}")
					message += _(f"<br><br>To update the correct serial no, use <b>'Add Serial / Batch No'</b> button.")
					if frappe.db.get_single_value("Stock Settings", "enable_validation_serial_no"):
						frappe.throw(message)

def validate_reserved_stock_usage(self):
	serial_nos = []
	outward_batch_qty = {}

	for entry in self.entries:
		serial_no = cstr(entry.get("serial_no")).strip()
		batch_no = cstr(entry.get("batch_no")).strip()
		warehouse = cstr(entry.get("warehouse")).strip()

		if serial_no:
			serial_nos.append(serial_no)

		# For Serial and Batch Bundle, qty can be negative for Outward rows.
		# Use absolute qty so that both +ve and -ve entries are counted correctly.
		if self.type_of_transaction == "Outward" and batch_no and warehouse and flt(entry.get("qty")):
			key = (batch_no, warehouse)
			outward_batch_qty[key] = outward_batch_qty.get(key, 0) + abs(flt(entry.get("qty")))

	if not serial_nos and not outward_batch_qty:
		return

	reserved_refs = get_reserved_stock_references(serial_nos=serial_nos, batch_nos=[])
	reserved_serials = reserved_refs.get("serial_no", {})
	violating_batches = {}

	if outward_batch_qty:
		batch_details = get_reserved_batch_details(
			batch_nos=[k[0] for k in outward_batch_qty.keys()],
			warehouses=[k[1] for k in outward_batch_qty.keys()],
		)
		for (batch_no, warehouse), outgoing_qty in outward_batch_qty.items():
			reserved_detail = batch_details.get((batch_no, warehouse))
			if not reserved_detail:
				continue

			reserved_qty = flt(reserved_detail.get("reserved_qty"))
			current_qty = get_batch_qty_in_warehouse(batch_no, warehouse)
			projected_qty = current_qty - flt(outgoing_qty)

			if projected_qty < reserved_qty:
				violating_batches[(batch_no, warehouse)] = {
					"reserved_qty": reserved_qty,
					"current_qty": current_qty,
					"outgoing_qty": outgoing_qty,
					"reserve_stocks": reserved_detail.get("reserve_stocks", []),
				}

	if not reserved_serials and not violating_batches:
		return
	message_parts = []
	
	if reserved_serials:
		serial_links = ", ".join(
			frappe.bold(get_link_to_form("Serial No", serial_no))
			for serial_no in sorted(reserved_serials.keys())
		)
		message_parts.append(
			_(
				"The following Serial Nos are currently reserved and cannot be used in this transaction: {0}."
			).format(serial_links)
		)

	if violating_batches:
		for (batch_no, warehouse), data in sorted(violating_batches.items()):
			message_parts.append(
				_(
					"Batch {0} in warehouse {1} cannot be used for qty {2}. <br><br>"
					"Current qty: {3} <br>Reserved qty: {4}"
				).format(
					frappe.bold(get_link_to_form("Batch", batch_no)),
					frappe.bold(warehouse),
					frappe.bold(flt(data.get("outgoing_qty"))),
					frappe.bold(flt(data.get("current_qty"))),
					frappe.bold(flt(data.get("reserved_qty")))
				)
			)

	reserve_stock_links = sorted(
		set(
			[
				*reserved_serials.values(),
				*[
					reserve_stock
					for row in violating_batches.values()
					for reserve_stock in row.get("reserve_stocks", [])
				],
			]
		)
	)

	frappe.throw("<br>".join(message_parts))


def not_validate_finished_item(self, voucher_detail_no):
	data = frappe.db.sql(f"""
				Select is_finished_item, has_serial_no_replaced
				From `tabStock Entry Detail`
				Where name = '{voucher_detail_no}'
	 """, as_dict=1)

	return { "is_finished_item": data[0].is_finished_item, "has_serial_no_replaced" : data[0].has_serial_no_replaced } 

def build_conditions(self, material_transfer_entries):
	"""Build SQL conditions for serial and batch validation."""
	conditions = ''
	if material_transfer_entries:
		conditions += " AND sbb.voucher_no IN ({})".format(
			", ".join([f'"{entry}"' for entry in material_transfer_entries])
		)

	if self.item_code:
		conditions += f" AND sbb.item_code = '{self.item_code}'"

	if self.has_serial_no:
		conditions += f" AND sbb.has_serial_no = {self.has_serial_no}"

	return conditions

def get_serial_no_data(conditions, material_transfer_entries):
    """Fetch active serial numbers based on conditions."""

    # 1️⃣ Fetch serial numbers from Serial & Batch tables
    serial_no = frappe.db.sql(
        f"""
        SELECT 
            sbe.serial_no, 
            serial.warehouse, 
            serial.batch_no
        FROM `tabSerial and Batch Bundle` AS sbb
        LEFT JOIN `tabSerial and Batch Entry` AS sbe 
            ON sbe.parent = sbb.name
        LEFT JOIN `tabSerial No` AS serial 
            ON serial.name = sbe.serial_no
        WHERE serial.status = "Active" {conditions}
        """,
        as_dict=True,
    )

    if not material_transfer_entries:
        return serial_no

    # 2️⃣ Fetch serial numbers from Stock Entry Detail (in one optimized query)
    placeholders = ", ".join(["%s"] * len(material_transfer_entries))

    raw_serials = frappe.db.sql(
        f"""
        SELECT sed.serial_no
        FROM `tabStock Entry Detail` AS sed
        WHERE sed.parent IN ({placeholders})
        """,
        values=material_transfer_entries,
        as_dict=True,
    )

    # 3️⃣ Split and flatten serial numbers
    extra_serials = []
    for row in raw_serials:
        if row.serial_no:
            extra_serials.extend(
                {"serial_no": s.strip()}
                for s in row.serial_no.split("\n") if s.strip()
            )

    return serial_no + extra_serials


def get_batch_no_data(conditions):
	"""Fetch batch numbers with remaining quantity based on conditions."""
	return frappe.db.sql(f"""
		SELECT sbe.serial_no, batch.name AS batch_no
		FROM `tabSerial and Batch Bundle` AS sbb
		LEFT JOIN `tabSerial and Batch Entry` AS sbe ON sbe.parent = sbb.name
		LEFT JOIN `tabBatch` AS batch ON batch.name = sbe.batch_no
		WHERE 1=1 AND batch.batch_qty > 0 {conditions}
	""", as_dict=1)

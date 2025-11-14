import frappe
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	get_auto_batch_nos,
	get_reserved_serial_nos,
	get_serial_nos_based_on_posting_date,
	get_non_expired_batches
)
from frappe.utils import parse_json, cint, get_link_to_form
from frappe import _


@frappe.whitelist()
def get_auto_data(**kwargs):
	kwargs = frappe._dict(kwargs)
	if cint(kwargs.has_serial_no):
		return get_available_serial_nos(kwargs)

	elif cint(kwargs.has_batch_no):
		return get_auto_batch_nos(kwargs)


def get_available_serial_nos(kwargs):
	# start foss changes
	if kwargs.get("doc"):
		doc = frappe._dict(parse_json(kwargs.doc))
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
							Select sbe.serial_no, serial.warehouse, serial.batch_no
							From `tabSerial and Batch Bundle` as sbb
							Left Join `tabSerial and Batch Entry` as sbe ON sbe.parent =  sbb.name
							Left Join `tabSerial No` as serial ON serial.name = sbe.serial_no
							Where 1=1 and serial.status="Active" {conditions} 
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

	if kwargs.get("batches"):
		batches = get_non_expired_batches(kwargs.get("batches"))
		if not batches:
			return []

		filters["batch_no"] = ("in", batches)

	return frappe.get_all(
		"Serial No",
		fields=fields,
		filters=filters,
		limit=cint(kwargs.qty) or 10000000,
		order_by=order_by,
	)


def validate(self, method):
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
			serial_no_data = get_serial_no_data(conditions)
			batch_no_data = get_batch_no_data(conditions)

			# Prepare the lists for validation
			pre_serial_no = [row.serial_no for row in serial_no_data]
			pre_batch_no = [row.batch_no for row in batch_no_data]

			# Validate each entry in self.entries
			for row in self.entries:
				if row.serial_no and row.serial_no not in pre_serial_no:
					idx = frappe.db.sql(f"Select idx From `tabStock Entry Detail` Where name = '{self.voucher_detail_no}'", as_dict=1)
					message = _(f"Row #{idx[0].idx}: Selected Serial No '{frappe.bold(get_link_to_form('Serial No', row.serial_no))}' is not from previous material transfer entries.<br>")
					message += _(f"Serial No should be from related work order process {frappe.bold(get_link_to_form('Work Order', work_order))}")
					message += _(f"<br><br>To update the correct serial no, use <b>'Add Serial / Batch No'</b> button.")
					if frappe.db.get_single_value("Stock Settings", "enable_validation_serial_no"):
						frappe.throw(message)


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

def get_serial_no_data(conditions):
	"""Fetch active serial numbers based on conditions."""
	return frappe.db.sql(f"""
		SELECT sbe.serial_no, serial.warehouse, serial.batch_no
		FROM `tabSerial and Batch Bundle` AS sbb
		LEFT JOIN `tabSerial and Batch Entry` AS sbe ON sbe.parent = sbb.name
		LEFT JOIN `tabSerial No` AS serial ON serial.name = sbe.serial_no
		WHERE 1=1 AND serial.status="Active" {conditions}
	""", as_dict=1)

def get_batch_no_data(conditions):
	"""Fetch batch numbers with remaining quantity based on conditions."""
	return frappe.db.sql(f"""
		SELECT sbe.serial_no, batch.name AS batch_no
		FROM `tabSerial and Batch Bundle` AS sbb
		LEFT JOIN `tabSerial and Batch Entry` AS sbe ON sbe.parent = sbb.name
		LEFT JOIN `tabBatch` AS batch ON batch.name = sbe.batch_no
		WHERE 1=1 AND batch.batch_qty > 0 {conditions}
	""", as_dict=1)

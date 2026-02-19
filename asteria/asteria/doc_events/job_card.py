import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from frappe.model.mapper import get_mapped_doc
from erpnext import get_company_currency, get_default_company
from frappe.utils import flt
from erpnext.stock.doctype.stock_entry.stock_entry import OperationsNotCompleteError


def on_submit(self, method):
	if self.work_order:

		job_cards = frappe.db.get_list('Job Card',
											filters={
												'work_order': self.work_order,
												"docstatus" : ["<", 2]
											},
											fields=['name', 'status'],
											order_by='name desc',
										)
		
		
		not_completed = [
			row.name for row in job_cards if row.status != "Completed"
		]

		if not_completed:
			return

		if not job_cards:
			return 

		# check if any workflow is active
		workflow = frappe.db.get_value("Workflow", { "is_active" : 1 , "document_type" : "Stock Entry"}, "name")

		fg_warehouse = frappe.db.get_value("Work Order", self.work_order, "fg_warehouse")
		qty=None
		if self.for_quantity:
			qty = self.for_quantity
		try:
			stock_entry = make_stock_entry(
				self.work_order,
				"Manufacture",
				target_warehouse=fg_warehouse,
				qty=qty
			)

		except OperationsNotCompleteError as e:
			return   # or handle logic safely
		
		except frappe.ValidationError:
			raise  

		se = frappe.get_doc(stock_entry)

		work_order = frappe.get_doc("Work Order", self.work_order)
		se.cost_center = work_order.custom_cost_center
		se.project = work_order.project
		se.business_unit = work_order.custom_business_unit
		se.create_from_job_card = 1


		from asteria.asteria.override.serial_and_batch_bundle import get_auto_data
		
		for row in se.items:
			row.cost_center = work_order.custom_cost_center
			row.business_unit = work_order.custom_business_unit
			row.project = work_order.project

			if row.get("is_finished_item"):
				continue

			has_serial_no = frappe.db.get_value("Item", row.item_code, "has_serial_no")
			has_batch_no = frappe.db.get_value("Item", row.item_code, "has_batch_no")

			args = {
					'doc' : se,
					'item_code': row.item_code,
					'warehouse': row.s_warehouse,
					'has_serial_no': has_serial_no,
					'has_batch_no': has_batch_no,
					'qty': row.qty,
					'based_on': "FIFO",
					'posting_date' : se.posting_date,
					'posting_time' : se.posting_time,
				}
			
			auto_data = get_auto_data(**args) or []
			sr_list = [d.get("serial_no") for d in auto_data if d.get("serial_no")]

			if sr_list: 
				serial_no_list = ",".join(sr_list)
				row.use_serial_batch_fields = 1
				row.serial_no = serial_no_list

			# Auto-select batch from the same work order cycle
			if not sr_list and has_batch_no:
				batch_list = [d for d in auto_data if d.get("batch_no")]
				if batch_list:
					row.use_serial_batch_fields = 1
					row.batch_no = batch_list[0].get("batch_no")
		

		se.insert(ignore_mandatory = True)
		if workflow:
			doc = frappe.get_doc("Workflow", workflow)
			workflow_state = doc.transitions[0].get("next_state")
			frappe.db.set_value("Stock Entry", se.name, "workflow_state", workflow_state)
			# se.flags.ignore_permissions = True
			# se.flags.ignore_mandatory = True
			# se.save()

		frappe.msgprint("Stock Entry is successfully created. {0}".format(frappe.utils.get_link_to_form("Stock Entry", se.name)))


@frappe.whitelist()
def create_stock_entry(source_name, target_doc=None):
	doclist = get_mapped_doc(
		"Job Card",
		source_name,
		{
			"Job Card": {
				"doctype": "Stock Entry", 
				"validation": {"docstatus": ["=", 0]},
				"field_map" : {
					"job_card" : "name"
				}
			},
		},
		target_doc,
	)
	
	doclist.update({
		"stock_entry_type" : "Material Transfer for Manufacture",
		"from_warehouse" : "Main Store - AAPL",
		"to_warehouse" : "WIP Store - AAPL"
	})
	if custom_non_conformance:= frappe.db.exists("Non Conformance", {"custom_job_card_number" : source_name}):
		doclist.update({
			"custom_non_conformance" : custom_non_conformance
		})

	return doclist


def validate(self, method):
	fetch_non_conformance(self)
	fetch_nc_action(self)

def fetch_non_conformance(self):
	if self.for_job_card:
		if non_conformances := frappe.db.get_list("Non Conformance", {"custom_job_card_number" : self.for_job_card}, pluck="name"):
			current_data = [
				d.non_conformance for d in self.non_conformance_table
			]
			
			for row in non_conformances:
				if row not in current_data:
					self.append("non_conformance_table", {
						"non_conformance" : row
					})

def fetch_nc_action(self):
	if self.for_job_card:
		if nc_actions := frappe.db.get_list("NC Actions", {"job_card" : self.for_job_card}, pluck="name"):
			current_data = [
				d.nc_action for d in self.non_action_table
			]	

			for row in nc_actions:
				if row not in current_data:
					self.append("non_action_table", {
						"nc_action" : row
					})

@frappe.whitelist()
def make_corrective_job_card(source_name, operation=None, for_operation=None, target_doc=None):
	def set_missing_values(source, target):
		target.is_corrective_job_card = 1
		target.operation = operation
		target.for_operation = for_operation

		target.set("time_logs", [])
		target.set("employee", [])
		target.set("items", [])
		target.set("sub_operations", [])
		target.set_sub_operations()
		target.get_required_items()
		target.validate_time_logs()
		if target.for_job_card:
			if frappe.db.exists("Job Card", {
				"is_corrective_job_card" : 1,
				"for_job_card" : target.for_job_card,
				"docstatus" : 1
			}):
				corrective_job_card = frappe.db.get_list("Job Card", 
						{"is_corrective_job_card" : 1,
						"for_job_card" : target.for_job_card,
						"docstatus" : 1}, 
						"for_quantity"
				)
				total_qty = frappe.db.get_value("Job Card", target.for_job_card, "for_quantity")
				if corrective_job_card:
					produced_qty = sum([row.for_quantity for row in corrective_job_card])
					if total_qty > 0 and produced_qty:
						target.for_quantity = total_qty - produced_qty
				


	doclist = get_mapped_doc(
		"Job Card",
		source_name,
		{
			"Job Card": {
				"doctype": "Job Card",
				"field_map": {
					"name": "for_job_card",
				},
			}
		},
		target_doc,
		set_missing_values,
	)

	return doclist
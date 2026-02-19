import frappe
from erpnext.manufacturing.doctype.production_plan.production_plan import ProductionPlan
from frappe.utils import flt, getdate, nowdate

class CustomProductionPlan(ProductionPlan):
	def make_subcontracted_purchase_order(self, subcontracted_po, purchase_orders):
		if not subcontracted_po:
			return
		# changes by fosserp start
		sales_order = None
		material_request = None
		if (self.sales_orders):
			sales_order = self.sales_orders[0].sales_order

		if (self.material_requests):
			material_request = self.material_requests[0].material_request

		# changes by fosserp end

		for supplier, po_list in subcontracted_po.items():
			po = frappe.new_doc("Purchase Order")
			po.company = self.company
			po.supplier = supplier
			po.schedule_date = getdate(po_list[0].schedule_date) if po_list[0].schedule_date else nowdate()
			po.is_subcontracted = 1

			# changes by fosserp start
			if sales_order:
				po.sales_order = sales_order
				po.cost_center = self.custom_cost_center or frappe.get_cached_value("Sales Order", sales_order, "cost_center")
				po.project = self.custom_project or frappe.get_cached_value("Sales Order", sales_order, "project")
				po.business_unit = self.custom_business_unit or frappe.get_cached_value("Sales Order", sales_order, "business_unit")
			

			if material_request:
				mr_doc = frappe.get_doc("Material Request", material_request)
				mr_doc_first_item = mr_doc.items[0]
				po.material_request = material_request
				po.cost_center = mr_doc_first_item.cost_center
				po.project = mr_doc_first_item.project
				po.business_unit = mr_doc_first_item.business_unit
			
			# changes by fosserp end

			for row in po_list:
				po_data = {
					"fg_item": row.production_item,
					"warehouse": row.fg_warehouse,
					"production_plan_sub_assembly_item": row.name,
					"bom": row.bom_no,
					"production_plan": self.name,
					"fg_item_qty": row.qty,
				}

				for field in [
					"schedule_date",
					"qty",
					"description",
					"production_plan_item",
				]:
					po_data[field] = row.get(field)

				po.append("items", po_data)

			po.set_service_items_for_finished_goods()
			po.set_missing_values()
			po.flags.ignore_mandatory = True
			po.flags.ignore_validate = True
			po.insert()
			purchase_orders.append(po.name)

	
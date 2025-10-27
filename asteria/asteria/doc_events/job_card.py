import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

def on_submit(self, method):
    if self.work_order:
        operation_sequence_id = frappe.db.sql(f"""
                Select sequence_id
                From `tabWork Order Operation`
                Where parent = '{self.work_order}'
        """, as_dict=1)

        operation_sequence_id = [
            row.sequence_id for row in operation_sequence_id
        ]

        final_opration = max(operation_sequence_id)

        if self.sequence_id == final_opration:
            fg_warehouse = frappe.db.get_value("Work Order", self.work_order, "fg_warehouse")
            stock_entry = make_stock_entry(self.work_order, "Manufacture", target_warehouse = fg_warehouse)
            se = frappe.get_doc(stock_entry)
            work_order = frappe.get_doc("Work Order", self.work_order)
            se.cost_center = work_order.custom_cost_center
            se.project = work_order.project
            se.business_unit = work_order.custom_business_unit
            se.create_from_job_card = 1

            for row in se.items:
                row.cost_center = work_order.custom_cost_center
                row.business_unit = work_order.custom_business_unit
                row.project = work_order.project

            se.insert(ignore_mandatory = True)

            frappe.msgprint("Stock Entry is successfully created. {0}".format(frappe.utils.get_link_to_form("Stock Entry", se.name)))



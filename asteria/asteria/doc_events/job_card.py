import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from frappe.model.mapper import get_mapped_doc
from erpnext import get_company_currency, get_default_company


def on_submit(self, method):
    if self.work_order:

        job_cards = frappe.db.get_list('Job Card',
                                            filters={
                                                'work_order': self.work_order,
                                                "docstatus" : ["<", 2]
                                            },
                                            fields=['name'],
                                            order_by='name desc',
                                        )
        if not job_cards:
            return  
        if self.name == job_cards[0].get("name"):
            # check if any workflow is active
            workflow = frappe.db.get_value("Workflow", { "is_active" : 1 , "document_type" : "Stock Entry"}, "name")

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

            if workflow:
                doc = frappe.get_doc("Workflow", workflow)
                se.workflow_state = doc.transitions[0].get("next_state")
                se.flags.ignore_permissions = True
                se.flags.ignore_mandatory = True
                se.save()

            doc = frappe.get_doc("Stock Entry", se.name)
            from asteria.asteria.override.serial_and_batch_bundle import get_auto_data
            for row in doc.items:
                if row.get("is_finished_item"):
                    continue
                args = {
                        'doc' : doc,
                        'item_code': row.item_code,
                        'warehouse': row.s_warehouse,
                        'has_serial_no': frappe.db.get_value("Item", row.item_code, "has_serial_no"),
                        'has_batch_no': frappe.db.get_value("Item", row.item_code, "has_batch_no"),
                        'qty': row.qty,
                        'based_on': "FIFO",
                        'posting_date' : doc.posting_date,
                        'posting_time' : doc.posting_time,
                    }
                
                serial_no = get_auto_data(**args) or []
                sr_list = [d.get("serial_no") for d in serial_no if d.get("serial_no")]
               
                if sr_list and row.qty != len(sr_list):
                    row.qty = len(sr_list)
                    
                if sr_list: 
                    serial_no_list = "\n".join(sr_list)
                    row.use_serial_batch_fields = 1
                    row.serial_no = serial_no_list

            doc.flags.ignore_permissions=True
            doc.flags.ignore_mandatory=True
            
            doc.save()

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

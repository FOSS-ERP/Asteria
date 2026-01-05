import frappe

def validate(doc, method=None):
    if doc.reference_type == "Stock Entry":
        if doc.reference_name: 
            work_order = frappe.db.get_value("Stock Entry",doc.reference_name,"work_order")
            doc.custom_work_order = work_order
            
    if doc.reference_type == "Job Card":
        if doc.reference_name: 
            job_card = frappe.db.get_value("Job Card",doc.reference_name,"work_order")
            doc.custom_work_order = job_card
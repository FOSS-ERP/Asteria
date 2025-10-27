import frappe

def execute():
    frappe.get_doc({
        "doctype" : "Custom Field",
        "dt" : "Stock Entry",
        "fieldtype" : "Check",
        "fieldname" : "create_from_job_card",
        "label" : "Reference From Job Card",
        "hidden" : 1
    }).insert()
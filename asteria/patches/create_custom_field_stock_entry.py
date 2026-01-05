import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    setup_custom_fields()

def setup_custom_fields():
    """Setup custom fields for Referral Practitioner Integration"""
    custom_fields = {
        "Stock Entry": [
            {
                "fieldname" : "job_card",
                "label" : "Job Card",
                "fieldtype" : "Link",
                "options" : "Job Card",
                "insert_after" : "cost_center",
                "allow_on_submit" : 0
            }
        ]
    }
    
    # create_custom_fields(custom_fields)
    print("Custom Fields for Referral Practitioner Integration created successfully") 

    stock_entries = frappe.db.get_list("Stock Entry", {"custom_job_card" : ["!=", '']})
    for row in stock_entries:
        linked_job_card = frappe.db.get_value("Stock Entry", row.name, "custom_job_card")
        frappe.db.set_value("Stock Entry", row.name, "job_card", linked_job_card, update_modified=False)
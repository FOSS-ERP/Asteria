import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def setup_custom_fields():
    """Setup custom fields for Referral Practitioner Integration"""
    custom_fields = {
        "Stock Entry": [
            {
                "fieldname" : "cost_center",
                "label" : "Cost Center",
                "fieldtype" : "Link",
                "options" : "Cost Center",
                "insert_after" : "posting_time",
                "allow_on_submit" : 1
            }
        ]
    }
    
    create_custom_fields(custom_fields)
    print("Custom Fields for Referral Practitioner Integration created successfully") 
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
        ],
        "Stock Entry Detail": [
            {
                "label" : "Has Serial No Replaced",
                "fieldname" : "has_serial_no_replaced",
                "fieldtype" : "Check",
                "insert_after" : "use_serial_batch_fields",
                "allow_on_submit" : 0
            }
        ],
        "Accounts Settings": [
            {
                "label" : "Blank Payment Data File IN Excel",
                "fieldname" : "payment_file",
                "fieldtype" : "Attach",
                "insert_after" : "enable_party_matching",
            }
        ],
        "Payment Entry": [
            {
                "label" : "H2H Transfered",
                "fieldname" : "h2h_transfered",
                "fieldtype" : "Check",
                "insert_after" : "mode_of_payment",
            }
        ],
        "Expense Claim Detail" : [
            {
                "label" : "Distance (KM)",
                "fieldname" : "distance",
                "fieldtype" : "Float",
                "insert_after" : "expense_type",
                "in_list_view" : 1
            }
        ],
        "Expense Claim Type" : [
            {
                "label" : "Is Travel Expense Type",
                "fieldname" : "is_travel_type",
                "fieldtype" : "Check",
                "insert_after" : "accounts",
            },
            {
                "label" : "Rate Per KM",
                "fieldname" : "rate_per_km",
                "fieldtype" : "Float",
                "insert_after" : "is_travel_type",
            }
        ]
    }
    
    create_custom_fields(custom_fields)
    print("Custom Fields for Referral Practitioner Integration created successfully") 
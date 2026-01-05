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
        ],
        "Employee" : [
            {
                "label" : "City",
                "fieldname" : "city",
                "fieldtype" : "Data",
                "insert_after" : "cell_number",
                "reqd" :  1
            },
            {
                "label" : "Pincode",
                "fieldname" : "pincode",
                "fieldtype" : "Data",
                "insert_after" : "city",
                "reqd" : 1
            }
        ],
        "Serial No" : [
            {
                "label" : "Warranty Expiry Date For Purchase",
                "fieldname" : "warranty_expiry_date_purchase",
                "fieldtype" : "Date",
                "insert_after" : "amc_expiry_date",
                "reqd" : 0   
            },
        ],
        "Purchase Receipt Item" : [
            {
                "label" : "Warranty Period Day For Purchase",
                "fieldname" : "warranty_period_day_purchase",
                "fieldtype" : "Int",
                "insert_after" : "item_name",
                "reqd" : 0 ,
                "fetch_from" : "item_code.warranty_period_day_purchase",
                "fetch_if_empty" : 1
            }
        ],
        "Item" : [
            {
                "label" : "Warranty Period Day For Purchase",
                "fieldname" : "warranty_period_day_purchase",
                "fieldtype" : "Int",
                "insert_after" : "warranty_period",
                "reqd" : 0 
            }
        ],
        "Batch" : [
            {
                "label" : "Warranty Expiry Date For Purchase",
                "fieldname" : "warranty_expiry_date_purchase",
                "fieldtype" : "Date",
                "insert_after" : "expiry_date",
                "reqd" : 0  
            }
        ],
        "Payment Request" : [
            {
                "label" : "Payment Aging (In Days)",
                "fieldname" : "payment_aging",
                "fieldtype" : "Data",
                "insert_after" : "mode_of_payment",
                "reqd" : 0  
            }
        ]
        
    }
    
    create_custom_fields(custom_fields)
    print("Custom Fields for Referral Practitioner Integration created successfully") 
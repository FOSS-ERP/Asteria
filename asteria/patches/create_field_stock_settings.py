import frappe

def execute():
    frappe.get_doc({
        "doctype" : "Custom Field",
        "dt" : "Stock Settings",
        "label" : "Enable Serial and Batch validation",
        "fieldname" : "enable_validation_serial_no",
        "fieldtype" : "Check",
        "insert_after" : "allow_uom_with_conversion_rate_defined_in_item"
    }).insert()

    frappe.db.set_value("Stock Settings", "Stock Settings", "enable_validation_serial_no", 1)
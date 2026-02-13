import frappe

def execute():
    frappe.db.sql("""
        UPDATE `tabEmployee Advance`
        SET custom_status = status
        WHERE
            (custom_status IS NULL OR custom_status = '')
            AND status IS NOT NULL
    """)

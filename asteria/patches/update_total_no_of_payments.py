import frappe

def execute():
    frappe.db.sql("""
        UPDATE `tabH2H Log` h
        SET h.total_no_of_payments = (
            SELECT COUNT(*)
            FROM `tabH2H Log Details` v
            WHERE v.parent = h.name
              AND v.parenttype = 'H2H Log'
        )
    """)

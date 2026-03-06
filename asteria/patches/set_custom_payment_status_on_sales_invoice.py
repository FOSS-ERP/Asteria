import frappe

def execute():
    """
    Set custom_payment_status = status for all Sales Invoices
    where custom_payment_status is empty/missing.
    """
    frappe.db.sql(""" 
        UPDATE `tabSales Invoice`
        SET custom_payment_status = status
        WHERE
            (custom_payment_status IS NULL OR custom_payment_status = '')
            AND status IS NOT NULL
    """)
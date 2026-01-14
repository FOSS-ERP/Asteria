import frappe
from frappe.utils import today


def on_submit(self, method=None):
    update_payment_date(self)

def update_payment_date(self):
    for row in self.references:
        if row.payment_request:
            doc = frappe.get_doc("Payment Request", row.payment_request)
            doc.last_payment_date = today()
            doc.save()

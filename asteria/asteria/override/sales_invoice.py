import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

class CustomSalesInvoice(SalesInvoice):
    def set_status(self, update=False, status=None, update_modified=True):
        # call the original method
        super().set_status(update, status, update_modified)
        
        self.custom_payment_status = self.status
        
        if update:
            self.db_set("custom_payment_status", self.status, update_modified=update_modified)
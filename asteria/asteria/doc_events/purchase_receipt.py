import frappe
from frappe.utils import (
	add_days,
	add_months,
	cint,
	date_diff,
	flt,
	get_first_day,
	get_last_day,
	get_link_to_form,
	getdate,
	rounded,
	today,
)

def on_submit(self,method=None):
    update_warenty_expiry_date(self)

def update_warenty_expiry_date(self):
    if not frappe.db.get_value("Purchase Receipt", self.voucher_no, "custom_supplier_invoice_date"):
        return
    else:
        custom_supplier_invoice_date = frappe.db.get_value("Purchase Receipt", self.voucher_no, "custom_supplier_invoice_date")
    if self.voucher_type == "Purchase Receipt" and self.voucher_no and self.voucher_detail_no:
        if self.has_serial_no:
            days = frappe.db.sql(f"Select warranty_period_day_purchase as days From `tabPurchase Receipt Item` Where name = '{self.voucher_detail_no}'", as_dict=1)
            if days and days[0].get("days") and days[0].get("days") > 0:
                warranty_date = add_days(str(getdate(custom_supplier_invoice_date)), (days[0].get("days") - 1) )
                frappe.db.set_value("Item", self.item_code, "warranty_period_day_purchase", days[0].get("days"))
                for row in self.entries:
                    frappe.db.set_value("Serial No", row.serial_no, "warranty_expiry_date_purchase", warranty_date)
        
        if self.has_batch_no:
            days = frappe.db.sql(f"Select warranty_period_day_purchase as days From `tabPurchase Receipt Item` Where name = '{self.voucher_detail_no}'", as_dict=1)
            if days and days[0].get("days") and days[0].get("days") > 0:
                warranty_date = add_days(str(getdate(custom_supplier_invoice_date)), (days[0].get("days") - 1))
                frappe.db.set_value("Item", self.item_code, "warranty_period_day_purchase", days[0].get("days"))
                for row in self.entries:
                    frappe.db.set_value("Batch", row.batch_no, "warranty_expiry_date_purchase", warranty_date)
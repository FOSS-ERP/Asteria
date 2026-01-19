import frappe
import re
from frappe.model.mapper import get_mapped_doc
from frappe.utils import getdate

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_fg_serial_no(doctype, txt, searchfield, start, page_len, filters):
    conditions = []
    values = []

    if txt:
        conditions.append("sed.serial_no LIKE %s")
        values.append(f"%{txt}%")

    condition_sql = " AND ".join(conditions)
    if condition_sql:
        condition_sql = " AND " + condition_sql

    query = f"""
        SELECT sed.serial_no
        FROM `tabStock Entry Detail` sed
        WHERE
            sed.is_finished_item = 1
            AND sed.docstatus = 1
            {condition_sql}
        ORDER BY sed.serial_no
        LIMIT %s OFFSET %s
    """

    values.extend([page_len, start])

    data = frappe.db.sql(query, values)

    final_data = []

    for (sr_no,) in data:
        if not sr_no:
            continue
        result = []
        for part in sr_no.split("\n"):
            result.extend([x.strip() for x in part.split(",") if x.strip()])

        for sr in result:
            sr = sr.strip()
            if sr:
                final_data.append((sr,))

    return final_data


from frappe.utils import getdate

def set_payment_aging_for_payment_request():
    payment_request_list = frappe.db.get_list(
        "Payment Request",
        {"status": ["!=", "Paid"]},
        pluck="name"
    )

    for pr in payment_request_list:
        doc = frappe.get_doc("Payment Request", pr)

        if doc.custom_payment_need_date:
            # date difference
            diff_date =  doc.custom_payment_need_date
            diff_days = (getdate(diff_date) - getdate()).days

            # only store when less than 0
            if diff_days < 0:
                frappe.db.set_value("Payment Request", pr, "payment_aging", abs(diff_days), update_modified=False)
            else:
                frappe.db.set_value("Payment Request", pr, "payment_aging", 0, update_modified=False)

        if doc.last_payment_date:
            diff_date =  doc.last_payment_date
            diff_days = (getdate(diff_date) - getdate()).days

            # only store when less than 0
            if diff_days < 0:
                frappe.db.set_value("Payment Request", pr, "payment_aging_based_last_payment", abs(diff_days), update_modified=False)
            else:
                frappe.db.set_value("Payment Request", pr, "payment_aging_based_last_payment", 0, update_modified=False)


def update_aging_in_pr(self, method = None):
    if self.status == "Paid":
        return

    last_payment_date = self.last_payment_date
    custom_payment_need_date = self.custom_payment_need_date

    diff_days_base1 = (getdate(custom_payment_need_date) - getdate()).days
    diff_days_base2 = (getdate(last_payment_date) - getdate()).days

    if diff_days_base1 < 0:
        self.payment_aging = abs(diff_days_base1)
    else:
        self.payment_aging = 0
    
    if diff_days_base2 < 0:
        self.payment_aging_based_last_payment = abs(diff_days_base2)
    else:
        self.payment_aging_based_last_payment = 0
    
    if method == "on_update_after_submit":
        if self.status == "Paid" and not self.full_payment_date:
            frappe.db.set_value("Payment Request", self.name, "full_payment_date", today(), update_modified=False)

        if diff_days_base1 < 0:
            payment_aging = abs(diff_days_base1)
            frappe.db.set_value("Payment Request", self.name, "payment_aging", payment_aging, update_modified=False)
        else:
            frappe.db.set_value("Payment Request", self.name, "payment_aging", 0, update_modified=False)
        
        if diff_days_base2 < 0:
            payment_aging = abs(diff_days_base2)
            frappe.db.set_value("Payment Request", self.name, "payment_aging_based_last_payment", payment_aging, update_modified=False)
        else:
            frappe.db.set_value("Payment Request", self.name, "payment_aging_based_last_payment", 0, update_modified=False)



@frappe.whitelist()
def create_production_plan(source_name, target_doc=None):

    def set_missing_values(source, target):
        target.posting_date = getdate()
        target.get_items_from = "Sales Order"

        # clear existing rows just in case
        target.sales_orders = []

        target.append("sales_orders", {
            "sales_order": source.name,
            "sales_order_date": source.transaction_date,
            "customer": source.customer,
            "grand_total": source.grand_total
        })

    doc = get_mapped_doc(
        "Sales Order",
        source_name,
        {
            "Sales Order": {
                "doctype": "Production Plan",
                "validation": {"docstatus": ["=", 1]},
            }
        },
        target_doc,
        set_missing_values
    )

    doc.get_items()
    return doc

@frappe.whitelist()
def make_purchase_material_request(source_name, target_doc=None):
    def postprocess(source, target, source_parent):
        target.material_request_type = "Purchase"
        target.reference_mr = source_name
    
    def update_item(source, target, source_parent):
        remaining_qty = (source.qty or 0) - (source.ordered_qty or 0)
        target.qty = remaining_qty

    doc = get_mapped_doc(
        "Material Request",
        source_name,
        {
            "Material Request": {
                "doctype": "Material Request",
                "postprocess": postprocess,
                "validation": {"docstatus": ["=", 1]},
            },
            "Material Request Item": {
                "doctype": "Material Request Item",
                "postprocess": update_item,
                "condition": lambda source: (source.qty or 0) > (source.ordered_qty or 0),
            },
        },
        target_doc
    )
    return doc

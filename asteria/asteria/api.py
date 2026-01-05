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
        {"status": "Initiated"},
        pluck="name"
    )

    for pr in payment_request_list:
        doc = frappe.get_doc("Payment Request", pr)

        if doc.custom_payment_need_date:
            # date difference
            diff_days = (getdate(doc.custom_payment_need_date) - getdate()).days

            # only store when less than 0
            if diff_days < 0:
                frappe.db.set_value("Payment Request", pr, "payment_aging", abs(diff_days))
            else:
                frappe.db.set_value("Payment Request", pr, "payment_aging", 0)


def update_aging_in_pr(self, method):
    diff_days = (getdate(self.custom_payment_need_date) - getdate()).days

    if diff_days < 0:
        self.payment_aging = abs(diff_days)
    else:
        self.payment_aging = 0



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

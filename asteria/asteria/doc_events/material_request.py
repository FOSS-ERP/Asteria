import frappe
from frappe.utils import flt
from frappe.utils.data import get_link_to_form


def on_submit(self, method=None):
    if self.material_request_type != "Purchase":
        return

    for row in self.items:
        if not (row.material_request and row.material_request_item):
            continue

        mr_item = frappe.db.get_value(
            "Material Request Item",
            row.material_request_item,
            [
                "qty",
                "ordered_qty",
                "received_qty",
                "against_purchase",
                "docstatus",
            ],
            as_dict=True,
        )
        # if not mr_item:
        #     frappe.throw(
        #         f"Material Request Item not found for {get_link_to_form('Material Request', row.material_request)}"
        #     )

        # # MR Item Cancelled
        # if mr_item.docstatus == 2:
        #     frappe.throw(
        #         f"Material Request {get_link_to_form('Material Request', row.material_request)} is Cancelled"
        #     )

      

        total_after_this_po = flt(mr_item.against_purchase) + flt(row.qty) + mr_item.ordered_qty

        # # Over-order validation
        # if total_after_this_po > flt(mr_item.qty):
        #     frappe.throw(
        #         f"""
        #         Material Request is for <b>{mr_item.qty}</b> quantity.<br>
        #         """
        #     )
        new_against_purchase = flt(mr_item.against_purchase) + flt(row.qty)
        # Safe update
        try:
            frappe.db.set_value(
                "Material Request Item",
                row.material_request_item,
                "against_purchase",
                new_against_purchase,
                update_modified=False,
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Material Request Item against_purchase update failed",
            )

import frappe
from frappe.utils import flt, today
from frappe.utils.data import get_link_to_form
import json


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


import json
import frappe
from frappe.utils import today
from frappe import _

@frappe.whitelist()
def create_production_plan(doc):
    try:
        # Safely parse incoming JSON
        if isinstance(doc, str):
            doc = json.loads(doc)

        doc = frappe._dict(doc)

        if not doc.get("name"):
            frappe.throw(_("Material Request name is missing"))

        # Prepare Production Plan data
        args = {
            "doctype": "Production Plan",
            "get_items_from": "Material Request",
            "posting_date": today(),
            "material_requests": [
                {"material_request": doc.name}
            ]
        }

        production_plan = frappe.get_doc(args)

        # Fetch items & sub assemblies
        production_plan.get_items()
        # production_plan.get_sub_assembly_items()

        # Permission handling (use carefully in APIs)
        production_plan.flags.ignore_permissions = True
        production_plan.flags.ignore_mandatory = True

        production_plan.insert()
        message = "<p>Production Plan is created. {0}</p>".format(get_link_to_form("Production Plan", production_plan.name))
        
        frappe.msgprint(message)

    except json.JSONDecodeError:
        frappe.throw(_("Invalid JSON data received"))

    except frappe.ValidationError:
        # Keeps original validation message
        raise

    except Exception as e:
        frappe.log_error(
            title="Production Plan API Error",
            message=frappe.get_traceback()
        )

        frappe.throw(
            _("Failed to create Production Plan. Please check error logs.")
        )


@frappe.whitelist()
def check_if_production_plan_exists(name):
    production_plan = frappe.db.sql(f""" 
        Select ppm.parent
        From `tabProduction Plan Material Request` as ppm
        Where ppm.material_request = '{name}' and ppm.docstatus < 2
    """, as_dict=1)

    if production_plan:
        return True
    else:
        return False
# Copyright (c) 2025, Viral and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)

    # if not filters.get("serial_no") and not (
    #     filters.get("from_date") and filters.get("to_date")
    # ):
    #     return columns, []

    if not filters.get("work_order") and not (
        filters.get("from_date") and filters.get("to_date")
    ):
        return columns, []

    condition_sql, values = get_conditions(filters)
    rows = get_rows(condition_sql, values)

    # Get BOM items (not exploded) for each work order
    bom_cache = {}
    for r in rows:
        if r.work_order not in bom_cache:
            bom_cache[r.work_order] = get_bom_items(r.bom_no, r.wo_qty)

    data = build_tree(rows, bom_cache)
    return columns, data


def get_columns(filters):
    return [
        {"label": "", "fieldname": "indent", "fieldtype": "Int", "width": 40},

        {"label": _("Finished Good"), "fieldname": "fg_item", "fieldtype": "Link", "options": "Item", "width": 180},
        {"label": _("FG Serial No"), "fieldname": "fg_serial_no", "fieldtype": "Link", "options": "Serial No", "width": 150},

        {"label": _("Raw Material (BOM)"), "fieldname": "rm_item_bom", "fieldtype": "Link", "options": "Item", "width": 180},
        {"label": _("Raw Material (Consumed)"), "fieldname": "rm_item_consumed", "fieldtype": "Link", "options": "Item", "width": 180},

        {"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 200},
        {"label": _("BOM ID"), "fieldname": "bom_no", "fieldtype": "Link", "options": "BOM", "width": 280},

        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
        {"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Link", "options": "Stock Entry", "width": 180},

        {"label": _("BOM Qty"), "fieldname": "bom_qty", "fieldtype": "Float", "precision": 2, "width": 120},
        {"label": _("BOM Rate"), "fieldname": "bom_rate", "fieldtype": "Currency", "precision": 2, "width": 120},
        {"label": _("BOM Amount"), "fieldname": "bom_amount", "fieldtype": "Currency", "precision": 2, "width": 120},

        {"label": _("Transferred Qty"), "fieldname": "transferred_qty", "fieldtype": "Float", "precision": 2, "width": 150},
        {"label": _("Transferred Amount"), "fieldname": "transferred_value", "fieldtype": "Currency", "precision": 2, "width": 180},

        {"label": _("Variance Qty (Transferred)"), "fieldname": "variance_issue_qty", "fieldtype": "Float", "precision": 2, "width": 200},
        {"label": _("Variance Amount (Transferred)"), "fieldname": "variance_issue_value", "fieldtype": "Currency", "precision": 2, "width": 200},

        {"label": _("Consumed Qty"), "fieldname": "consumed_qty", "fieldtype": "Float", "precision": 2, "width": 150},
        {"label": _("Consumed Amount"), "fieldname": "consumed_value", "fieldtype": "Currency", "precision": 2, "width": 180},

        {"label": _("Variance Qty (Consumption)"), "fieldname": "variance_consumption_qty", "fieldtype": "Float", "precision": 2, "width": 220},
        {"label": _("Variance Amount (Consumption)"), "fieldname": "variance_consumption_value", "fieldtype": "Currency", "precision": 2, "width": 250},

        {"label": _("Consumed Amount - BOM Amount"), "fieldname": "consumed_minus_bom_amount", "fieldtype": "Currency", "precision": 2, "width": 200},
    ]


def get_conditions(filters):
    conditions = []
    values = {}

    # if filters.get("serial_no"):
    #     conditions.append("sed_fg.serial_no = %(serial_no)s")
    #     values["serial_no"] = filters.get("serial_no")
    
    if filters.get("work_order"):
        conditions.append("se.work_order = %(work_order)s")
        values["work_order"] = filters.get("work_order")
    else:
        if filters.get("from_date"):
            conditions.append("se.posting_date >= %(from_date)s")
            values["from_date"] = filters.get("from_date")
        if filters.get("to_date"):
            conditions.append("se.posting_date <= %(to_date)s")
            values["to_date"] = filters.get("to_date")

    return " AND ".join(conditions), values


def get_rows(condition_sql, values):
    query = f"""
        SELECT
            se.name AS voucher_no,
            se.work_order,
            se.stock_entry_type,
            sed.item_code AS item_code,
            sed.qty AS qty,
            sed.basic_rate AS rate,
            sed.is_finished_item,
            sed.serial_no AS fg_serial_no,
            bo.name AS bom_no,
            wo.qty AS wo_qty,
            wo.production_item AS fg_item
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed
            ON sed.parent = se.name
        INNER JOIN `tabWork Order` wo
            ON wo.name = se.work_order AND wo.docstatus = 1
        LEFT JOIN `tabBOM` bo
            ON bo.name = wo.bom_no
        WHERE se.docstatus = 1
        {f" AND {condition_sql}" if condition_sql else ""}
        AND (
            (sed.is_finished_item = 1 AND se.stock_entry_type = 'Manufacture') 
            OR (sed.is_finished_item = 0 AND se.stock_entry_type IN ('Manufacture', 'Material Transfer for Manufacture'))
        )
        ORDER BY se.work_order, se.stock_entry_type DESC, sed.is_finished_item DESC
    """
    rows = frappe.db.sql(query, values, as_dict=True)
    add_transferred_qty(rows)
    return rows



def add_transferred_qty(rows):
    if not rows:
        return

    # Only consider raw material rows (is_finished_item = 0)
    raw_material_rows = [r for r in rows if not r.is_finished_item]
    if not raw_material_rows:
        return

    work_orders = list({r.work_order for r in raw_material_rows})
    items = list({r.item_code for r in raw_material_rows})

    if not work_orders or not items:
        # Nothing to fetch, safely set 0
        for r in raw_material_rows:
            r.transferred_qty = 0
        return

    transfer_data = frappe.db.sql("""
        SELECT
            se.work_order,
            sed.item_code,
            SUM(ABS(sed.qty)) AS transferred_qty
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed
            ON sed.parent = se.name AND sed.is_finished_item = 0
        WHERE
            se.docstatus = 1
            AND se.purpose = 'Material Transfer for Manufacture'
            AND se.work_order IN %(work_orders)s
            AND sed.item_code IN %(items)s
        GROUP BY se.work_order, sed.item_code
    """, {"work_orders": work_orders, "items": items}, as_dict=True)

    lookup = {(d.work_order, d.item_code): d.transferred_qty for d in transfer_data}

    for r in raw_material_rows:
        r.transferred_qty = lookup.get((r.work_order, r.item_code), 0)



def get_bom_items(bom_no, wo_qty):
    """Get BOM items (not exploded) - includes subassembly items with their own qty and rate"""
    bom_items = {}
    if not bom_no:
        return bom_items

    company = frappe.db.get_value("BOM", bom_no, "company")
    if not company:
        return bom_items

    # Get BOM items directly (not exploded) to get subassembly items
    bom_doc = frappe.get_doc("BOM", bom_no)
    
    for item in bom_doc.items:
        # Calculate qty based on work order quantity
        item_qty = item.qty * wo_qty
        
        bom_items[item.item_code] = {
            "qty": item_qty,
            "rate": item.rate
        }

    return bom_items


def build_tree(rows, bom_cache):
    data = []
    
    # Group rows by finished good
    fg_groups = {}
    for r in rows:
        if r.is_finished_item:
            key = (r.work_order, r.fg_item, r.fg_serial_no)
            fg_groups[key] = {"fg": r, "raw_materials": []}
    
    # Add raw materials to the corresponding FG group
    for r in rows:
        if not r.is_finished_item:
            # Find FG for this work order
            # If multiple FGs exist for same work_order, attach to first FG
            fg_keys = [k for k in fg_groups.keys() if k[0] == r.work_order]
            if not fg_keys:
                continue
            fg_key = fg_keys[0]
            fg_groups[fg_key]["raw_materials"].append(r)

    # Build final data
    for fg_key, fg_data in fg_groups.items():
        fg = fg_data["fg"]
        raw_materials = fg_data["raw_materials"]

        # Parent row
        data.append({
            "indent": 0,
            "fg_item": fg.fg_item,
            "fg_serial_no": fg.fg_serial_no,
            "work_order": fg.work_order,
            "bom_no": fg.bom_no,
            "voucher_no": None,
            "voucher_type": None,
            "rm_item_bom": None,
            "rm_item_consumed": None,
            "bom_qty": None,
            "bom_rate": None,
            "bom_amount": None,
            "transferred_qty": None,
            "transferred_value": None,
            "variance_issue_qty": None,
            "variance_issue_value": None,
            "consumed_qty": None,
            "consumed_value": None,
            "variance_consumption_qty": None,
            "variance_consumption_value": None,
            "consumed_minus_bom_amount": None,
        })

        # Child rows (raw materials)
        for r in raw_materials:
            bom_items = bom_cache.get(r.work_order, {})
            bom_data = bom_items.get(r.item_code, {})
            bom_qty = bom_data.get("qty", 0)
            bom_rate = bom_data.get("rate", 0)
            bom_amount = bom_qty * bom_rate

            consumed_qty = r.qty or 0
            consumed_rate = r.rate or 0
            consumed_value = consumed_qty * consumed_rate

            transferred_qty = getattr(r, "transferred_qty", 0)
            transferred_value = transferred_qty * bom_rate

            variance_issue_qty = transferred_qty - bom_qty
            variance_issue_value = variance_issue_qty * bom_rate
            variance_consumption_qty = consumed_qty - bom_qty
            variance_consumption_value = variance_consumption_qty * consumed_rate

            data.append({
                "indent": 1,
                "fg_item": fg.fg_item,
                "fg_serial_no": fg.fg_serial_no,
                "work_order": fg.work_order,
                "bom_no": fg.bom_no,
                "voucher_no": r.voucher_no,
                "voucher_type": "Stock Entry",
                "rm_item_bom": r.item_code if bom_data else None,
                "rm_item_consumed": r.item_code,
                "bom_qty": bom_qty,
                "bom_rate": bom_rate,
                "bom_amount": bom_amount,
                "transferred_qty": transferred_qty,
                "transferred_value": transferred_value,
                "variance_issue_qty": variance_issue_qty,
                "variance_issue_value": variance_issue_value,
                "consumed_qty": consumed_qty,
                "consumed_value": consumed_value,
                "variance_consumption_qty": variance_consumption_qty,
                "variance_consumption_value": variance_consumption_value,
                "consumed_minus_bom_amount": consumed_value - bom_amount,
            })

    return data






def empty_parent_row(r):
    return {
        "indent": 0,

        "fg_item": r.fg_item,
        "work_order": r.work_order,
        "bom_no": r.bom_no,

        # Parent row should not point to a single voucher
        "voucher_no": None,
        "voucher_type": None,

        "rm_item_bom": None,
        "rm_item_consumed": None,

        "bom_qty": None,
        "bom_rate": None,
        "bom_amount": None,

        "transferred_qty": None,
        "transferred_value": None,
        "variance_issue_qty": None,
        "variance_issue_value": None,

        "consumed_qty": None,
        "consumed_value": None,
        "variance_consumption_qty": None,
        "variance_consumption_value": None,
        "consumed_minus_bom_amount": None,
    }

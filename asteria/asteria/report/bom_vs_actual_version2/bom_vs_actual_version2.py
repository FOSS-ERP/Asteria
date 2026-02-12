# Copyright (c) 2026, Viral and contributors
# For license information, please see license.txt

# import frappe


import frappe
from frappe import _
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)

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

		{"label" : "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 200},
		{"label": _("SO Delivery Date"), "fieldname": "delivery_date", "fieldtype": "Date", "width": 150},
		{"label": _("Customer ID"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 120},
        {"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 250},
		{"label": _("Production Plan"), "fieldname": "production_plan", "fieldtype": "Link", "options": "Production Plan", "width": 180},
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 185},
		{"label": _("Work Order Status"), "fieldname": "work_order_status", "fieldtype": "Data", "width": 150},
		{"label": _("BOM ID"), "fieldname": "bom_no", "fieldtype": "Link", "options": "BOM", "width": 235},
        ## 
        {"label": _("Finished Good"), "fieldname": "fg_item", "fieldtype": "Link", "options": "Item", "width": 180},
        {"label": _("Raw Material (BOM)"), "fieldname": "rm_item_bom", "fieldtype": "Link", "options": "Item", "width": 180},
        {"label": _("Raw Material(As Per Consumption)"), "fieldname": "rm_item_consumed", "fieldtype": "Link", "options": "Item", "width": 250},	
        # {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
        {"label": _("BOM Qty"), "fieldname": "bom_qty", "fieldtype": "Float", "precision": 2, "width": 120},
        {"label": _("BOM Rate"), "fieldname": "bom_rate", "fieldtype": "Currency", "precision": 2, "width": 120},
        {"label": _("BOM Amount"), "fieldname": "bom_amount", "fieldtype": "Currency", "precision": 2, "width": 120},
        {"label": _("Transferred Qty"), "fieldname": "transferred_qty", "fieldtype": "Float", "precision": 2, "width": 150},
        {"label": _("Transferred Rate"), "fieldname": "transferred_rate", "fieldtype": "Currency", "precision": 2, "width": 150},

        {"label": _("Transferred Amount"), "fieldname": "transferred_value", "fieldtype": "Currency", "precision": 2, "width": 180},
        {"label": _("Variance Qty (Transferred)"), "fieldname": "variance_issue_qty", "fieldtype": "Float", "precision": 2, "width": 200},
        {"label": _("Variance Amount (Transferred)"), "fieldname": "variance_issue_value", "fieldtype": "Currency", "precision": 2, "width": 200},
        {"label": _("Consumed Qty"), "fieldname": "consumed_qty", "fieldtype": "Float", "precision": 2, "width": 150},
        {"label": _("Consumed Rate"), "fieldname": "consumed_rate", "fieldtype": "Currency", "precision": 2, "width": 150},

        {"label": _("Consumed Amount"), "fieldname": "consumed_value", "fieldtype": "Currency", "precision": 2, "width": 180},
        {"label": _("Variance Qty (Consumption)"), "fieldname": "variance_consumption_qty", "fieldtype": "Float", "precision": 2, "width": 220},
        {"label": _("Variance Amount (Consumption)"), "fieldname": "variance_consumption_value", "fieldtype": "Currency", "precision": 2, "width": 250},
        {"label": _("FG Serial No"), "fieldname": "fg_serial_no", "fieldtype": "Link", "options": "Serial No", "width": 250},
        {"label": _("Stock Entry Type"), "fieldname": "stock_entry_type", "fieldtype": "Data", "width" : 120},
        {"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Link", "options": "Stock Entry", "width": 180},
        {"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 180},
        {"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"label": _("Consumed Amt - BOM Amt"), "fieldname": "consumed_minus_bom_amount", "fieldtype": "Currency", "precision": 2, "width": 220},
    ]


def get_conditions(filters):
    conditions = []
    values = {}
    
    if filters.get("work_order"):
        # conditions.append("se.work_order = %(work_order)s")
        conditions.append("""
        (
            (se.purpose != 'Material Issue' AND se.work_order = %(work_order)s)
            OR
            (se.purpose = 'Material Issue' AND se.work_order = %(work_order)s)
        )
        """)
        values["work_order"] = filters.get("work_order")
    else:
        if filters.get("from_date"):
            conditions.append("se.posting_date >= %(from_date)s")
            values["from_date"] = filters.get("from_date")
        if filters.get("to_date"):
            conditions.append("se.posting_date <= %(to_date)s")
            values["to_date"] = filters.get("to_date")

    if filters.get("sales_order"):
        conditions.append("wo.sales_order = %(sales_order)s")
        values["sales_order"] = filters.get("sales_order")

    return " AND ".join(conditions), values


def get_rows(condition_sql, values):
    query = f"""
        SELECT
			so.name AS sales_order,
			so.delivery_date AS delivery_date,
			so.customer AS customer,
            so.customer_name,
			wo.production_plan,
			wo.status AS work_order_status,
			wo.production_item AS fg_item,
            se.name AS voucher_no,
            # se.work_order,
            CASE 
                WHEN se.purpose = 'Material Issue' THEN se.work_order
                ELSE se.work_order
            END AS work_order,
            se.stock_entry_type,
            sed.item_code AS item_code,
            sed.qty AS qty,
            sed.basic_rate AS rate,
            sed.is_finished_item,
            sed.serial_no AS fg_serial_no,
            sed.basic_rate AS transferred_rate,
            sed.basic_rate AS consumed_rate,
            bo.name AS bom_no,
            wo.qty AS wo_qty,
            wo.production_item AS fg_item,

            -- Aggregate Delivery Notes & Sales Invoices
            (
                SELECT GROUP_CONCAT(DISTINCT dn.name SEPARATOR ', ')
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
                WHERE dni.against_sales_order = so.name
            ) AS delivery_note,
            (
                SELECT GROUP_CONCAT(DISTINCT si.name SEPARATOR ', ')
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
                WHERE sii.sales_order = so.name OR sii.delivery_note IN (
                    SELECT dn.name
                    FROM `tabDelivery Note Item` dni
                    INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
                    WHERE dni.against_sales_order = so.name
                )
            ) AS sales_invoice
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed
            ON sed.parent = se.name
        # INNER JOIN `tabWork Order` wo
        #     ON wo.name = se.work_order AND wo.docstatus = 1
        INNER JOIN `tabWork Order` wo
            ON wo.name = CASE 
                            WHEN se.purpose = 'Material Issue' THEN se.work_order
                            ELSE se.work_order
                        END
            AND wo.docstatus = 1
        LEFT JOIN `tabBOM` bo
            ON bo.name = wo.bom_no
		LEFT JOIN `tabSales Order` so
    		ON so.name = wo.sales_order

        WHERE se.docstatus = 1
        {f" AND {condition_sql}" if condition_sql else ""}
        AND (
            (sed.is_finished_item = 1 AND se.purpose = 'Manufacture') 
            OR (sed.is_finished_item = 0 AND se.purpose IN ('Manufacture', 'Material Issue'))
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
            CASE 
                WHEN se.purpose = 'Material Issue' THEN se.work_order
                ELSE se.work_order
            END AS work_order_key,
            sed.item_code,
            SUM(ABS(sed.qty)) AS transferred_qty
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed
            ON sed.parent = se.name AND sed.is_finished_item = 0
        WHERE
            se.docstatus = 1
            AND se.purpose = 'Material Issue'
            AND (
                se.work_order IN %(work_orders)s OR se.work_order IN %(work_orders)s
            )
            AND sed.item_code IN %(items)s
        GROUP BY work_order_key, sed.item_code
    """, {"work_orders": work_orders, "items": items}, as_dict=True)

    lookup = {(d.work_order_key, d.item_code): d.transferred_qty for d in transfer_data}


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
    fg_groups = {}
    for r in rows:
        if r.is_finished_item:
            key = (r.work_order, r.fg_item, r.fg_serial_no)
            fg_groups[key] = {
                "fg": r,
                "raw_materials": {}
            }

    for r in rows:
        if r.is_finished_item:
            continue

        fg_keys = [k for k in fg_groups if k[0] == r.work_order]
        if not fg_keys:
            continue

        fg_key = fg_keys[0]
        rm_map = fg_groups[fg_key]["raw_materials"]

        if r.item_code not in rm_map:
            rm_map[r.item_code] = {
                "item_code": r.item_code,
                "voucher_no": r.voucher_no,
                "stock_entry_type": r.stock_entry_type,
                "consumed_qty": 0,
                "consumed_value": 0,
                "rate": r.rate or 0,
                "transferred_qty": getattr(r, "transferred_qty", 0)
            }

        rm_map[r.item_code]["consumed_qty"] += r.qty or 0
        rm_map[r.item_code]["consumed_value"] += (r.qty or 0) * (r.rate or 0)

    for fg_key, fg_data in fg_groups.items():
        fg = fg_data["fg"]
        raw_materials = fg_data["raw_materials"]

        # Parent Row
        # === NEW FG BOM LOGIC ===

        # FG BOM Qty = WO Qty
        bom_qty_fg = fg.wo_qty or 0  

        # BOM rate from raw_material_cost
        bom_rate_fg = 0
        if fg.bom_no:
            bom_rate_fg = frappe.db.get_value("BOM", fg.bom_no, "raw_material_cost") or 0

        bom_amount_fg = bom_qty_fg * bom_rate_fg

        # FG Consumption from Stock Entry
        # FG Consumption from Stock Entry including Material Issue
        cons = frappe.db.sql("""
            SELECT 
                SUM(CASE WHEN sed.is_finished_item = 1 THEN sed.qty ELSE 0 END) AS fg_qty,
                SUM(CASE WHEN sed.is_finished_item = 1 THEN se.total_outgoing_value ELSE 0 END) AS fg_value,
                SUM(CASE WHEN sed.is_finished_item = 0 AND se.purpose = 'Material Issue' THEN sed.qty * sed.basic_rate ELSE 0 END) AS raw_material_qty,
                SUM(CASE WHEN sed.is_finished_item = 0 AND se.purpose = 'Material Issue' THEN sed.qty * sed.basic_rate ELSE 0 END) AS raw_material_value
            FROM `tabStock Entry` se
            INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
            WHERE se.docstatus = 1
            AND (se.work_order = %(wo)s OR se.work_order = %(wo)s)
        """, {"wo": fg.work_order}, as_dict=True)

        consumed_qty_fg = (cons[0].fg_qty or 0) + (cons[0].raw_material_qty or 0)
        consumed_value_fg = (cons[0].fg_value or 0) + (cons[0].raw_material_value or 0)


        # Get FG Basic Rate from Stock Entry Detail
        fg_basic_rate = fg.rate or fg.transferred_rate or fg.consumed_rate or 0

        consumed_rate_fg = fg_basic_rate
        transferred_rate_fg = fg_basic_rate

        # Push into FG row
        data.append({
            "indent": 0,
            "sales_order": fg.sales_order,
            "delivery_date": fg.delivery_date,
            "customer": fg.customer,
            "customer_name": fg.customer_name,
            "production_plan": fg.production_plan or "",
            "work_order_status": fg.work_order_status,
            "fg_item": fg.fg_item,
            "fg_serial_no": fg.fg_serial_no,
            "work_order": fg.work_order,
            "bom_no": fg.bom_no,
            "delivery_note": fg.delivery_note,
            "sales_invoice": fg.sales_invoice,

            # NEW FG BOM FIELDS
            "bom_qty": bom_qty_fg,
            # "bom_rate": bom_rate_fg,
            "bom_rate": None,
            "bom_amount": bom_amount_fg,
            "consumed_qty": consumed_qty_fg,
            # "consumed_rate": consumed_rate_fg,
            "consumed_rate": None,
            "consumed_value": consumed_value_fg,
            "consumed_minus_bom_amount": consumed_value_fg - bom_amount_fg,

            # Keep placeholders
            "voucher_no": fg.voucher_no,
            "stock_entry_type": fg.stock_entry_type,
            "rm_item_bom": None,
            "rm_item_consumed": None,
            # "transferred_qty": 0,
            # "transferred_value": 0,
            "transferred_qty": consumed_qty_fg,
            # "transferred_rate": transferred_rate_fg,
            "transferred_rate": None,
            "transferred_value": consumed_value_fg,
            "variance_issue_qty": 0,
            "variance_issue_value": 0,
            "variance_consumption_qty": 0,
            "variance_consumption_value": 0,
        })


        # Child Rows (DEDUPED)
        for item_code, r in raw_materials.items():
            bom_items = bom_cache.get(fg.work_order, {})
            bom_data = bom_items.get(item_code, {})

            bom_qty = bom_data.get("qty", 0)
            bom_rate = bom_data.get("rate", 0)
            bom_amount = bom_qty * bom_rate

            consumed_qty = r["consumed_qty"]
            consumed_value = r["consumed_value"]
            consumed_rate = r["rate"] or 0
            transferred_rate = consumed_rate

            # transferred_qty = r["transferred_qty"]
            # transferred_value = transferred_qty * bom_rate

            # Match transferred = consumed
            transferred_qty = consumed_qty
            transferred_value = consumed_value

            variance_issue_qty = transferred_qty - bom_qty
            variance_issue_value = variance_issue_qty * bom_rate

            variance_consumption_qty = consumed_qty - bom_qty
            variance_consumption_value = variance_consumption_qty * r["rate"]
            prepared_data = {
                "indent": 1,
                "sales_order": fg.sales_order,
                "delivery_date": fg.delivery_date,
                "customer": fg.customer,
                "customer_name": fg.customer_name,
                "production_plan": fg.production_plan or "",
                "work_order_status": fg.work_order_status,
                "fg_item": fg.fg_item,
                "fg_serial_no": fg.fg_serial_no,
                "work_order": fg.work_order,
                "bom_no": fg.bom_no,
                "voucher_no": r["voucher_no"],
                "stock_entry_type": r["stock_entry_type"],
                # "delivery_note": fg.delivery_note,
                # "sales_invoice": fg.sales_invoice,
                "rm_item_bom": item_code if bom_data else None,
                "rm_item_consumed": item_code,
                "bom_qty": bom_qty,
                "bom_rate": bom_rate,
                "bom_amount": bom_amount,
                "transferred_qty": transferred_qty,
                "transferred_rate": transferred_rate,
                "transferred_value": transferred_value,
                "variance_issue_qty": variance_issue_qty,
                "variance_issue_value": variance_issue_value,
                "consumed_qty": consumed_qty,
                "consumed_rate": consumed_rate,
                "consumed_value": consumed_value,
                "variance_consumption_qty": variance_consumption_qty,
                "variance_consumption_value": variance_consumption_value,
                "consumed_minus_bom_amount": consumed_value - bom_amount,
            }
            

            if not item_code or not fg.work_order:
                continue

            sr_details = frappe.db.sql(f"""
                                Select sle.name, 
                                    sle.incoming_rate, 
                                    sle.has_serial_no, 
                                    sle.item_code,
                                    sle.actual_qty,
                                    sle.qty_after_transaction,
                                    sle.posting_date, 
                                    sle.valuation_rate
                                From `tabStock Reconciliation` as sr
                                Left Join  `tabStock Ledger Entry` as sle ON sle.voucher_no = sr.name
                                Where sle.is_cancelled = 0 and sr.work_order = '{fg.work_order}' and sle.item_code = '{item_code}'
                        """, as_dict=1)

            if sr_details:
                if len(sr_details) == 1:
                    sle_data = [abs(flt(row.actual_qty)) for row in sr_details]
                else:
                    sle_data = [abs(flt(row.actual_qty)) for row in sr_details if row.actual_qty < 0]
                frappe.log_error(item_code, sle_data)
                if sle_data:
                    # frappe.log_error("sum log",prepared_data.get("transferred_qty") - abs(sum(sle_data)))
                    prepared_data.update({
                        "transferred_qty" : final_qty,
                        "transferred_value" : final_qty * sr_details[0].get("valuation_rate"),
                        "consumed_qty": final_qty,
                        "consumed_value": final_qty * sr_details[0].get("valuation_rate"),
                        "transferred_rate" : sr_details[0].get("valuation_rate"),
                       
                        "consumed_rate": sr_details[0].get("valuation_rate"),
                        
                    })


                    
                    
            
            data.append(prepared_data)
            


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

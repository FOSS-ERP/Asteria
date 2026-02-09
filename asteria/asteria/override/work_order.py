import frappe
from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder 



class CustomWorkOrder(WorkOrder):
    def update_transferred_qty_for_required_items(self):
        ste = frappe.qb.DocType("Stock Entry")
        ste_child = frappe.qb.DocType("Stock Entry Detail")

        wip_warehouse = self.wip_warehouse

        query = (
        frappe.qb.from_(ste)
            .inner_join(ste_child)
            .on(ste_child.parent == ste.name)
            .select(
                ste_child.item_code,
                ste_child.original_item,
                ste_child.qty,
                ste_child.s_warehouse,
                ste_child.t_warehouse,
            )
            .where(
                (ste.docstatus == 1)
                & (ste.work_order == self.name)
                & (ste.purpose == "Material Transfer for Manufacture")
                & (ste.is_return == 0)
            )
        )

        data = query.run(as_dict=1) or []

        # fosserp changes
        transferred_items = frappe._dict()

        for d in data:
            key = d.original_item or d.item_code
            qty = d.qty or 0

            # Material moved OUT of WIP
            if d.s_warehouse == wip_warehouse and d.t_warehouse != wip_warehouse:
                transferred_items[key] = transferred_items.get(key, 0) - qty

            # Material moved INTO WIP (reduce transferred qty)
            elif d.t_warehouse == wip_warehouse and d.s_warehouse != wip_warehouse:
                transferred_items[key] = transferred_items.get(key, 0) + qty

        # fosserp changes end
        for row in self.required_items:
            row.db_set(
                "transferred_qty",
                transferred_items.get(row.item_code, 0.0),
                update_modified=False
            )
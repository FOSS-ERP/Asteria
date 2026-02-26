import frappe
from frappe import _
from frappe.utils import cstr, flt, get_link_to_form
from asteria.asteria.doctype.reserve_stock.reserve_stock import (
    get_batch_qty_in_warehouse,
    get_reserved_batch_details,
    get_reserved_stock_references,
)


def validate(self, method):
    # validate_reserved_stock_usage(self)
    warn_manufacture_batch_from_work_order(self)


def on_submit(self, method):
    validate_manufacture_batch_from_work_order(self)
    show_serial_no_transaction(self)

def show_serial_no_transaction(self):
    if self.work_order:
        stock_entry_list = frappe.db.get_list("Stock Entry", {"docstatus" : 1, "work_order" : self.work_order}, "name")
        stock_entry_list.append({
            "name" : self.name
        })
        conditions = ''
        if stock_entry_list:
            conditions = " and sbb.voucher_no in {} ".format(
                    "(" + ", ".join([f'"{l.get("name")}"' for l in stock_entry_list]) + ")")

        serial_and_batch_bundle = frappe.db.sql(f"""
                    Select sbe.serial_no, sbb.type_of_transaction, sbb.warehouse, sbb.item_code, sbb.name, sbb.voucher_detail_no
                    From `tabSerial and Batch Bundle` as sbb
                    Left Join `tabSerial and Batch Entry` as sbe ON sbe.parent = sbb.name
                    Where sbb.docstatus < 2 {conditions}
                    Order By sbb.creation
        """, as_dict=1)

        message = """
            <h4>Serial Number Transactions</h4>
            <table style="width:100%; border-collapse: collapse; margin-top:10px;">
                <thead>
                    <tr>
                        <th style="border: 1px solid #d1d8dd; padding: 8px; background-color: #f7fafc;">Serial No</th>
                        <th style="border: 1px solid #d1d8dd; padding: 8px; background-color: #f7fafc;">Inward</th>
                        <th style="border: 1px solid #d1d8dd; padding: 8px; background-color: #f7fafc;">Outward</th>
                    </tr>
                </thead>
                <tbody>
        """

        for row in serial_and_batch_bundle:
            sted_data = []
            has_serial_no_replaced = False
            style = ''
            inward_warehouse = ""
            outward_warehouse = ""
            if row.type_of_transaction == "Outward":
                outward_warehouse = row.warehouse
            if row.type_of_transaction == "Inward":
                inward_warehouse = row.warehouse
            if row.voucher_detail_no:
                sted_data = frappe.db.sql("""Select 
                                                sed.has_serial_no_replaced, se.from_bom 
                                            From 
                                                `tabStock Entry Detail`  as sed
                                            Left Join 
                                                `tabStock Entry` as se ON se.name = sed.parent
                                            Where 
                                                sed.name = '{0}'    
                                            """.format(row.voucher_detail_no), as_dict=1)
            if sted_data:
                has_serial_no_replaced = sted_data[0].get("has_serial_no_replaced")
                from_bom = sted_data[0].get("from_bom")
                if has_serial_no_replaced or not from_bom:
                    style = "color: red;"
            message += f"""
                <tr>
                    <td style="border: 1px solid #d1d8dd; padding: 8px; {style}">{row.serial_no or ""}</td>
                    <td style="border: 1px solid #d1d8dd; padding: 8px; {style}">{inward_warehouse}</td>
                    <td style="border: 1px solid #d1d8dd; padding: 8px; {style}">{outward_warehouse}</td>
                </tr>
            """

        message += """
                </tbody>
            </table>
        """

        frappe.msgprint(message)


@frappe.whitelist()
def get_serial_no(serial_and_batch_bundle):
    ssb_serial_no = frappe.get_doc("Serial and Batch Bundle", serial_and_batch_bundle)
    serial_no_list = [
        row.serial_no for row in ssb_serial_no.entries
    ]
    return serial_no_list


@frappe.whitelist()
def cancel_stock_entry_in_rq(stock_entry):
    frappe.enqueue(
            cancel_stock_entry, stock_entry=stock_entry, queue="long", timeout=7200
        )
    return True

def cancel_stock_entry(stock_entry):
    doc = frappe.get_doc("Stock Entry", stock_entry)
    doc.cancel()


@frappe.whitelist()
def submit_stock_entry_in_rq(stock_entry):
    frappe.enqueue(
            submit_stock_entry, stock_entry=stock_entry, queue="long", timeout=7200
        )
    return True

def submit_stock_entry(stock_entry):
    doc = frappe.get_doc("Stock Entry", stock_entry)
    doc.submit()


def warn_manufacture_batch_from_work_order(self):
    """Show a warning (msgprint) on save/draft if any raw-material row
    uses a batch that is invalid for the Work Order. Allows saving."""
    _check_manufacture_batches(self, block=False)


def validate_manufacture_batch_from_work_order(self):
    """Block submission of a Manufacture Stock Entry if any raw-material row
    uses a batch that was NOT transferred via Material Transfer for Manufacture
    for the same Work Order."""
    _check_manufacture_batches(self, block=True)


def _check_manufacture_batches(self, block=True):
    """Core check logic. If block=True, frappe.throw; if False, frappe.msgprint."""

    # Check if batch validation is enabled in Stock Settings
    if not frappe.db.get_single_value("Stock Settings", "enable_batch_validation_for_manufacture", 0) and block:
        return

    if self.stock_entry_type != "Manufacture" or not self.work_order:
        return

    # 1. Get WIP warehouse from Work Order
    wip_warehouse = frappe.db.get_value("Work Order", self.work_order, "wip_warehouse")
    if not wip_warehouse:
        return

    # 2. Get all submitted Material Transfer for Manufacture entries for this WO
    material_transfer_entries = frappe.get_all(
        "Stock Entry",
        {
            "stock_entry_type": "Material Transfer for Manufacture",
            "work_order": self.work_order,
            "docstatus": 1,
        },
        pluck="name",
    )

    if not material_transfer_entries:
        return

    # 3. Collect valid batches from those transfers
    valid_batches = _get_valid_batches_for_work_order(
        material_transfer_entries, self.work_order
    )

    if not valid_batches:
        return

    # 4. Validate each raw-material row
    for row in self.items:
        if row.get("is_finished_item") or row.get("is_scrap_item"):
            continue

        batch_no = cstr(row.get("batch_no")).strip()
        if not batch_no:
            continue

        # 4a. Batch must come from a MTfM of this Work Order
        item_valid = valid_batches.get(cstr(row.item_code).strip(), set())

        if batch_no not in item_valid:
            msg = _(
                "Row #{0}: Batch {1} for item {2} is not from the "
                "Material Transfer for Manufacture entries of Work Order {3}.<br><br>"
                "Only batches transferred for this Work Order cycle are allowed."
            ).format(
                row.idx,
                frappe.bold(get_link_to_form("Batch", batch_no)),
                frappe.bold(get_link_to_form("Item", row.item_code)),
                frappe.bold(get_link_to_form("Work Order", self.work_order)),
            )
            if block:
                frappe.throw(msg, title=_("Invalid Batch for Manufacture"))
            else:
                frappe.msgprint(msg, title=_("Invalid Batch for Manufacture"), indicator="orange")

        # 4b. Batch must currently exist in the WIP warehouse
        #     (rejected batches transferred out of WIP will have 0 qty)
        batch_qty = _get_batch_qty_in_warehouse(batch_no, wip_warehouse)
        if flt(batch_qty) <= 0:
            msg = _(
                "Row #{0}: Batch {1} for item {2} is not available in "
                "WIP Warehouse {3} of Work Order {4}.<br><br>"
                "The batch may have been rejected and transferred out. "
                "Please use a batch that is currently in the WIP Warehouse."
            ).format(
                row.idx,
                frappe.bold(get_link_to_form("Batch", batch_no)),
                frappe.bold(get_link_to_form("Item", row.item_code)),
                frappe.bold(wip_warehouse),
                frappe.bold(get_link_to_form("Work Order", self.work_order)),
            )
            if block:
                frappe.throw(msg, title=_("Batch Not in WIP Warehouse"))
            else:
                frappe.msgprint(msg, title=_("Batch Not in WIP Warehouse"), indicator="orange")


def _get_valid_batches_for_work_order(material_transfer_entries, work_order):
    """Return { item_code: set(batch_no, …) } collected from the given
    Material Transfer for Manufacture stock entries."""

    valid = {}  # { item_code: set() }

    entry_list = ", ".join([f'"{e}"' for e in material_transfer_entries])

    # --- Source 1: Serial and Batch Bundle entries ---
    sbb_batches = frappe.db.sql(
        f"""
        SELECT sbb.item_code, sbe.batch_no
        FROM `tabSerial and Batch Bundle` AS sbb
        INNER JOIN `tabSerial and Batch Entry` AS sbe ON sbe.parent = sbb.name
        WHERE
            sbb.docstatus = 1
            AND sbb.has_batch_no = 1
            AND sbe.batch_no IS NOT NULL
            AND sbb.voucher_no IN ({entry_list})
        """,
        as_dict=True,
    )

    for r in sbb_batches:
        valid.setdefault(cstr(r.item_code).strip(), set()).add(cstr(r.batch_no).strip())

    # --- Source 2: Stock Entry Detail (use_serial_batch_fields) ---
    sed_batches = frappe.db.sql(
        f"""
        SELECT sed.item_code, sed.batch_no
        FROM `tabStock Entry Detail` AS sed
        WHERE
            sed.parent IN ({entry_list})
            AND sed.batch_no IS NOT NULL
            AND sed.batch_no != ''
        """,
        as_dict=True,
    )

    for r in sed_batches:
        valid.setdefault(cstr(r.item_code).strip(), set()).add(cstr(r.batch_no).strip())

    return valid


def _get_batch_qty_in_warehouse(batch_no, warehouse):
    """Return the current stock balance of a batch in a specific warehouse
    using the Stock Ledger Entry (single source of truth for stock)."""

    qty = frappe.db.sql(
        """
        SELECT IFNULL(SUM(actual_qty), 0)
        FROM `tabStock Ledger Entry`
        WHERE
            batch_no = %s
            AND warehouse = %s
            AND is_cancelled = 0
        """,
        (batch_no, warehouse),
    )
    return flt(qty[0][0]) if qty else 0


def validate_reserved_stock_usage(self):
    """Validate reserved serial and warehouse-wise batch floor in Stock Entry rows."""
    serial_nos = []
    outward_batch_qty = {}

    for row in self.items:
        batch_no = cstr(row.get("batch_no")).strip()
        source_warehouse = cstr(row.get("s_warehouse")).strip()
        if batch_no and source_warehouse and flt(row.get("qty")) > 0:
            key = (batch_no, source_warehouse)
            outward_batch_qty[key] = outward_batch_qty.get(key, 0) + flt(row.get("qty"))

        serial_text = cstr(row.get("serial_no")).strip()
        if serial_text:
            serial_nos.extend([s.strip() for s in serial_text.split("\n") if s.strip()])

    if not serial_nos and not outward_batch_qty:
        return

    reserved_refs = get_reserved_stock_references(serial_nos=serial_nos, batch_nos=[])
    reserved_serials = reserved_refs.get("serial_no", {})
    violating_batches = {}

    if outward_batch_qty:
        batch_details = get_reserved_batch_details(
            batch_nos=[k[0] for k in outward_batch_qty.keys()],
            warehouses=[k[1] for k in outward_batch_qty.keys()],
        )
        for (batch_no, warehouse), outgoing_qty in outward_batch_qty.items():
            reserved_detail = batch_details.get((batch_no, warehouse))
            if not reserved_detail:
                continue

            reserved_qty = flt(reserved_detail.get("reserved_qty"))
            current_qty = get_batch_qty_in_warehouse(batch_no, warehouse)
            projected_qty = current_qty - flt(outgoing_qty)
            if projected_qty < reserved_qty:
                violating_batches[(batch_no, warehouse)] = {
                    "reserved_qty": reserved_qty,
                    "current_qty": current_qty,
                    "outgoing_qty": outgoing_qty,
                    "reserve_stocks": reserved_detail.get("reserve_stocks", []),
                }

    if not reserved_serials and not violating_batches:
        return

    message = [_("Reserved Serial / Batch validation failed.")]
    if reserved_serials:
        message.append(
            _("Reserved Serial No: {0}").format(
                ", ".join(frappe.bold(get_link_to_form("Serial No", s)) for s in sorted(reserved_serials.keys()))
            )
        )

    if violating_batches:
        for (batch_no, warehouse), data in sorted(violating_batches.items()):
            message.append(
                _(
                    "Batch {0} in warehouse {1} cannot be used for qty {2}. "
                    "Current qty: {3}, Reserved qty: {4}, Remaining after transaction: {5}."
                ).format(
                    frappe.bold(get_link_to_form("Batch", batch_no)),
                    frappe.bold(warehouse),
                    frappe.bold(flt(data.get("outgoing_qty"))),
                    frappe.bold(flt(data.get("current_qty"))),
                    frappe.bold(flt(data.get("reserved_qty"))),
                    frappe.bold(flt(data.get("current_qty")) - flt(data.get("outgoing_qty"))),
                )
            )

    reserve_stock_links = sorted(
        set(
            [
                *reserved_serials.values(),
                *[
                    reserve_stock
                    for row in violating_batches.values()
                    for reserve_stock in row.get("reserve_stocks", [])
                ],
            ]
        )
    )
    if reserve_stock_links:
        message.append(
            _("Reserve Stock document: {0}").format(
                ", ".join(
                    frappe.bold(get_link_to_form("Reserve Stock", reserve_stock))
                    for reserve_stock in reserve_stock_links
                )
            )
        )

    frappe.throw("<br>".join(message))
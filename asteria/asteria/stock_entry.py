import frappe


def on_submit(self, method):
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
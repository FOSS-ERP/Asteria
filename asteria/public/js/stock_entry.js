frappe.ui.form.on("Stock Entry", {
    refresh : (frm)=>{
        class CustomSerialBatchPackageSelector extends erpnext.SerialBatchPackageSelector {
            get_auto_data() {
                console.log("console")
                let { qty, based_on } = this.dialog.get_values();
        
                // if (this.item.serial_and_batch_bundle || this.item.rejected_serial_and_batch_bundle) {
                //     if (this.qty && qty === Math.abs(this.qty)) {
                //         return;
                //     }
                // }
        
                if (this.item.serial_no || this.item.batch_no) {
                    return;
                }
        
                if (!based_on) {
                    based_on = "FIFO";
                }
        
                let warehouse = this.item.warehouse || this.item.s_warehouse;
                if (this.item?.is_rejected) {
                    warehouse = this.item.rejected_warehouse;
                }
        
                if (qty) {
                    frappe.call({
                        method: "asteria.asteria.override.serial_and_batch_bundle.get_auto_data",
                        args: {
                            doc : this.frm.doc,
                            item_code: this.item.item_code,
                            warehouse: warehouse,
                            has_serial_no: this.item.has_serial_no,
                            has_batch_no: this.item.has_batch_no,
                            qty: qty,
                            based_on: based_on,
                            posting_date: this.frm.doc.posting_date,
                            posting_time: this.frm.doc.posting_time,
                        },
                        callback: (r) => {
                            if (r.message) {
                                console.log(r.message)

                                this.dialog.fields_dict.entries.df.data = r.message;
                                this.dialog.fields_dict.entries.grid.refresh();
                            }
                        },
                    });
                }
            }
        }
        erpnext.SerialBatchPackageSelector = CustomSerialBatchPackageSelector;
    }
});
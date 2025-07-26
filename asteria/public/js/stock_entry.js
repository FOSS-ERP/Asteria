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

            update_serial_no() {
                const rowIdx = this.dialog.fields_dict["item_row_number"].value;
                if (!rowIdx) return;
                const item = this.frm.doc.items.find(e => e.idx == rowIdx);
            
                if (!item) {
                    frappe.throw(`No item found at row ${rowIdx}`);
                }
            
                if (!item.serial_no && !item.serial_and_batch_bundle) {
                    frappe.throw(`Serial No not available in row ${item.idx} for item ${item.item_code}`);
                }
                let serialNos = ''
                if (item.serial_no){
                    serialNos = item.serial_no
                        .split(/\r?\n/)
                        .map(line => `${this.item.item_code}${line}`)
                        .join('\n');
                    this.dialog.set_value("upload_serial_nos", serialNos);
                }else{

                    frappe.call({
                        method: "asteria.asteria.stock_entry.get_serial_no",
                        args: {
                            serial_and_batch_bundle: item.serial_and_batch_bundle
                        },
                        callback:(b)=>{
                            if (!b.message){
                                frappe.throw(`Serial No not available in row ${item.idx} for item ${item.item_code}`);
                            }
                            serialNos = b.message.map(line => `${this.item.item_code}${line}`).join('\n');
                            this.dialog.set_value("upload_serial_nos", serialNos);
                        }
                    })
        
                }
            
                
            }

            get_attach_field() {
                console.log("Activated")
                let me = this;
                let label = this.item?.has_serial_no ? __("Serial Nos") : __("Batch Nos");
                let primary_label = this.bundle ? __("Update") : __("Add");
        
                if (this.item?.has_serial_no && this.item?.has_batch_no) {
                    label = __("Serial Nos / Batch Nos");
                }
        
                let fields = [];
                if (this.item.has_serial_no) {
                    fields.push({
                        fieldtype: "Check",
                        label: __("Enter Manually"),
                        fieldname: "enter_manually",
                        default: 1,
                        depends_on: "eval:doc.import_using_csv_file !== 1",
                        change() {
                            if (me.dialog.get_value("enter_manually")) {
                                me.dialog.set_value("import_using_csv_file", 0);
                            }
                        },
                    });
                }
        
                fields = [
                    ...fields,
                    {
                        fieldtype: "Check",
                        label: __("Import Using CSV file"),
                        fieldname: "import_using_csv_file",
                        depends_on: "eval:doc.enter_manually !== 1",
                        default: !this.item.has_serial_no ? 1 : 0,
                        change() {
                            if (me.dialog.get_value("import_using_csv_file")) {
                                me.dialog.set_value("enter_manually", 0);
                            }
                        },
                    },
                    {
                        fieldtype: "Section Break",
                        depends_on: "eval:doc.import_using_csv_file === 1",
                        label: __("{0} {1} via CSV File", [primary_label, label]),
                    },
                    {
                        fieldtype: "Button",
                        fieldname: "download_csv",
                        label: __("Download CSV Template"),
                        click: () => this.download_csv_file(),
                    },
                    {
                        fieldtype: "Column Break",
                    },
                    {
                        fieldtype: "Attach",
                        fieldname: "attach_serial_batch_csv",
                        label: __("Attach CSV File"),
                        onchange: () => this.upload_csv_file(),
                    },
                ];
        
                if (this.item?.has_serial_no) {
                    fields = [
                        ...fields,
                        {
                            fieldtype: "Section Break",
                            label: __("{0} {1} Manually", [primary_label, label]),
                            depends_on: "eval:doc.enter_manually === 1",
                        },
                        {
                            fieldtype: "Data",
                            label: __("Serial No Range"),
                            fieldname: "serial_no_range",
                            depends_on: "eval:doc.enter_manually === 1 && !doc.serial_no_series",
                            description: __('"SN-01::10" for "SN-01" to "SN-10"'),
                            onchange: () => {
                                this.set_serial_nos_from_range();
                            },
                        },
                        {
                            fieldtype: "Int",
                            label: __("Item Row Number"),
                            fieldname: "item_row_number",
                            onchange:()=>{
                                this.update_serial_no()
                            }
                        },
                    ];
                }
        
                if (this.item?.has_serial_no) {
                    fields = [
                        ...fields,
                        {
                            fieldtype: "Column Break",
                            depends_on: "eval:doc.enter_manually === 1",
                        },
                        {
                            fieldtype: "Small Text",
                            label: __("Enter Serial Nos"),
                            fieldname: "upload_serial_nos",
                            depends_on: "eval:doc.enter_manually === 1",
                            description: __("Enter each serial no in a new line"),
                        },
                    ];
                }
        
                return fields;
            }
        }
        erpnext.SerialBatchPackageSelector = CustomSerialBatchPackageSelector;
    }
});
frappe.ui.form.on("Sales Order", {
    refresh:(frm)=>{
        if(frm.doc.docstatus == 1){
            frm.add_custom_button(__("Production Plan"), function(){
                frappe.model.open_mapped_doc({
                    method: "asteria.asteria.api.create_production_plan",
                    frm: cur_frm,
                });
            },__("Create"))
        }
    }
})

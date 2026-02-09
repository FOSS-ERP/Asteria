frappe.ui.form.on("Material Request", {
    refresh(frm) {
        if (!frm.doc.__islocal && frm.doc.material_request_type != 'Purchase') {
            frm.add_custom_button(
                __("Material Request (Purchase)"),
                function () {
                    frappe.model.open_mapped_doc({
                        method: "asteria.asteria.api.make_purchase_material_request",
                        frm: frm
                    });
                },
                __("Create")
            );
        }
        if (!frm.doc.__islocal && frm.doc.material_request_type === "Manufacture") {
            frappe.call({
                method : "asteria.asteria.doc_events.material_request.check_if_production_plan_exists",
                args : {
                    name : frm.doc.name
                },
                callback : (r)=>{
                    if(!r.message){
                        frm.add_custom_button(
                            __("Production Plan"),
                            () => {
                                frappe.call({
                                    method: "asteria.asteria.doc_events.material_request.create_production_plan",
                                    args: {
                                        doc: frm.doc
                                    },
                                    freeze: true,
                                    freeze_message: __("Creating Production Plan..."),
            
                                    callback: function (r) {
                                        frm.refresh()
                                    }
                                });
                            },
                            __("Create")
                        );
                    }
                }
            })
        }   
    }
});
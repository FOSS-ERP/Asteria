frappe.ui.form.on("Material Request", {
    refresh(frm) {
        if (!frm.doc.__islocal) {
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
    }
});
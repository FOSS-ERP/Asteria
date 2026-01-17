frappe.ui.form.on("Production Plan", {
    refresh:function(frm) {
        console.log("Hello")
        frm.remove_custom_button("Material Request", "Create")
        if (frm.doc.status !== "Completed") {
            if (
                frm.doc.mr_items &&
                frm.doc.mr_items.length &&
                !["Material Requested", "Closed"].includes(frm.doc.status)
            ) {
                frm.add_custom_button(
                    __("Material Request"),
                    () => {
                        frm.events.create_material_request(frm, 0);
                    },
                    __("Create")
                );
                has_create_buttons = true;
            }
        }
    }
})

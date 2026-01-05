frappe.ui.form.on("Job Card", {
    refresh:(frm)=>{
        frm.add_custom_button(__("Stock Entry"), function(){
            frappe.model.open_mapped_doc({
                method: "asteria.asteria.doc_events.job_card.create_stock_entry",
                frm: cur_frm,
		    });
        },__("Create"))
    }
})
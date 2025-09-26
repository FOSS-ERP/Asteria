
frappe.listview_settings["H2H Log"] = {
	onload(listview) {
        console.log("hh")
		listview.page.add_inner_button(__('Check Status'), function() {
            // Your button action here
            frappe.call({
                method : "asteria.asteria.doc_events.check_sftp_payment_status.check_status",
                args:{

                },
                callback:(r)=>{
                    
                }
            })
        });
	}
};

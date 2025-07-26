frappe.ui.form.on("Expense Claim", {
    refresh:(frm)=>{

    }
})

frappe.ui.form.on("Expense Claim Detail", {
    distance : (frm, cdt, cdn)=>{
        console.log("hhhh")
        let d = locals[cdt][cdn]
        console.log(d.distance)
        if (!d.distance) return;

        frappe.call({
            method : "frappe.client.get_value",
            args :{
                doctype: "Expense Claim Type",
				filters: { name: d.expense_type },
				fieldname: "rate_per_km",
            },
            callback:(r)=>{
                if(r.message.rate_per_km){
                    frappe.model.set_value(cdt, cdn, "amount", (d.distance * r.message.rate_per_km))
                    frm.refresh_field('expenses')
                }
            }
        })
    }
})
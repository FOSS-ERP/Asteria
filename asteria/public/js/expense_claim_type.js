frappe.ui.form.on("Expense Claim Type", {
    refresh:(frm)=>{
        console.log("cha")
        if(frm.doc.is_travel_type){
            frm.set_df_property("rate_per_km", "hidden", 0);
            frm.set_df_property("rate_per_km", "reqd", 1);
        }else{
            frm.set_df_property("rate_per_km", "hidden", 1);
            frm.set_value("rate_per_km", 0)
        }        
    },
    is_travel_type:(frm)=>{
        if(frm.doc.is_travel_type){
            frm.set_df_property("rate_per_km", "hidden", 0);
            frm.set_df_property("rate_per_km", "reqd", 1);
        }else{
            frm.set_df_property("rate_per_km", "hidden", 1);
            frm.set_value("rate_per_km", 0)
        }
    }
})
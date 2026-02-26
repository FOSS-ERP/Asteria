// Copyright (c) 2026, Asteria and contributors
// For license information, please see license.txt

frappe.ui.form.on("Return Material Authorization", {	
	validate(frm) {
		if(frm.doc.data_fyvuu && frm.doc.rate) {
			calculate_total_amount(frm);	
		}
	},
	refresh(frm) {
		frm.set_query("part_number", function(doc) {
			if (doc.purchase_order_number) {
				return {
					query: "asteria.asteria.doctype.return_material_authorization.return_material_authorization.get_items_from_po",
					filters: {
						po: doc.purchase_order_number
					}
				};
			}
		});
	},
	data_fyvuu:function(frm) {
		if(frm.doc.data_fyvuu && frm.doc.rate) {
			calculate_total_amount(frm);	
		}
	},
	part_number(frm) {
		// When part_number is selected, fetch clean description from Item master and rate from PO
		if (!frm.doc.part_number) {
			frm.set_value("part_description", "");
			frm.set_value("rate", 0);
			frm.set_value("purchase_order_item", "");
			return;
		}

		// Fetch description from Item master
		frappe.db
			.get_value("Item", frm.doc.part_number, ["description", "item_name"])
			.then((r) => {
				const item = r.message || {};
				let description = item.description || item.item_name || "";

				// Strip HTML tags like <p>...</p> before setting
				if (description) {
					if (frappe.utils && frappe.utils.strip_html) {
						description = frappe.utils.strip_html(description);
					} else {
						description = description.replace(/<[^>]*>/g, "").trim();
					}
				}

				frm.set_value("part_description", description || "");
			});

		// Fetch rate from Purchase Order if PO is selected
		if (frm.doc.purchase_order_number && frm.doc.part_number) {
			frappe.call({
				method: "asteria.asteria.doctype.return_material_authorization.return_material_authorization.get_item_rate_from_po",
				args: {
					po: frm.doc.purchase_order_number,
					item_code: frm.doc.part_number
				},
				callback: (r) => {
					if (r.message) {
						if (r.message.rate) {
							frm.set_value("rate", r.message.rate);
						}
						if (r.message.purchase_order_item) {
							frm.set_value("purchase_order_item", r.message.purchase_order_item);
						}
					}
				}
			});
		}
	},

	purchase_order_number(frm) {
		if (frm.doc.purchase_order_number) {
			frm.set_query("part_number", function(doc) {
				if (doc.purchase_order_number) {
					return {
						query: "asteria.asteria.doctype.return_material_authorization.return_material_authorization.get_items_from_po",
						filters: {
							po: doc.purchase_order_number
						}
					};
				}
			});
		}
	}
});
function calculate_total_amount(frm) {
	frm.set_value("value", frm.doc.data_fyvuu * frm.doc.rate);
}
// Copyright (c) 2026, Viral and contributors
// For license information, please see license.txt

function toggle_qty_editable_for_row(frm, cdn, editable) {
	const grid_row = frm.fields_dict.table_zbqd?.grid?.grid_rows_by_docname?.[cdn];
	if (!grid_row) return;

	grid_row.toggle_editable("qty", editable);
	if (grid_row.grid_form?.fields_dict?.qty) {
		grid_row.grid_form.fields_dict.qty.df.read_only = editable ? 0 : 1;
		grid_row.grid_form.refresh_field("qty");
	}
}

frappe.ui.form.on("Reserve Stock", {
	refresh(frm) {
		(frm.doc.table_zbqd || []).forEach((row) => {
			toggle_qty_editable_for_row(frm, row.name, !row.serial_no);
		});

		if (!frm.is_new() && frm.doc.docstatus === 1 && frm.doc.status !== "Unreserved") {
			frm.add_custom_button(__("Unreserve"), () => {
				frappe.confirm(__("Are you sure you want to mark this Reserve Stock as Unreserved?"), () => {
					frappe.call({
						method: "asteria.asteria.doctype.reserve_stock.reserve_stock.mark_as_unreserved",
						args: { name: frm.doc.name },
						callback: () => frm.reload_doc(),
					});
				});
			});
		}
	},

	item_code(frm) {
		const item_code = frm.doc.item_code;

		if (!item_code) {
			frm.set_value("item_name", "");
			frm.set_value("has_serial_no", 0);
			frm.set_value("has_batch_no", 0);
			return;
		}

		frappe.db.get_value("Item", item_code, ["item_name", "has_serial_no", "has_batch_no"]).then((r) => {
			const item = r.message || {};
			frm.set_value("item_name", item.item_name || "");
			frm.set_value("has_serial_no", item.has_serial_no ? 1 : 0);
			frm.set_value("has_batch_no", item.has_batch_no ? 1 : 0);
		});
	},
});

frappe.ui.form.on("Serial and Batch Entry", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		toggle_qty_editable_for_row(frm, cdn, !row.serial_no);
	},

	serial_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.serial_no) {
			toggle_qty_editable_for_row(frm, cdn, true);
			frappe.model.set_value(cdt, cdn, "warehouse", "");
			return;
		}

		frappe.model.set_value(cdt, cdn, "qty", 1);
		toggle_qty_editable_for_row(frm, cdn, false);

		frappe.db.get_value("Serial No", row.serial_no, "warehouse").then((r) => {
			const warehouse = (r.message && r.message.warehouse) || "";
			frappe.model.set_value(cdt, cdn, "warehouse", warehouse);
		});
	},

	qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.serial_no && row.qty !== 1) {
			frappe.model.set_value(cdt, cdn, "qty", 1);
		}
	},
});

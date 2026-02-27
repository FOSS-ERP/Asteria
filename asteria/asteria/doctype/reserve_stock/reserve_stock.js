// Copyright (c) 2026, Viral and contributors
// For license information, please see license.txt

function toggle_qty_editable_for_row(frm, cdn, editable) {
	const grid_row = frm.fields_dict.items?.grid?.grid_rows_by_docname?.[cdn];
	if (!grid_row) return;

	grid_row.toggle_editable("qty", editable);
	if (grid_row.grid_form?.fields_dict?.qty) {
		grid_row.grid_form.fields_dict.qty.df.read_only = editable ? 0 : 1;
		grid_row.grid_form.refresh_field("qty");
	}
}

frappe.ui.form.on("Reserve Stock", {
	refresh(frm) {
		// Filter Serial No and Batch No in child table by Item Code
		frm.set_query("serial_no", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row.item_code) {
				return {};
			}
			return {
				filters: {
					item_code: row.item_code,
					status: "Active",
				},
			};
		});

		frm.set_query("batch_no", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row.item_code) {
				return {};
			}
			return {
				filters: {
					item: row.item_code,
					disabled: 0,
				},
			};
		});

		(frm.doc.items || []).forEach((row) => {
			toggle_qty_editable_for_row(frm, row.name, !row.serial_no);
		});

		if (!frm.is_new() && frm.doc.docstatus === 1) {
			const has_reserved_row = (frm.doc.items || []).some(
				(row) => row.status !== "Unreserved"
			);
			if (!has_reserved_row) return;

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

		// Dynamic Warehouse filter per row based on selected Serial / Batch availability
		frm.set_query("warehouse", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			const allowed = row._allowed_warehouses || [];

			// If we have a computed allowed list, restrict to those warehouses.
			if (allowed.length) {
				return {
					filters: [
						["Warehouse", "name", "in", allowed],
						["Warehouse", "is_group", "=", 0],
					],
				};
			}

			// Fallback: any non-group warehouse
			return {
				filters: {
					is_group: 0,
				},
			};
		});
	},
});

function update_available_qty_for_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.batch_no || !row.warehouse) {
		frappe.model.set_value(cdt, cdn, "available_qty", 0);
		return;
	}

	frappe.call({
		method: "asteria.asteria.doctype.reserve_stock.reserve_stock.get_batch_qty_in_warehouse",
		args: {
			batch_no: row.batch_no,
			warehouse: row.warehouse,
			item_code: row.item_code,
		},
		callback: (r) => {
			console.log(r);
			if (r.message) {
				frappe.model.set_value(cdt, cdn, "available_qty", r.message || 0);
			}
		},
	});
}

function update_allowed_warehouses_for_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	// If neither serial nor batch is selected, clear any restrictions.
	if (!row.serial_no && !row.batch_no) {
		row._allowed_warehouses = [];
		return;
	}

	frappe.call({
		method: "asteria.asteria.doctype.reserve_stock.reserve_stock.get_available_warehouses_for_reserve_row",
		args: {
			item_code: row.item_code,
			serial_no: row.serial_no,
			batch_no: row.batch_no,
		},
		callback: (r) => {
			if (r.exc) return;

			const allowed = r.message || [];
			row._allowed_warehouses = allowed;

			// Auto-set warehouse if only one option is available.
			if (allowed.length === 1) {
				frappe.model.set_value(cdt, cdn, "warehouse", allowed[0]);
			} else if (row.warehouse && allowed.length && !allowed.includes(row.warehouse)) {
				// Clear warehouse if current value is not in the allowed list.
				frappe.model.set_value(cdt, cdn, "warehouse", "");
			}

			// After updating allowed warehouses, recompute available qty if batch+warehouse are set.
			update_available_qty_for_row(frm, cdt, cdn);
		},
	});
}

frappe.ui.form.on("Stock Reservation Items", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		toggle_qty_editable_for_row(frm, cdn, !row.serial_no);
	},

	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const item_code = row.item_code;

		if (!item_code) {
			frappe.model.set_value(cdt, cdn, "item_name", "");
			frappe.model.set_value(cdt, cdn, "has_serial_no", 0);
			frappe.model.set_value(cdt, cdn, "has_batch_no", 0);
			return;
		}

		frappe.db
			.get_value("Item", item_code, ["item_name", "has_serial_no", "has_batch_no"])
			.then((r) => {
				const item = r.message || {};
				frappe.model.set_value(cdt, cdn, "item_name", item.item_name || "");
				frappe.model.set_value(cdt, cdn, "has_serial_no", item.has_serial_no ? 1 : 0);
				frappe.model.set_value(cdt, cdn, "has_batch_no", item.has_batch_no ? 1 : 0);
			});

		// Reset allowed warehouses when item changes.
		row._allowed_warehouses = [];
	},

	batch_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		// Recompute allowed warehouses whenever batch changes.
		update_allowed_warehouses_for_row(frm, cdt, cdn);

		// Available qty will be updated as part of the callback if warehouse is set.
		if (!row.batch_no || !row.warehouse) {
			frappe.model.set_value(cdt, cdn, "available_qty", 0);
		}
	},

	serial_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.serial_no) {
			toggle_qty_editable_for_row(frm, cdn, true);

			// When serial is cleared, refresh allowed warehouses based on batch only.
			update_allowed_warehouses_for_row(frm, cdt, cdn);
			return;
		}

		frappe.model.set_value(cdt, cdn, "qty", 1);
		toggle_qty_editable_for_row(frm, cdn, false);

		// Recompute allowed warehouses when a serial is selected.
		update_allowed_warehouses_for_row(frm, cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.serial_no && row.qty !== 1) {
			frappe.model.set_value(cdt, cdn, "qty", 1);
		}
	},

	warehouse(frm, cdt, cdn) {
		// Whenever warehouse changes manually, recompute available qty for the chosen batch/warehouse.
		update_available_qty_for_row(frm, cdt, cdn);
	},
});

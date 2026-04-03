// Copyright (c) 2026, Viral and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Movement"] = {
	onload: function (report) {
		report.page.add_inner_button(__("Download Excel with Colors"), function () {
			let filters = report.get_filter_values(true);
			if (!filters) return;

			frappe.call({
				method: "asteria.asteria.report.stock_movement.stock_movement.enqueue_excel_download",
				args: { filters: filters },
				callback: function () {
					frappe.msgprint(
						__("Your Excel file is being generated in the background. You will receive a download link once it is ready."),
						__("Processing")
					);
				},
			});
		});
	},

	"filters": [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Link",
			options: "Batch",
			get_query: () => {
				let item = frappe.query_report.get_filter_value("item_code");
				return item ? { filters: { item: item } } : {};
			},
		},
		{
			fieldname: "serial_no",
			label: __("Serial No"),
			fieldtype: "Link",
			options: "Serial No",
			get_query: () => {
				let item = frappe.query_report.get_filter_value("item_code");
				return item ? { filters: { item_code: item } } : {};
			},
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		let formatted = default_formatter(value, row, column, data);
		if (!data || data.txn_type === undefined) return formatted;

		let bg, fg;
		if (data.txn_type === "Inward") {
			// Green — genuine purchase / receipt
			bg = "#d4edda"; fg = "#155724";
		} else if (data.txn_type === "") {
			// Summary row — neutral blue-grey
			bg = "#e8f0fe"; fg = "#1a237e";
		} else {
			// Any movement (Transfer, Manufacture, Delivery, Issue…) — amber
			bg = "#fff3cd"; fg = "#856404";
		}

		return `<div style="background:${bg}; color:${fg}; margin:-4px -8px; padding:4px 8px;">${formatted ?? ""}</div>`;
	},
};

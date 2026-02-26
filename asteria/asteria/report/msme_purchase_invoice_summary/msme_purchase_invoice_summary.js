// Copyright (c) 2026, Viral and contributors
// For license information, please see license.txt

frappe.query_reports["MSME Purchase Invoice Summary"] = {
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
			label: __("Purchase Invoice From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Purchase Invoice To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "purchase_invoice",
			label: __("Purchase Invoice"),
			fieldtype: "Link",
			options: "Purchase Invoice",
		},
		{
			fieldname: "mode_of_payment",
			label: __("Payment Mode"),
			fieldtype: "Link",
			options: "Mode of Payment",
		},
		{
			fieldname: "payment_status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: "\nAll\nOn Time\nDelay",
			default: "All",
		},
	]
};

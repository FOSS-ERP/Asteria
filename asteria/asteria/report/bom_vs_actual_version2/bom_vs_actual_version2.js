// Copyright (c) 2026, Viral and contributors
// For license information, please see license.txt

frappe.query_reports["BOM Vs Actual Version2"] = {
	"filters": [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.month_start()
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.month_end()
        },
        {
            fieldname: "work_order",
            label: __("Work Order"),
            fieldtype: "Link",
            options: "Work Order",

            on_change: function () {
                const work_order = this.get_value();

                const from_filter = frappe.query_report.get_filter('from_date');
                const to_filter = frappe.query_report.get_filter('to_date');

                if (work_order) {
                    // Disable and clear date filters
                    from_filter.set_value('');
                    to_filter.set_value('');

                    $(from_filter.input).prop('disabled', true);
                    $(to_filter.input).prop('disabled', true);
                } else {
                    // Enable date filters
                    $(from_filter.input).prop('disabled', false);
                    $(to_filter.input).prop('disabled', false);

                    // Restore default dates
                    if (!from_filter.get_value()) {
                        from_filter.set_value(frappe.datetime.month_start());
                    }
                    if (!to_filter.get_value()) {
                        to_filter.set_value(frappe.datetime.month_end());
                    }
                }
            }
        },
        {
            fieldname: "sales_order",
            label: __("Sales Order"),
            fieldtype: "Link",
            options: "Sales Order"
        },
    ]
};
// Copyright (c) 2025, Viral and contributors
// For license information, please see license.txt

frappe.query_reports["BoM Vs Actual Issue & Consumption"] = {
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
        // {
        //     fieldname: "serial_no",
        //     label: "Finished Good Serial No",
        //     fieldtype: "Link",
        //     options: "Serial No",
        //     get_query: function () {
        //         return {
        //             query: "asteria.asteria.api.get_fg_serial_no"
        //         };
        //     },
        //     on_change: function() {
        //         const serial_value = this.get_value();
        //         const from_filter = frappe.query_report.get_filter('from_date');
        //         const to_filter = frappe.query_report.get_filter('to_date');

        //         if (serial_value) {
        //             // Disable and clear date filters
        //             from_filter.set_value('');
        //             to_filter.set_value('');
        //             $(from_filter.input).prop('disabled', true);
        //             $(to_filter.input).prop('disabled', true);
        //         } else {
        //             // Enable date filters and restore defaults
        //             $(from_filter.input).prop('disabled', false);
        //             $(to_filter.input).prop('disabled', false);

        //             if (!from_filter.get_value()) {
        //                 from_filter.set_value(frappe.datetime.month_start());
        //             }
        //             if (!to_filter.get_value()) {
        //                 to_filter.set_value(frappe.datetime.month_end());
        //             }
        //         }
        //     }
        // }
    ]
};

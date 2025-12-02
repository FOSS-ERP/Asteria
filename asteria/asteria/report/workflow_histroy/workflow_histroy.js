// Copyright (c) 2025, Viral and contributors
// For license information, please see license.txt

frappe.query_reports['Workflow Histroy'] = {
    filters: [
        {
            "label": "DocType",
            "fieldname": "doctype",
            "fieldtype": "Link",
            "options": "DocType"
        },
        {
            "fieldname": "from_date",
            "fieldtype": "Date",
            "label": "From Date",
            default: frappe.datetime.month_start()
        },
        {
            "fieldname": "to_date",
            "fieldtype": "Date",
            "label": "To Date",
            default: frappe.datetime.month_end()
        }
    ]
}

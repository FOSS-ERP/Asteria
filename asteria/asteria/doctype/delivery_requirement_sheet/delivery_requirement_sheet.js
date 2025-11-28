// Copyright (c) 2025, Viral and contributors
// For license information, please see license.txt

frappe.ui.form.on('Delivery Requirement Sheet', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Create New Version'), () => {
                frappe.confirm(
                    __('Are you sure you want to create a new version of this document?'),
                    () => {
                        frappe.call({
                            method: 'asteria.asteria.doctype.delivery_requirement_sheet.delivery_requirement_sheet.create_new_version',
                            args: { docname: frm.doc.name },
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint(__('New version {0} created successfully', [r.message.name]));
                                    frappe.set_route('Form', 'Delivery Requirement Sheet', r.message.name);
                                }
                            },
                            error: function(err) {
                                frappe.msgprint(__('Error creating new version: {0}', [err]));
                            }
                        });
                    }
                );
            }).addClass('btn-primary');
        }
    },

    after_save(frm) {
        // Set original_reference for base documents
        if (frm.doc.revision == 0 && !frm.doc.original_reference) {
            frm.set_value('original_reference', frm.doc.name);
            frm.save();
        }
    }
});
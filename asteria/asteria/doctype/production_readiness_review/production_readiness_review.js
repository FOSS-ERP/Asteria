// Copyright (c) 2025, Viral and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Production Readiness Review", {
// 	refresh(frm) {

// 	},
// });


frappe.ui.form.on('Production Readiness Review', {
    onload(frm) {
        if (frm.is_new()) {
            // Check if this is a duplicated document with wrong original_reference
            if (frm.doc.original_reference && frm.doc.original_reference !== frm.doc.name) {
                console.log('Detected duplicated document - resetting versioning fields');
                
                // Reset all versioning fields to make this a new base document
                frm.set_value('original_reference', null);
                frm.set_value('revision', 0);
                frm.set_value('previous_reference', null);
                frm.set_value('is_active', 1);
                
                frappe.show_alert({
                    message: __('Document duplicated as a new base document. Versioning fields reset.'),
                    indicator: 'blue'
                });
            }
        }
    },

    refresh(frm) {
        if (!frm.is_new()) {
            // Add "Create New Version" button
            frm.add_custom_button(__('Create New Version'), () => {
                frappe.confirm(
                    __('Are you sure you want to create a new version?'),
                    () => {
                        frappe.call({
                            method: 'asteria.asteria.doctype.production_readiness_review.production_readiness_review.create_new_version',
                            args: { docname: frm.doc.name },
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: __('Success'),
                                        indicator: 'green',
                                        message: __('New version {0} created and activated. Previous versions have been deactivated.', [r.message.name])
                                    });
                                    frappe.set_route('Form', 'Production Readiness Review', r.message.name);
                                }
                            },
                            error: function(err) {
                                frappe.msgprint({
                                    title: __('Error'),
                                    indicator: 'red',
                                    message: __('Failed to create new version: {0}', [err])
                                });
                            }
                        });
                    }
                );
            }).addClass('btn-primary');
        }
    },

    after_save(frm) {
        // Set original_reference for base documents
        if (frm.doc.revision == 0 && !frm.doc.original_reference && frm.doc.name) {
            frm.set_value('original_reference', frm.doc.name);
            frm.save();
        }
    }
});
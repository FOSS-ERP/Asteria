// Copyright (c) 2025, Viral and contributors
// For license information, please see license.txt

frappe.ui.form.on('Delivery Requirement Sheet', {
    onload(frm) {
        // This runs when the form loads - perfect for detecting duplicates
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
                const dialog = new frappe.ui.Dialog({
                    title: __("Create New Version"),
                    fields: [
                        {
                            fieldtype: "Small Text",
                            fieldname: "version_reason",
                            label: __("Reason for creating new version"),
                            reqd: 1,
                            description: __("Please provide a reason why a new version is being created.")
                        }
                    ],
                    primary_action_label: __("Create"),
                    primary_action(values) {
                        if (!values.version_reason || !values.version_reason.trim()) {
                            frappe.msgpring({
                                title: __("Validation Error"),
                                indicator: "red",
                                message: __("Please enter a reason for creating a new version.")
                            });
                            return;
                        }
                        dialog.hide();

                        frappe.call({
                            method: "asteria.asteria.doctype.delivery_requirement_sheet.delivery_requirement_sheet.create_new_version",
                            args: {
                                docname: frm.doc.name,
                                reason: values.version_reason.trim()
                            },
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: __("Sucess"),
                                        indicator: "green",
                                        message: __("New Version {0} created and activated. Previous versions have been deactivated.", [r.message.name])
                                    });
                                    frappe.set_route("Form", "Delivery Requirement Sheet", r.message.name);
                                }
                            },
                            error: function(err) {
                                frappe.msgprint({
                                    title: __("Error"),
                                    indicator: "red",
                                    message: __("Failed to create new version: {0}", [err])
                                });
                            }
                        });
                    },
                    secondary_action_label: __("Cancel"),
                    secondary_action() {
                        dialog.hide();
                    }
                });

                dialog.show();
            }).addClass("btn-primary");
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
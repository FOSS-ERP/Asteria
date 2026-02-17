frappe.pages['h2h-payment-transfer'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'H2H Payment Transfer',
		single_column: true
	});

	page.document_type = page.add_field({
		fieldname: 'document_type',
		label: __('Document Type'),
		fieldtype: 'Select',
		options: "Purchase Order\nPurchase Invoice\nExpense Claim\nEmployee Advance",
		default: "Purchase Order",
		onchange:()=>{
			frappe.h2h_payment_transfer.run(page);
		}
	});

	// Add filters
	page.transaction_date = page.add_field({
		fieldname: 'transaction_date',
		label: __('Payment Process Date'),
		fieldtype: 'Date'
	});

	frappe.h2h_payment_transfer.make(page);
};

frappe.h2h_payment_transfer = {
	make: function (page) {
		var me = this;
		me.page = page;

		// Create container and render main HTML (h2h_payment_transfer.html)
		me.body = $('<div></div>').appendTo(page.body);
		$(frappe.render_template('h2h_payment_transfer', {})).appendTo(me.body);

		// Add button to fetch/render table
		page.add_inner_button(__('Transfer File'), function () {
			let selected_invoices = [];
			$('.purchase_invoice_no:checked').each(function () {
				selected_invoices.push($(this).data('invoice'));
			});

			if (selected_invoices.length === 0) {
				frappe.msgprint("Please select at least one invoice.");
				return;
			}
			let document_type = me.page.document_type.get_value();
			let scheduled_date = me.page.transaction_date.get_value();

			if (!scheduled_date){
				frappe.throw(frappe._("<b>Payment Process Date</b> is missing"))
			}
			// Call Python API
			frappe.call({
				method: 'asteria.asteria.page.h2h_payment_transfer.process_dummy_csv_and_create_updated_csv',
				args: {
					invoices: selected_invoices,
					document_type : document_type,
					scheduled_date : scheduled_date
				},
				freeze: true,
				freeze_message: __("Loading ..."),
				callback: function (r) {
					if (r.message) {
						frappe.msgprint("Invoices processed successfully!");
						// You can optionally reload the page or refresh data
						frappe.h2h_payment_transfer.run();
					}
				}
			});
		}).addClass('btn-success');
		
		$(document).on('change', '#select-all', function () {
			$('.purchase_invoice_no').prop('checked', this.checked);
		});
		// Auto-run on page load if you want:
		me.run();
	},

	run: function () {
		let me = this;
		let document_type = me.page.document_type.get_value();
		if(!document_type) return
		frappe.call({
			method: 'asteria.asteria.page.h2h_payment_transfer.get_vendor_payments',
			args: {
				document_type: document_type
			},
			freeze: true,
			freeze_message: __("Loading ..."),
			callback: function (r) {
				let data = r.message.data || [];
				// Make sure DOM is available before rendering
				let parent = me.page.main.find('.purchase_invoice_table');
				parent.empty();

				if (data.length > 0) {
					let html = frappe.render_template('h2h_payment_entry', r.message);
					parent.append(html);
				} else {
					parent.html(`<div class="text-muted text-center">No Data Found</div>`);
				}
			}
		});
	}
};

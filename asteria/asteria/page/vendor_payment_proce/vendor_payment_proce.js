frappe.pages['vendor-payment-proce'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Vendor Payment Processor',
		single_column: true
	});

	// Add filters
	page.transaction_date = page.add_field({
		fieldname: 'transaction_date',
		label: __('Payment Process Date'),
		fieldtype: 'Date',
		default: frappe.datetime.get_today()
	});

	page.due_date = page.add_field({
		fieldname: 'due_date',
		label: __('Due Date'),
		fieldtype: 'Date',
		default: '2025-07-09'
	});

	frappe.vendor_payment_proce.make(page);
};

frappe.vendor_payment_proce = {
	make: function (page) {
		var me = this;
		me.page = page;

		// Create container and render main HTML (vendor_payment_proce.html)
		me.body = $('<div></div>').appendTo(page.body);
		$(frappe.render_template('vendor_payment_proce', {})).appendTo(me.body);

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

			// Call Python API
			frappe.call({
				method: 'asteria.asteria.page.vendor_payment_proce.process_dummy_csv_and_create_updated_csv',
				args: {
					invoices: selected_invoices
				},
				callback: function (r) {
					if (r.message) {
						frappe.msgprint("Invoices processed successfully!");
						// You can optionally reload the page or refresh data
						frappe.vendor_payment_proce.run();
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
		let due_date = me.page.due_date.get_value();

		frappe.call({
			method: 'asteria.asteria.page.vendor_payment_proce.get_vendor_payments',
			args: {
				due_date: due_date
			},
			callback: function (r) {
				let data = r.message.data || [];
				console.log(data)
				// Make sure DOM is available before rendering
				let parent = me.page.main.find('.purchase_invoice_table');
				parent.empty();

				if (data.length > 0) {
					let html = frappe.render_template('purchase_invoice_table', r.message);
					parent.append(html);
				} else {
					parent.html(`<div class="text-muted text-center">No Data Found</div>`);
				}
			}
		});
	}
};

frappe.pages['payment-run'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Payment Run (Create Payment Entry)',
		single_column: true
	});

	page.document_type = page.add_field({
		fieldname: 'document_type',
		label: __('Document Type'),
		fieldtype: 'Select',
		options: "Purchase Order\nPurchase Invoice\nExpense Claim",
		default: "Purchase Order",
		onchange:()=>{
			frappe.payment_run.run(page);
			toggle_date_filters(page)
		}
	});

	page.due_date = page.add_field({
		fieldname: 'due_date',
		label: __('Due Date'),
		fieldtype: 'Date',
		onchange:()=>{
			frappe.payment_run.run(page);
		}
	})

	page.from_date = page.add_field({
		fieldname: 'from_date',
		label: __('From Date'),
		fieldtype: 'Date',
		onchange:()=>{
			frappe.payment_run.run(page);
		}
	})

	page.to_date = page.add_field({
		fieldname: 'to_date',
		label: __('To Date'),
		fieldtype: 'Date',
		onchange:()=>{
			frappe.payment_run.run(page);
		}
	})

	page.bank_account = page.add_field({
		fieldname: 'bank_account',
		label: __('Bank Account'),
		fieldtype: 'Link',
		options: 'Account',
		get_query: () => {
			return {
				filters: {
					account_type: ['in', ['Bank', 'Cash']]
				}
			};
		},
	});

	page.supplier = page.add_field({
		fieldname: 'supplier',
		label: __('Supplier'),
		fieldtype: 'Link',
		options: 'Supplier',
		onchange:()=>{
			frappe.payment_run.run(page);
		}
	});

	page.employee = page.add_field({
		fieldname: 'employee',
		label: __('Employee'),
		fieldtype: 'Link',
		options: 'Employee',
		onchange:()=>{
			frappe.payment_run.run(page);
		}
	});

	frappe.payment_run.make(page);
}


function toggle_date_filters(page) {
	const selected = page.fields_dict.document_type.get_value();
	const show = (selected === "Purchase Invoice" || selected === "Purchase Order");
	page.from_date.toggle(show);
	page.to_date.toggle(show);
	page.supplier.toggle(show)
	const due_date_show = (selected === "Purchase Invoice");
	page.due_date.toggle(due_date_show);
	const showemployee = (selected === "Expense Claim")
	page.employee.toggle(showemployee)
}

frappe.payment_run = {
	make: function (page) {
		var me = this;
		me.page = page;

		// Create container and render main HTML (payment_run.html)
		me.body = $('<div></div>').appendTo(page.body);
		$(frappe.render_template('payment_run', {})).appendTo(me.body);

		// Add button to fetch/render table
		page.add_inner_button(__('Create payment Entry'), function () {
			let selected_invoices = [];
			$('.document-selected:checked').each(function () {
				selected_invoices.push($(this).data('invoice'));
			});

			if (selected_invoices.length === 0) {
				frappe.msgprint("Please select at least one invoice.");
				return;
			}
			
			// Call Python API
			let document_type = me.page.fields_dict.document_type.get_value();
			let bank_account = me.page.fields_dict.bank_account.get_value();
			if (!bank_account){
				frappe.throw("Bank Account is not selected")
			}
			frappe.call({
				method: 'asteria.asteria.page.payment_run.create_payment_entry_',
				args: {
					document_type : document_type,
					invoices: selected_invoices,
					bank_account : bank_account
				},
				freeze: true,
				freeze_message: __("Payment Entry Loading ..."),
				callback: function (r) {
					if (r.message) {
						frappe.payment_run.run();
						frappe.msgprint("Payment Entry processed successfully!");
						// You can optionally reload the page or refresh data
					}
				}
			});
		}).addClass('btn-success');
		
		// $(document).on('change', '#select-all', function () {
		// 	$('.document-selected').prop('checked', this.checked);
		// 	updateSelectedCount();
		// });
		$(document).on('change', '#select-all', function () {
			$('.document-selected').prop('checked', this.checked);
			updateSelectedCount();
		});
		
		$(document).on('change', '.document', function () {
			let allChecked = $('.document').length === $('.document:checked').length;
			$('#select-all').prop('checked', allChecked);
			updateSelectedCount();
		});
		$(document).on('click', '.sort-icon-pe', ()=>{
			const icon = document.querySelector(".sort-icon-pe");
			const currentOrder = icon.getAttribute("data-order-type");
			const newOrder = currentOrder === "ASC" ? "DESC" : "ASC";
			icon.setAttribute("data-order-type", newOrder);
			icon.textContent = newOrder === "ASC" ? "↑" : "↓";
			me.run();
		})
		// Auto-run on page load if you want:
		me.run();
	},

	run: function () {
		let me = this;
		toggle_date_filters(me.page)
		let document_type = me.page.fields_dict.document_type.get_value();
		let due_date = me.page.fields_dict.due_date.get_value();
		let from_date = me.page.fields_dict.from_date.get_value();
		let to_date = me.page.fields_dict.to_date.get_value();
		let supplier = me.page.fields_dict.supplier.get_value();
		let employee = me.page.fields_dict.employee.get_value();
		let OrderBy = '';
		let sort_icon = document.querySelector(".sort-icon-pe");
		if (sort_icon) {
			OrderBy = sort_icon.getAttribute("data-order-type");
		}
		console.log(OrderBy)
		frappe.call({
			method: 'asteria.asteria.page.payment_run.get_entries',
			args: {
				document_type: document_type,
				due_date: due_date,
				from_date: from_date,
				to_date: to_date,
				supplier: supplier,
				orderby : OrderBy,
				employee : employee
			},
			freeze:true,
			freeze_message: __("Loading ......"),
			callback: function (r) {
				let data = r.message.data || [];

				let parent = me.page.main.find('.entries_table');
				parent.empty();

				if (data.length > 0) {
					let html = frappe.render_template('payment_entries_table', r.message);

					let tempDiv = document.createElement("div");
					tempDiv.innerHTML = html;

					let sortIcon = tempDiv.querySelector(".sort-icon-pe");
					if (sortIcon) {
						sortIcon.setAttribute("data-order-type", OrderBy);
					}
					
					parent.append(tempDiv);
				} else {
					parent.html(`<div class="text-muted text-center">No Data Found</div>`);
				}
			}
		});
	}
};


function updateSelectedCount() {
    let count = $('.document-selected:checked').length;
    $('#selected-count').text(count);
    
    let selectedInvoices = $('.document-selected:checked').map(function() {
        return $(this).data('invoice');
    }).get();

	$('#selected-count').text(selectedInvoices.length);
}


$(document).on('change', '#select-all', function () {
    $('.document').prop('checked', this.checked);
    updateSelectedCount();
});

$(document).on('change', '.document-selected', function () {
    let allChecked = $('.document-selected').length === $('.document-selected:checked').length;
    $('#select-all').prop('checked', allChecked);
    updateSelectedCount();
});
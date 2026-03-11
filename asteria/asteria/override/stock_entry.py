from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class CustomStockEntry(StockEntry):
	"""Override Stock Entry to preserve user-set child table field values on save.

	When a field value (e.g. Difference Account / expense_account) is already set
	by the user, the system will not overwrite it with defaults during validate.
	"""

	# Fields in items child table that should not be overwritten when user has set a value
	PRESERVE_IF_SET_FIELDS = (
		"expense_account",
		"cost_center",
		"uom",
		"description",
		"barcode",
	)

	def validate_item(self):
		# Save user-set values before parent overwrites them
		saved_values = []
		for item in self.get("items"):
			row_saved = {}
			for field in self.PRESERVE_IF_SET_FIELDS:
				if item.get(field):
					row_saved[field] = item.get(field)
			saved_values.append(row_saved)

		# Call original validation (which may overwrite these fields)
		super().validate_item()

		# Restore preserved values
		for item, row_saved in zip(self.get("items"), saved_values):
			for field, value in row_saved.items():
				item.set(field, value)

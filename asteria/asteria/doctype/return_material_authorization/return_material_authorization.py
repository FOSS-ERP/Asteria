# Copyright (c) 2026, Viral and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReturnMaterialAuthorization(Document):
	"""Server-side controller for Return Material Authorization."""
	pass


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_items_from_po(doctype, txt, searchfield, start, page_len, filters):
	"""
	Link-field query for `part_number`.

	- Filters items based on the selected Purchase Order (filters.po / purchase_order_number)
	- Returns distinct item codes from `Purchase Order Item`
	"""

	if not filters:
		return []

	po = filters.get("po") or filters.get("purchase_order") or filters.get("purchase_order_number")
	if not po:
		return []

	like_txt = f"%{txt or ''}%"

	items = frappe.db.sql(
		"""
		SELECT DISTINCT
			item_code,
			item_name,
			description
		FROM `tabPurchase Order Item`
		WHERE parent = %s
			AND (
				item_code LIKE %s
				OR IFNULL(item_name, '') LIKE %s
				OR IFNULL(description, '') LIKE %s
			)
		ORDER BY idx
		LIMIT %s OFFSET %s
		""",
		(po, like_txt, like_txt, like_txt, page_len, start),
		as_dict=True,
	)

	# Standard link-query response: [value, label]
	return [[d.item_code, d.item_name or d.item_code] for d in items]


@frappe.whitelist()
def get_item_rate_from_po(po, item_code):
	"""
	Get the rate and purchase_order_item reference for an item from Purchase Order.
	
	Args:
		po: Purchase Order name
		item_code: Item code to find in the PO
		
	Returns:
		dict with 'rate' and 'purchase_order_item' (row name from Purchase Order Item table)
	"""
	if not po or not item_code:
		return {"rate": 0, "purchase_order_item": ""}

	# Get the first matching item row from Purchase Order
	po_item = frappe.db.get_value(
		"Purchase Order Item",
		{"parent": po, "item_code": item_code},
		["rate", "name"],
		as_dict=True
	)

	if po_item:
		return {
			"rate": po_item.rate or 0,
			"purchase_order_item": po_item.name
		}
	
	return {"rate": 0, "purchase_order_item": ""}


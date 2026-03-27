import frappe
from frappe.utils import getdate


def autoname(doc, method=None):
	date = getdate(doc.creation) if doc.creation else getdate()
	doc.fiscal_year = get_fiscal_year_label(date)


def before_validate(doc, method=None):
	date = getdate(doc.creation) if doc.creation else getdate()
	doc.fiscal_year = get_fiscal_year_label(date)


def get_fiscal_year_label(date):
	# Indian fiscal year: April 1 to March 31
	if date.month >= 4:
		start = date.year
	else:
		start = date.year - 1
	end = start + 1
	return f"{str(start)[-2:]}-{str(end)[-2:]}"

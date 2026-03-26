import frappe
from frappe.utils import getdate


def before_validate(doc, method=None):
	date = getdate(doc.creation) if doc.creation else getdate()
	doc.fiscal_year = get_fiscal_year_label(date)


def get_fiscal_year_label(date):
	# Indian fiscal year: April 1 to March 31
	# If month >= 4 (April onwards), FY is current_year - (current_year+1)
	# If month < 4 (Jan to March), FY is (current_year-1) - current_year
	if date.month >= 4:
		start = date.year
	else:
		start = date.year - 1
	end = start + 1
	return f"{str(start)[-2:]}-{str(end)[-2:]}"

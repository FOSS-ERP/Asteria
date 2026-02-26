# Copyright (c) 2026, Viral and contributors
# For license information, please see license.txt
#
# MSME Purchase Invoice Summary – Purchase Invoice and Journal Entry
# Unpaid Amount = Outstanding Amount (from PLE)
# Invoice/Paid amounts not double-counted when multiple payments per voucher

import frappe
from frappe.utils import flt, getdate, today


def execute(filters=None):
    if not filters:
        filters = {}
    columns = get_columns()
    data = get_data(filters)
    # Use framework's built-in total row functionality
    return columns, data


def get_data(filters):
    report_date = getdate(filters.get("to_date") or today())
    company = filters.get("company")

    # 1. Purchase Invoices only (exclude returns)
    purchase_invoices = _get_purchase_invoices(filters)

    # 2. Payment allocations (PI and JE)
    payment_map_pi = _get_payment_allocations_by_pi(filters)
    payment_map_je = _get_payment_allocations_by_je(filters)

    # 3. Outstanding from PLE (matches Accounts Payable – PI and JE)
    outstanding_map = _get_outstanding_from_ple(filters)

    # 4. Tax breakdown per PI (CGST, SGST, IGST, TDS)
    tax_map = _get_tax_details()

    # 5. Purchase Receipt linked to PI
    pr_map = _get_purchase_receipt_by_pi(purchase_invoices)

    # 6. Journal Entry linked to PI (for Journal Entry column)
    je_map = _get_journal_entry_by_pi(purchase_invoices)

    # 7–10. Standalone / PLE / TDS Journal Entries and Advance / PO Payments
    # When filtering by a specific Purchase Invoice, user wants to see
    # only rows that have a Purchase Invoice reference, so we SKIP
    # standalone JEs in that case.
    journal_entries = []
    advance_payments = []
    if not filters.get("purchase_invoice"):
        # 7. Standalone Journal Entries (Supplier payable, not linked to PI)
        journal_entries = _get_standalone_journal_entries(filters)

        # 8. Journal Entries from PLE (including those with negative outstanding)
        je_from_ple = _get_journal_entries_from_ple(filters)

        # Merge: Add JEs from PLE that are not already in journal_entries
        je_names_existing = {je.name for je in journal_entries}
        for je in je_from_ple:
            if je.name not in je_names_existing:
                journal_entries.append(je)

        # 9. TDS Deduction Journal Entries (without PI reference, supplier-wise)
        tds_journal_entries = _get_tds_deduction_journal_entries(filters)

        # Merge: Add TDS JEs that are not already in journal_entries
        for je in tds_journal_entries:
            if je.name not in je_names_existing:
                journal_entries.append(je)
                je_names_existing.add(je.name)

        # 10. Advance / Purchase Order Payment Entries (no PI/JE reference)
        advance_payments = _get_advance_payment_entries(filters)

    data = []
    for pi in purchase_invoices:
        payments = payment_map_pi.get(pi.name, [])
        taxes = tax_map.get(pi.name, {})
        pr_info = pr_map.get(pi.name, {})
        je_refs = je_map.get(pi.name, [])  # Now returns a list of JEs

        # Invoice amount = rounded total (base_rounded_total when enabled, else base_grand_total)
        if pi.base_rounded_total and not pi.disable_rounded_total:
            invoice_amount = flt(pi.base_rounded_total, 2)
        else:
            invoice_amount = flt(pi.base_grand_total, 2)

        # Unpaid = PLE outstanding (matches Accounts Payable report)
        pi_outstanding = flt(outstanding_map.get(("Purchase Invoice", pi.name), 0), 2)

        is_delay = (
            pi_outstanding > 0
            and pi.due_date
            and getdate(pi.due_date) < report_date
        )
        overdue_amount = pi_outstanding if is_delay else 0
        payment_status = "Delay" if is_delay else "On Time"

        # Payment status filter
        if filters.get("payment_status") == "Delay" and not is_delay:
            continue
        if filters.get("payment_status") == "On Time" and is_delay:
            continue

        # Sum of all Payment Entries against this PI (Payment Entry Value total)
        # This is used for:
        #   - Sum of Payment Entry Value in PI-wise Balance formula
        #   - Base for Paid Amount before JE adjustments
        total_payment_entry_value = sum(
            flt(p.base_allocated_amount or p.allocated_amount, 2) for p in payments
        )

        # Calculate Rounded Amount Net Payable for PI row
        rounded_amount_pi = flt(pi.base_rounded_total, 2) if (pi.base_rounded_total and not pi.disable_rounded_total) else flt(pi.base_grand_total, 2)
        
        # Track:
        #   - JE effect on Rounded Amount Net Payable (per invoice)
        #   - JE effect on Paid Amount when company is RECEIVING from supplier.
        # For complex JEs with multiple debits/credits on the payable account, we use NET effect:
        #   net_payable = total_debit - total_credit on the supplier payable account.
        #   net_payable > 0  -> company is paying supplier
        #   net_payable < 0  -> supplier is paying company (refund/credit)
        je_rounded_amount_total = 0  # Sum of JE impact shown in Rounded Amount Net Payable column (per PI)
        je_paid_adjustment = 0       # Negative when supplier pays company (reduces Paid Amount)
        for je_ref in je_refs:
            # Compute JE impact per Purchase Invoice:
            # Use only those JE Account rows which explicitly reference this PI.
            je_amount = frappe.db.sql("""
                SELECT 
                    SUM(ABS(jea.debit_in_account_currency)) AS debit_amount,
                    SUM(ABS(jea.credit_in_account_currency)) AS credit_amount
                FROM `tabJournal Entry Account` jea
                INNER JOIN `tabAccount` acc ON acc.name = jea.account
                WHERE jea.parent = %s
                    AND jea.party_type = 'Supplier'
                    AND jea.party = %s
                    AND acc.account_type = 'Payable'
                    AND jea.reference_type = 'Purchase Invoice'
                    AND jea.reference_name = %s
            """, (je_ref, pi.supplier, pi.name), as_dict=True)
            debit_amt = flt(je_amount[0].debit_amount, 2) if je_amount and je_amount[0].debit_amount else 0
            credit_amt = flt(je_amount[0].credit_amount, 2) if je_amount and je_amount[0].credit_amount else 0

            net_payable = debit_amt - credit_amt
            if net_payable != 0:
                effect_amount = abs(net_payable)

                # JE impact on Rounded Amount Net Payable (JE row):
                #   > 0  -> company pays supplier (show as negative)
                #   < 0  -> supplier pays company (show as positive)
                if net_payable > 0:
                    je_rounded_amount_total += -effect_amount
                else:  # net_payable < 0
                    je_rounded_amount_total += effect_amount

                # When supplier is paying company (net_payable < 0),
                # the PI row's Paid Amount must get REDUCED by this JE net amount.
                if net_payable < 0:
                    je_paid_adjustment -= effect_amount

        # Final Paid Amount in PI row = Payment Entries total + JE adjustments
        total_paid_amount = flt(total_payment_entry_value + je_paid_adjustment, 2)
        
        # Purchase Invoice-wise Balance:
        #   Balance (PI) = Sum of Rounded Amount Net Payable (PI + all linked JEs)
        #                  - Sum of Payment Entry Value (all PEs against that PI)
        total_rounded_amount = rounded_amount_pi + je_rounded_amount_total
        balance_amount = flt(total_rounded_amount - total_payment_entry_value, 2)

        # First row: Purchase Invoice row (with outstanding amount and total paid amount)
        # Payment Delay in Days logic:
        # - If invoice is Paid  -> last Payment Entry posting_date - due_date
        # - If not Paid         -> BLANK
        delay_days = None
        if pi.due_date and pi.status == "Paid" and payments:
            # Last payment date from all Payment Entry rows only (pe.posting_date)
            payment_dates = [
                getdate(p.posting_date)
                for p in payments
                if getattr(p, "posting_date", None)
            ]
            if payment_dates:
                last_payment_date = max(payment_dates)
                delay_days = (last_payment_date - getdate(pi.due_date)).days

        data.append(_build_row(
            pi=pi,
            payment=None,  # No payment in first row
            payments=payments,
            invoice_amount=invoice_amount,
            paid_amount=flt(total_paid_amount, 2),  # Total paid amount in PI row
            unpaid_amount=pi_outstanding,  # Outstanding only in PI row
            overdue_amount=overdue_amount,
            payment_status=payment_status,
            delay_days=delay_days,
            taxes=taxes,
            pr_info=pr_info,
            je_ref=None,  # JE will be shown in separate row
            report_date=report_date,
            show_invoice_details=True,
            balance_amount=balance_amount,  # Pass calculated balance
        ))

        # Subsequent rows: Payment Entry or JV rows (no outstanding amount)
        if payments:
            for p in payments:
                # Payment Delay only if outstanding; payment rows have no outstanding
                delay_days = None

                data.append(_build_row(
                    pi=pi,
                    payment=p,
                    payments=payments,
                    invoice_amount=0,  # No invoice amount in payment rows
                    paid_amount=0,  # No paid amount in payment rows (shown in PI row only)
                    unpaid_amount=0,  # No outstanding in payment rows
                    overdue_amount=0,  # No overdue in payment rows
                    payment_status=None,  # No status in payment rows
                    delay_days=delay_days,
                    taxes=taxes,
                    pr_info=pr_info,
                    je_ref=None,  # Don't show JE ref in payment rows
                    report_date=report_date,
                    show_invoice_details=False,  # Payment details only
                ))
        
        # Add Journal Entry rows for ALL linked JEs
        for je_ref in je_refs:
            # Get JE details
            je_details = frappe.db.get_value("Journal Entry", je_ref, [
                "posting_date", "cheque_no", "cheque_date", "due_date"
            ], as_dict=True)
            
            if je_details:
                # Create a row for each linked JE (shows as payment/JV row)
                data.append(_build_je_linked_row(
                    pi=pi,
                    je_ref=je_ref,
                    je_details=je_details,
                    taxes=taxes,
                    pr_info=pr_info,
                    report_date=report_date,
                ))

    # Add standalone Journal Entry rows
    for je in journal_entries:
        payments = payment_map_je.get(je.name, [])
        je_outstanding = flt(outstanding_map.get(("Journal Entry", je.name), 0), 2)
        # For standalone JEs (not linked to PI), Invoice Amount = 0
        # Unpaid Amount = Outstanding Amount (they are the same)
        je_invoice_amount = 0

        is_delay = je_outstanding > 0 and je.due_date and getdate(je.due_date) < report_date
        overdue_amount = je_outstanding if is_delay else 0
        payment_status = "Delay" if is_delay else "On Time"

        if filters.get("payment_status") == "Delay" and not is_delay:
            continue
        if filters.get("payment_status") == "On Time" and is_delay:
            continue

        if payments:
            # First row: all JE details, subsequent rows: payment details only
            # Payment Delay = Today - due_date, only if outstanding
            for idx, p in enumerate(payments):
                delay_days = (getdate(today()) - getdate(je.due_date)).days if je_outstanding > 0 and je.due_date and idx == 0 else None
                # For subsequent payment rows, set invoice amount and unpaid amount to 0
                is_first_payment = (idx == 0)
                row_invoice_amount = je_invoice_amount if is_first_payment else 0
                row_unpaid_amount = je_outstanding if is_first_payment else 0
                row_overdue_amount = overdue_amount if is_first_payment else 0
                data.append(_build_je_row(
                    je=je, payment=p, invoice_amount=row_invoice_amount,
                    paid_amount=flt(p.base_allocated_amount or p.allocated_amount, 2),
                    unpaid_amount=row_unpaid_amount, overdue_amount=row_overdue_amount,
                    payment_status=payment_status, delay_days=delay_days,
                    report_date=report_date,
                    show_invoice_details=is_first_payment,
                ))
        else:
            # Payment Delay = Today - due_date, only if outstanding
            delay_days = (getdate(today()) - getdate(je.due_date)).days if je_outstanding > 0 and je.due_date else None
            data.append(_build_je_row(
                je=je, payment=None, invoice_amount=je_invoice_amount,
                paid_amount=0, unpaid_amount=je_outstanding, overdue_amount=overdue_amount,
                payment_status=payment_status, delay_days=delay_days,
                report_date=report_date,
            ))

    # Add advance / Purchase Order Payment Entry rows (no PI/JE reference)
    for pe in advance_payments:
        data.append(_build_advance_payment_row(
            pe=pe,
            report_date=report_date,
        ))

    # Sort by Purchase Invoice/Journal Entry/Payment Entry first, then by row type (PI/JE main row first, then payment/advance rows), then by PINV Date
    # Row type: 0 = PI/JE main row (has Invoice Amount > 0), 1 = payment/JV/advance row (Invoice Amount = 0)
    def sort_key(row):
        voucher = (
            row.get("Purchase Invoice")
            or row.get("Journal Entry")
            or row.get("Payment Entry")
            or ""
        )
        # Determine row type: if has Invoice Amount > 0, it's main row (0), else payment row (1)
        row_type = 0 if flt(row.get("Invoice Amount", 0), 2) > 0 else 1
        pinv_date = row.get("PINV Date") or getdate("1900-01-01")
        return (voucher, row_type, pinv_date)
    
    data.sort(key=sort_key)
    return data


def _build_row(pi, payment, payments, invoice_amount, paid_amount, unpaid_amount,
        overdue_amount, payment_status, delay_days, taxes, pr_info, je_ref, report_date=None, show_invoice_details=True, balance_amount=None):
    """Build one report row – format matches Excel (36 columns).
    
    Args:
        show_invoice_details: If False, only payment details are shown (for subsequent payment rows).
        report_date: Report date for calculating "Due in" days.
    """
    # Calculate Rounded Amount Net Payable 
    rounded_amount = flt(pi.base_rounded_total, 2) if (pi.base_rounded_total and not pi.disable_rounded_total) else flt(pi.base_grand_total, 2)
    
    # Calculate Payment Entry Value  - allocated amount in base currency
    payment_entry_value = 0
    if payment:
        payment_entry_value = flt(getattr(payment, 'base_allocated_amount', None) or getattr(payment, 'allocated_amount', 0), 2)
    
    # Calculate Balance = Total of "Rounded Amount Net Payable" - Paid Amount (invoice-wise)
    # If balance_amount is provided (for PI row), use it; otherwise 0 for payment rows
    if balance_amount is not None and show_invoice_details:
        balance = balance_amount
    else:
        balance = 0
    
    # Due In: only for invoices that are NOT fully paid
    #   If status != "Paid" and due_date exists:
    #       Due In = today - due_date (in days)
    #   If status == "Paid": Due In is blank
    due_in = None
    if pi.status != "Paid" and pi.due_date:
        due_in = (getdate(today()) - getdate(pi.due_date)).days

    # Paid Date (new column):
    #   Only for PI row, when status is Paid -> last Payment Entry posting_date
    paid_date = None
    if show_invoice_details and pi.status == "Paid" and payments:
        payment_dates = [
            getdate(p.posting_date)
            for p in payments
            if getattr(p, "posting_date", None)
        ]
        if payment_dates:
            paid_date = max(payment_dates)
    
    if show_invoice_details:
        # First row: all invoice details
        row = {
            "PINV Date": pi.posting_date,
            "Purchase Invoice": pi.name,
            "Supplier ID": pi.supplier,
            "Supplier Name": pi.supplier_name,
            "Rounded Amount Net Payable": rounded_amount,
            "Invoice Amount": invoice_amount,
            "Taxable Amount": flt(pi.base_net_total, 2),
            "CGST Amount": flt(taxes.get("cgst", 0), 2),
            "SGST Amount": flt(taxes.get("sgst", 0), 2),
            "IGST Amount": flt(taxes.get("igst", 0), 2),
            "Payment Date": payment.posting_date if payment else None,
            "Payment Entry": payment.payment_entry if payment else None,
            "Payment Entry Value": payment_entry_value,
            "Paid Amount": paid_amount,
            "Balance": balance,
            "Due Date": pi.due_date,
            "Paid Date": paid_date,
            "Due in": due_in,
            "MSME": pi.msme,
            "Payment Delay in Days": delay_days,
            "Payment Status": payment_status,
            "Payment Mode": payment.mode_of_payment if payment else None,
            "Payment Entry Status": payment.pe_status if payment else None,
            "Supplier Invoice No": pi.bill_no,
            "Supplier Invoice Date": pi.bill_date,
            "GST Category": pi.gst_category,
            "GST": pi.tax_id,
            "Unpaid Amount": unpaid_amount,
            "Overdue Amount": overdue_amount,
            "TDS Amount": flt(taxes.get("tds", 0), 2),
            "TDS Account": taxes.get("tds_account"),
            "Currency": pi.currency,
            "Purchase Order": None,
            "Purchase Receipt": pr_info.get("name"),
            "Purchase Receipt Date": pr_info.get("posting_date"),
            "Journal Entry": je_ref,
            "Journal Entry Ref": je_ref,  # Same as Journal Entry
            "Purchase Invoice Status": pi.status,
        }
    else:
        # Subsequent payment rows: only payment entry details
        row = {
            "PINV Date": pi.posting_date,  # Keep PI date for sorting and reference
            "Purchase Invoice": pi.name,  # Keep for reference
            "Supplier ID": pi.supplier,  # Keep for reference
            "Supplier Name": pi.supplier_name,  # Keep for reference
            "Rounded Amount Net Payable": 0,
            "Invoice Amount": 0,
            "Taxable Amount": 0,
            "CGST Amount": 0,
            "SGST Amount": 0,
            "IGST Amount": 0,
            "Payment Date": payment.posting_date if payment else None,
            "Payment Entry": payment.payment_entry if payment else None,
            "Payment Entry Value": payment_entry_value,
            "Paid Amount": paid_amount,
            "Balance": 0,
            "Due Date": None,
            "Paid Date": None,
            "Due in": None,
            "MSME": None,
            "Payment Delay in Days": None,
            "Payment Status": None,
            "Payment Mode": payment.mode_of_payment if payment else None,
            "Payment Entry Status": payment.pe_status if payment else None,
            "Supplier Invoice No": None,
            "Supplier Invoice Date": None,
            "GST Category": None,
            "GST": None,
            "Unpaid Amount": 0,
            "Overdue Amount": 0,
            "TDS Amount": 0,
            "TDS Account": None,
            "Currency": pi.currency,
            "Purchase Order": None,
            "Purchase Receipt": None,
            "Purchase Receipt Date": None,
            "Journal Entry": None,
            "Journal Entry Ref": None,
            "Purchase Invoice Status": None,
        }
    return row


def _build_je_linked_row(pi, je_ref, je_details, taxes, pr_info, report_date=None):
    """Build row for Journal Entry linked to Purchase Invoice (shows as JV row after payment rows)."""
    # Due In = due_date - purchase invoice posting_date (JE is linked to PI)
    due_in = None
    if je_details.due_date and pi.posting_date:
        due_in = (getdate(je_details.due_date) - getdate(pi.posting_date)).days
    
    # Get JE amount on supplier payable account.
    # For complex JEs with multiple debit/credit lines, use NET effect:
    #   net_payable = total_debit - total_credit on the supplier payable account.
    #   net_payable > 0  -> company is paying supplier
    #   net_payable < 0  -> supplier is paying company (refund/credit)
    je_amount = frappe.db.sql("""
        SELECT 
            SUM(ABS(jea.debit_in_account_currency)) AS debit_amount,
            SUM(ABS(jea.credit_in_account_currency)) AS credit_amount
        FROM `tabJournal Entry Account` jea
        INNER JOIN `tabAccount` acc ON acc.name = jea.account
        WHERE jea.parent = %s
            AND jea.party_type = 'Supplier'
            AND jea.party = %s
            AND acc.account_type = 'Payable'
            AND jea.reference_type = 'Purchase Invoice'
            AND jea.reference_name = %s
    """, (je_ref, pi.supplier, pi.name), as_dict=True)
    
    debit_amt = flt(je_amount[0].debit_amount, 2) if je_amount and je_amount[0].debit_amount else 0
    credit_amt = flt(je_amount[0].credit_amount, 2) if je_amount and je_amount[0].credit_amount else 0
    
    net_payable = debit_amt - credit_amt
    je_paid_amount = 0
    if net_payable > 0:
        # Company is paying supplier:
        # - Rounded Amount Net Payable should be negative
        # - Paid Amount in JV row should show the payment amount
        effect_amount = abs(net_payable)
        je_rounded_amount = -effect_amount
        je_paid_amount = effect_amount
    elif net_payable < 0:
        # Supplier is paying company (refund/credit):
        # - Rounded Amount Net Payable should be positive
        # - Paid Amount in JV row remains 0 (reduction handled in PI row)
        effect_amount = abs(net_payable)
        je_rounded_amount = effect_amount
    else:
        je_rounded_amount = 0
    
    return {
        "PINV Date": je_details.posting_date,  # Use JE posting date
        "Purchase Invoice": pi.name,  # Keep PI reference
        "Supplier ID": pi.supplier,  # Keep for reference
        "Supplier Name": pi.supplier_name,  # Keep for reference
        "Rounded Amount Net Payable": je_rounded_amount,  # Negative amount for payment
        "Invoice Amount": 0,  # No invoice amount in JE row
        "Taxable Amount": 0,
        "CGST Amount": 0,
        "SGST Amount": 0,
        "IGST Amount": 0,
        "Payment Date": je_details.posting_date,  # JE posting date as payment date
        "Payment Entry": None,  # JE is not a Payment Entry
        # For JEs linked to Purchase Invoice, show the value ONLY in Rounded Amount Net Payable
        # and NOT in Payment Entry Value (PE column is reserved for Payment Entries only).
        "Payment Entry Value": 0,
        "Paid Amount": je_paid_amount,
        "Balance": 0,  # No balance in JE row
        "Due Date": je_details.due_date,
        "Due in": due_in,
        "MSME": None,  # Not shown in JE row
        "Payment Delay in Days": None,
        "Payment Status": None,
        "Payment Mode": None,
        "Payment Entry Status": None,
        "Supplier Invoice No": je_details.cheque_no,
        "Supplier Invoice Date": je_details.cheque_date,
        "GST Category": None,  # Not shown in JE row
        "GST": None,  # Not shown in JE row
        "Unpaid Amount": 0,  # No outstanding in JE row
        "Overdue Amount": 0,
        "TDS Amount": 0,
        "TDS Account": None,
        "Currency": pi.currency,
        "Purchase Order": None,
        "Purchase Receipt": None,
        "Purchase Receipt Date": None,
        "Journal Entry": je_ref,
        "Journal Entry Ref": je_ref,  # Same as Journal Entry
        "Purchase Invoice Status": None,
    }


# ---------------------------------------------------------------------------
# DATA FETCH
# ---------------------------------------------------------------------------

def _get_purchase_invoices(filters):
    conditions = [
        "pi.docstatus = 1",
    ]
    values = []

    if filters.get("company"):
        conditions.append("pi.company = %s")
        values.append(filters.get("company"))

    if filters.get("purchase_invoice"):
        # When a specific Purchase Invoice is selected, ignore date/supplier
        # filters and rely on the exact invoice name (plus company).
        conditions.append("pi.name = %s")
        values.append(filters.get("purchase_invoice"))
    else:
        if filters.get("from_date"):
            conditions.append("pi.posting_date >= %s")
            values.append(getdate(filters.get("from_date")))
        if filters.get("to_date"):
            conditions.append("pi.posting_date <= %s")
            values.append(getdate(filters.get("to_date")))
        if filters.get("supplier"):
            conditions.append("pi.supplier = %s")
            values.append(filters.get("supplier"))

    where = " AND ".join(conditions)
    return frappe.db.sql(
        f"""
        SELECT
            pi.name,
            pi.posting_date,
            pi.bill_no,
            pi.bill_date,
            pi.supplier,
            pi.supplier_name,
            pi.due_date,
            pi.base_net_total,
            pi.base_grand_total,
            pi.base_rounded_total,
            pi.disable_rounded_total,
            pi.status,
            pi.currency,
            s.msme,
            s.gst_category,
            s.tax_id
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabSupplier` s ON s.name = pi.supplier
        WHERE {where}
        """,
        tuple(values),
        as_dict=True,
    )


def _get_payment_allocations_by_pi(filters):
    """Get Payment Entry Reference rows for Purchase Invoice, with PE details."""
    conditions = [
        "per.reference_doctype = 'Purchase Invoice'",
        "per.allocated_amount > 0",
        "pe.docstatus = 1",
        "pe.payment_type = 'Pay'",
    ]
    values = []

    if filters.get("company"):
        conditions.append("pe.company = %s")
        values.append(filters.get("company"))

    # For a specific Purchase Invoice, ignore PI date/supplier filters so that
    # all its payments are fetched regardless of posting_date or supplier filters.
    if filters.get("purchase_invoice"):
        conditions.append("pi.name = %s")
        values.append(filters.get("purchase_invoice"))
    else:
        if filters.get("from_date"):
            conditions.append("pi.posting_date >= %s")
            values.append(getdate(filters.get("from_date")))
        if filters.get("to_date"):
            conditions.append("pi.posting_date <= %s")
            conditions.append("pe.posting_date <= %s")
            values.append(getdate(filters.get("to_date")))
            values.append(getdate(filters.get("to_date")))
        if filters.get("supplier"):
            conditions.append("pi.supplier = %s")
            values.append(filters.get("supplier"))
    if filters.get("mode_of_payment"):
        conditions.append("pe.mode_of_payment = %s")
        values.append(filters.get("mode_of_payment"))

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT
            per.reference_name AS purchase_invoice,
            per.parent AS payment_entry,
            per.allocated_amount,
            per.exchange_rate,
            pe.posting_date,
            pe.mode_of_payment,
            pe.status AS pe_status
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = per.reference_name
        WHERE {where}
        ORDER BY per.reference_name, pe.posting_date
        """,
        tuple(values),
        as_dict=True,
    )

    # Base allocated = allocated_amount * exchange_rate (company currency)
    result = {}
    for r in rows:
        base_alloc = flt(r.allocated_amount, 2) * flt(r.exchange_rate or 1, 2)
        r.base_allocated_amount = base_alloc
        result.setdefault(r.purchase_invoice, []).append(r)
    return result


def _get_outstanding_from_ple(filters):
    """Outstanding from Payment Ledger Entry – matches Accounts Payable (PI and JE)."""
    conditions = [
        "ple.delinked = 0",
        "ple.account_type = 'Payable'",
        "ple.party_type = 'Supplier'",
        "ple.against_voucher_no IS NOT NULL",
        "(ple.against_voucher_type = 'Purchase Invoice' OR ple.against_voucher_type = 'Journal Entry')",
    ]
    values = []
    if filters.get("company"):
        conditions.append("ple.company = %s")
        values.append(filters.get("company"))
    if filters.get("to_date"):
        conditions.append("ple.posting_date <= %s")
        values.append(getdate(filters.get("to_date")))
    if filters.get("supplier"):
        conditions.append("ple.party = %s")
        values.append(filters.get("supplier"))

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT
            ple.against_voucher_type AS voucher_type,
            ple.against_voucher_no AS voucher_no,
            SUM(ple.amount_in_account_currency) AS outstanding
        FROM `tabPayment Ledger Entry` ple
        WHERE {where}
        GROUP BY ple.against_voucher_type, ple.against_voucher_no, ple.party
        """,
        tuple(values),
        as_dict=True,
    )
    result = {}
    for r in rows:
        key = (r.voucher_type, r.voucher_no)
        result[key] = result.get(key, 0) + flt(r.outstanding, 2)
    return result


def _get_tax_details():
    """Tax breakdown per PI."""
    rows = frappe.db.sql(
        """
        SELECT
            parent,
            SUM(CASE WHEN account_head LIKE '%%CGST%%' THEN base_tax_amount_after_discount_amount ELSE 0 END) AS cgst,
            SUM(CASE WHEN account_head LIKE '%%SGST%%' THEN base_tax_amount_after_discount_amount ELSE 0 END) AS sgst,
            SUM(CASE WHEN account_head LIKE '%%IGST%%' THEN base_tax_amount_after_discount_amount ELSE 0 END) AS igst,
            SUM(CASE WHEN account_head LIKE '%%TDS%%' THEN base_tax_amount_after_discount_amount ELSE 0 END) AS tds,
            GROUP_CONCAT(DISTINCT CASE WHEN account_head LIKE '%%TDS%%' THEN account_head END) AS tds_account
        FROM `tabPurchase Taxes and Charges`
        GROUP BY parent
        """,
        as_dict=True,
    )
    return {r.parent: r for r in rows}


def _get_purchase_receipt_by_pi(purchase_invoices):
    """First Purchase Receipt linked to each PI."""
    if not purchase_invoices:
        return {}
    pi_names = [pi.name for pi in purchase_invoices]
    placeholders = ", ".join(["%s"] * len(pi_names))
    rows = frappe.db.sql(
        f"""
        SELECT
            pii.parent AS purchase_invoice,
            pii.purchase_receipt AS name,
            pr.posting_date
        FROM `tabPurchase Invoice Item` pii
        LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pii.purchase_receipt
        WHERE pii.parent IN ({placeholders})
            AND pii.purchase_receipt IS NOT NULL
            AND pii.purchase_receipt != ''
        GROUP BY pii.parent
        """,
        tuple(pi_names),
        as_dict=True,
    )
    return {r.purchase_invoice: r for r in rows}


def _get_journal_entry_by_pi(purchase_invoices):
    """All Journal Entries linked to each PI (via Journal Entry Account reference OR via Payment Ledger Entry).
    Returns a dict mapping PI name to a list of JE names."""
    if not purchase_invoices:
        return {}
    pi_names = [pi.name for pi in purchase_invoices]
    placeholders = ", ".join(["%s"] * len(pi_names))
    
    # Method 1: Direct reference in Journal Entry Account
    rows1 = frappe.db.sql(
        f"""
        SELECT jea.reference_name AS purchase_invoice, je.name AS journal_entry
        FROM `tabJournal Entry Account` jea
        INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE jea.reference_type = 'Purchase Invoice'
            AND jea.reference_name IN ({placeholders})
            AND je.docstatus = 1
            AND je.is_system_generated = 0
        GROUP BY jea.reference_name, je.name
        """,
        tuple(pi_names),
        as_dict=True,
    )
    
    # Method 2: Linked via Payment Ledger Entry (when JE is against a PI)
    # This catches JEs that are linked through payment processing
    rows2 = frappe.db.sql(
        f"""
        SELECT DISTINCT
            ple.against_voucher_no AS purchase_invoice,
            ple.voucher_no AS journal_entry
        FROM `tabPayment Ledger Entry` ple
        INNER JOIN `tabJournal Entry` je ON je.name = ple.voucher_no
        WHERE ple.against_voucher_type = 'Purchase Invoice'
            AND ple.against_voucher_no IN ({placeholders})
            AND ple.voucher_type = 'Journal Entry'
            AND ple.delinked = 0
            AND ple.account_type = 'Payable'
            AND je.docstatus = 1
            AND je.is_system_generated = 0
        """,
        tuple(pi_names),
        as_dict=True,
    )
    
    # Combine both methods - collect ALL JEs for each PI
    result = {}
    je_set = set()  # Track (pi_name, je_name) pairs to avoid duplicates
    
    for r in rows1:
        key = (r.purchase_invoice, r.journal_entry)
        if key not in je_set:
            je_set.add(key)
            if r.purchase_invoice not in result:
                result[r.purchase_invoice] = []
            if r.journal_entry not in result[r.purchase_invoice]:
                result[r.purchase_invoice].append(r.journal_entry)
    
    for r in rows2:
        key = (r.purchase_invoice, r.journal_entry)
        if key not in je_set:
            je_set.add(key)
            if r.purchase_invoice not in result:
                result[r.purchase_invoice] = []
            if r.journal_entry not in result[r.purchase_invoice]:
                result[r.purchase_invoice].append(r.journal_entry)
    
    return result


def _get_journal_entries_from_ple(filters):
    """Get Journal Entries from PLE (including those with negative outstanding).
    These are JEs that appear in Accounts Payable, regardless of outstanding sign."""
    conditions = [
        "ple.delinked = 0",
        "ple.account_type = 'Payable'",
        "ple.party_type = 'Supplier'",
        "ple.against_voucher_type = 'Journal Entry'",
        "ple.against_voucher_no IS NOT NULL",
        "je.docstatus = 1",
        "NOT EXISTS (SELECT 1 FROM `tabJournal Entry Account` x WHERE x.parent = je.name AND x.reference_type = 'Purchase Invoice')",
    ]
    values = []
    if filters.get("company"):
        conditions.append("ple.company = %s")
        values.append(filters.get("company"))
    if filters.get("to_date"):
        conditions.append("ple.posting_date <= %s")
        values.append(getdate(filters.get("to_date")))
    if filters.get("supplier"):
        conditions.append("ple.party = %s")
        values.append(filters.get("supplier"))

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT
            je.name,
            je.posting_date,
            je.cheque_no AS bill_no,
            je.cheque_date AS bill_date,
            je.due_date,
            ple.party AS supplier,
            ple.account_currency AS currency
        FROM `tabPayment Ledger Entry` ple
        INNER JOIN `tabJournal Entry` je ON je.name = ple.against_voucher_no
        WHERE {where}
        GROUP BY je.name, ple.party
        """,
        tuple(values),
        as_dict=True,
    )
    je_map = {}
    for r in rows:
        if r.name not in je_map:
            je_map[r.name] = frappe._dict({
                "name": r.name,
                "posting_date": r.posting_date,
                "bill_no": r.bill_no,
                "bill_date": r.bill_date,
                "due_date": r.due_date,
                "supplier": r.supplier,
                "currency": r.currency,
            })
    for je in je_map.values():
        s = frappe.db.get_value("Supplier", je.supplier, ["supplier_name", "msme", "gst_category", "tax_id"], as_dict=True)
        je.supplier_name = s.supplier_name if s else je.supplier
        je.msme = s.msme if s else None
        je.gst_category = s.gst_category if s else None
        je.tax_id = s.tax_id if s else None
    return list(je_map.values())


def _get_standalone_journal_entries(filters):
    """Journal Entries created for Supplier, not linked to Purchase Invoice."""
    conditions = [
        "je.docstatus = 1",
        "je.is_system_generated = 0",
        "jea.party_type = 'Supplier'",
        "jea.party IS NOT NULL",
        "acc.account_type = 'Payable'",
        # Any non-zero line on the payable account (debit or credit)
        "(jea.debit_in_account_currency != 0 OR jea.credit_in_account_currency != 0)",
        "NOT EXISTS (SELECT 1 FROM `tabJournal Entry Account` x WHERE x.parent = je.name AND x.reference_type = 'Purchase Invoice')",
    ]
    values = []
    if filters.get("company"):
        conditions.append("je.company = %s")
        values.append(filters.get("company"))
    if filters.get("from_date"):
        conditions.append("je.posting_date >= %s")
        values.append(getdate(filters.get("from_date")))
    if filters.get("to_date"):
        conditions.append("je.posting_date <= %s")
        values.append(getdate(filters.get("to_date")))
    if filters.get("supplier"):
        conditions.append("jea.party = %s")
        values.append(filters.get("supplier"))

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT
            je.name,
            je.posting_date,
            je.cheque_no AS bill_no,
            je.cheque_date AS bill_date,
            je.due_date,
            jea.party AS supplier,
            jea.credit_in_account_currency AS credit_amount,
            jea.account_currency AS currency
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
        INNER JOIN `tabAccount` acc ON acc.name = jea.account
        WHERE {where}
        GROUP BY je.name, jea.name
        """,
        tuple(values),
        as_dict=True,
    )
    je_map = {}
    for r in rows:
        if r.name not in je_map:
            je_map[r.name] = frappe._dict({
                "name": r.name,
                "posting_date": r.posting_date,
                "bill_no": r.bill_no,
                "bill_date": r.bill_date,
                "due_date": r.due_date,
                "supplier": r.supplier,
                "currency": r.currency,
            })
        je_map[r.name].credit_amount = je_map[r.name].get("credit_amount", 0) + flt(r.credit_amount, 2)
    for je in je_map.values():
        s = frappe.db.get_value("Supplier", je.supplier, ["supplier_name", "msme", "gst_category", "tax_id"], as_dict=True)
        je.supplier_name = s.supplier_name if s else je.supplier
        je.msme = s.msme if s else None
        je.gst_category = s.gst_category if s else None
        je.tax_id = s.tax_id if s else None
    return list(je_map.values())


def _get_tds_deduction_journal_entries(filters):
    """Get Journal Entries for TDS deduction without Purchase Invoice reference, supplier-wise."""
    conditions = [
        "je.docstatus = 1",
        "je.apply_tds = 1",
        "jea.party_type = 'Supplier'",
        "jea.party IS NOT NULL",
        "acc.account_type = 'Payable'",
        "NOT EXISTS (SELECT 1 FROM `tabJournal Entry Account` x WHERE x.parent = je.name AND x.reference_type = 'Purchase Invoice')",
    ]
    values = []
    if filters.get("company"):
        conditions.append("je.company = %s")
        values.append(filters.get("company"))
    if filters.get("from_date"):
        conditions.append("je.posting_date >= %s")
        values.append(getdate(filters.get("from_date")))
    if filters.get("to_date"):
        conditions.append("je.posting_date <= %s")
        values.append(getdate(filters.get("to_date")))
    if filters.get("supplier"):
        conditions.append("jea.party = %s")
        values.append(filters.get("supplier"))

    where = " AND ".join(conditions)
    # First get the JEs
    je_rows = frappe.db.sql(
        f"""
        SELECT DISTINCT
            je.name,
            je.posting_date,
            je.cheque_no AS bill_no,
            je.cheque_date AS bill_date,
            je.due_date,
            jea.party AS supplier,
            jea.credit_in_account_currency AS credit_amount,
            jea.account_currency AS currency
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
        INNER JOIN `tabAccount` acc ON acc.name = jea.account
        WHERE {where}
        """,
        tuple(values),
        as_dict=True,
    )
    
    # Get TDS details separately
    je_names = [r.name for r in je_rows]
    tds_map = {}
    if je_names:
        placeholders = ", ".join(["%s"] * len(je_names))
        tds_rows = frappe.db.sql(
            f"""
            SELECT
                jea.parent AS je_name,
                jea.account AS tds_account,
                ABS(jea.debit_in_account_currency) AS tds_amount
            FROM `tabJournal Entry Account` jea
            WHERE jea.parent IN ({placeholders})
                AND jea.is_tax_withholding_account = 1
            """,
            tuple(je_names),
            as_dict=True,
        )
        for tds in tds_rows:
            if tds.je_name not in tds_map:
                tds_map[tds.je_name] = {"account": tds.tds_account, "amount": 0}
            tds_map[tds.je_name]["amount"] += flt(tds.tds_amount, 2)
    
    je_map = {}
    for r in je_rows:
        if r.name not in je_map:
            tds_info = tds_map.get(r.name, {})
            je_map[r.name] = frappe._dict({
                "name": r.name,
                "posting_date": r.posting_date,
                "bill_no": r.bill_no,
                "bill_date": r.bill_date,
                "due_date": r.due_date,
                "supplier": r.supplier,
                "currency": r.currency,
                "tds_account": tds_info.get("account"),
                "tds_amount": flt(tds_info.get("amount", 0), 2),
            })
        je_map[r.name].credit_amount = je_map[r.name].get("credit_amount", 0) + flt(r.credit_amount, 2)
    for je in je_map.values():
        s = frappe.db.get_value("Supplier", je.supplier, ["supplier_name", "msme", "gst_category", "tax_id"], as_dict=True)
        je.supplier_name = s.supplier_name if s else je.supplier
        je.msme = s.msme if s else None
        je.gst_category = s.gst_category if s else None
        je.tax_id = s.tax_id if s else None
    return list(je_map.values())


def _get_payment_allocations_by_je(filters):
    """Payment Entry Reference for Journal Entry."""
    conditions = [
        "per.reference_doctype = 'Journal Entry'",
        "per.allocated_amount > 0",
        "pe.docstatus = 1",
        "pe.payment_type = 'Pay'",
    ]
    values = []
    if filters.get("company"):
        conditions.append("pe.company = %s")
        values.append(filters.get("company"))
    if filters.get("to_date"):
        conditions.append("pe.posting_date <= %s")
        values.append(getdate(filters.get("to_date")))
    if filters.get("supplier"):
        conditions.append("pe.party = %s")
        values.append(filters.get("supplier"))
    if filters.get("mode_of_payment"):
        conditions.append("pe.mode_of_payment = %s")
        values.append(filters.get("mode_of_payment"))

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT
            per.reference_name AS journal_entry,
            per.parent AS payment_entry,
            per.allocated_amount,
            per.exchange_rate,
            pe.posting_date,
            pe.mode_of_payment,
            pe.status AS pe_status
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE {where}
        ORDER BY per.reference_name, pe.posting_date
        """,
        tuple(values),
        as_dict=True,
    )
    result = {}
    for r in rows:
        base_alloc = flt(r.allocated_amount, 2) * flt(r.exchange_rate or 1, 2)
        r.base_allocated_amount = base_alloc
        result.setdefault(r.journal_entry, []).append(r)
    return result


def _get_advance_payment_entries(filters):
    """Get Payment Entries that are:
    1. Advances with NO reference rows (no PI/JE/PO)
    2. Payment Entries linked ONLY to Purchase Orders (no PI/JE reference)

    These should appear in the report even though they are not tied to a Purchase Invoice.
    """
    conditions_adv = [
        "pe.docstatus = 1",
        # Include both 'Pay' (to supplier) and 'Receive' (from supplier, e.g. refund)
        "pe.party_type = 'Supplier'",
        # No reference rows at all
        "NOT EXISTS (SELECT 1 FROM `tabPayment Entry Reference` per WHERE per.parent = pe.name)",
    ]
    conditions_po = [
        "pe.docstatus = 1",
        # Include both 'Pay' and 'Receive' for supplier-related PO payments
        "pe.party_type = 'Supplier'",
        # Has at least one PO reference (may also have PI references – PO part is treated as advance)
        "EXISTS (SELECT 1 FROM `tabPayment Entry Reference` per WHERE per.parent = pe.name AND per.reference_doctype = 'Purchase Order')",
    ]
    values_adv = []
    values_po = []

    # Common filters for both queries
    def apply_common_filters(conditions, values):
        if filters.get("company"):
            conditions.append("pe.company = %s")
            values.append(filters.get("company"))
        if filters.get("from_date"):
            conditions.append("pe.posting_date >= %s")
            values.append(getdate(filters.get("from_date")))
        if filters.get("to_date"):
            conditions.append("pe.posting_date <= %s")
            values.append(getdate(filters.get("to_date")))
        if filters.get("supplier"):
            conditions.append("pe.party = %s")
            values.append(filters.get("supplier"))
        if filters.get("mode_of_payment"):
            conditions.append("pe.mode_of_payment = %s")
            values.append(filters.get("mode_of_payment"))

    apply_common_filters(conditions_adv, values_adv)
    apply_common_filters(conditions_po, values_po)

    where_adv = " AND ".join(conditions_adv)
    where_po = " AND ".join(conditions_po)

    # Advances with no references
    rows_adv = frappe.db.sql(
        f"""
        SELECT
            pe.name,
            pe.posting_date,
            pe.party AS supplier,
            pe.party_name AS supplier_name,
            pe.mode_of_payment,
            pe.status AS pe_status,
            pe.payment_type,
            pe.paid_amount,
            pe.paid_from_account_currency AS currency
        FROM `tabPayment Entry` pe
        WHERE {where_adv}
        """,
        tuple(values_adv),
        as_dict=True,
    )

    # Payments against Purchase Orders (including PEs that may ALSO be linked to Purchase Invoices)
    rows_po = frappe.db.sql(
        f"""
        SELECT
            pe.name,
            pe.posting_date,
            pe.party AS supplier,
            pe.party_name AS supplier_name,
            pe.mode_of_payment,
            pe.status AS pe_status,
            pe.payment_type,
            -- Advance portion = PO allocation in base currency
            SUM(per.allocated_amount * COALESCE(per.exchange_rate, 1)) AS paid_amount,
            pe.paid_from_account_currency AS currency,
            MIN(per.reference_name) AS purchase_order
        FROM `tabPayment Entry` pe
        INNER JOIN `tabPayment Entry Reference` per
            ON per.parent = pe.name
            AND per.reference_doctype = 'Purchase Order'
        WHERE {where_po}
        GROUP BY
            pe.name,
            pe.posting_date,
            pe.party,
            pe.party_name,
            pe.mode_of_payment,
            pe.status,
            pe.payment_type,
            pe.paid_from_account_currency
        """,
        tuple(values_po),
        as_dict=True,
    )

    # Merge both sets, keyed by Payment Entry name to avoid duplicates
    pe_map = {}
    for r in rows_adv + rows_po:
        if r.name not in pe_map:
            pe_map[r.name] = frappe._dict(r)

    # Enrich with Supplier master data (MSME, GST, etc.)
    for pe in pe_map.values():
        s = frappe.db.get_value(
            "Supplier",
            pe.supplier,
            ["supplier_name", "msme", "gst_category", "tax_id"],
            as_dict=True,
        )
        if s:
            pe.supplier_name = s.supplier_name or pe.supplier_name or pe.supplier
            pe.msme = s.msme
            pe.gst_category = s.gst_category
            pe.tax_id = s.tax_id
        else:
            pe.supplier_name = pe.supplier_name or pe.supplier
            pe.msme = None
            pe.gst_category = None
            pe.tax_id = None

    return list(pe_map.values())


def _build_je_row(je, payment, invoice_amount, paid_amount, unpaid_amount,
        overdue_amount, payment_status, delay_days, report_date=None, show_invoice_details=True):
    """Build row for standalone Journal Entry - matches Excel format (36 columns).
    
    Args:
        show_invoice_details: If False, only payment details are shown (for subsequent payment rows).
        report_date: Report date for calculating "Due in" days.
    """
    # Calculate Payment Entry Value 
    payment_entry_value = 0
    if payment:
        payment_entry_value = flt(getattr(payment, 'base_allocated_amount', None) or getattr(payment, 'allocated_amount', 0), 2)
    
    # Calculate Balance  - this is the outstanding amount
    # Balance should show outstanding only in the JE row, 0 in payment rows
    balance = unpaid_amount if show_invoice_details else 0
    
    # Due In = due_date - posting_date (for standalone JE, use JE posting_date)
    due_in = None
    if je.due_date and je.posting_date:
        due_in = (getdate(je.due_date) - getdate(je.posting_date)).days
    
    # Get TDS amount and account from JE if available
    tds_amount = getattr(je, 'tds_amount', 0) or 0
    tds_account = getattr(je, 'tds_account', None)
    
    if show_invoice_details:
        # First row: all JE details
        return {
            "PINV Date": je.posting_date,
            "Purchase Invoice": None,
            "Supplier ID": je.supplier,
            "Supplier Name": je.supplier_name,
            "Rounded Amount Net Payable": 0,  # JEs not linked to PI have no invoice amount
            "Invoice Amount": invoice_amount,
            "Taxable Amount": 0,
            "CGST Amount": 0,
            "SGST Amount": 0,
            "IGST Amount": 0,
            "Payment Date": payment.posting_date if payment else None,
            "Payment Entry": payment.payment_entry if payment else None,
            "Payment Entry Value": payment_entry_value,
            "Paid Amount": paid_amount,
            "Balance": balance,
            "Due Date": je.due_date,
            "Due in": due_in,
            "MSME": je.msme,
            "Payment Delay in Days": delay_days,
            "Payment Status": payment_status,
            "Payment Mode": payment.mode_of_payment if payment else None,
            "Payment Entry Status": payment.pe_status if payment else None,
            "Supplier Invoice No": je.bill_no,
            "Supplier Invoice Date": je.bill_date,
            "GST Category": je.gst_category,
            "GST": je.tax_id,
            "Unpaid Amount": unpaid_amount,
            "Overdue Amount": overdue_amount,
            "TDS Amount": flt(tds_amount, 2),
            "TDS Account": tds_account,
            "Currency": je.currency,
            "Purchase Order": None,
            "Purchase Receipt": None,
            "Purchase Receipt Date": None,
            "Journal Entry": je.name,
            "Journal Entry Ref": je.name,  # Same as Journal Entry
            "Purchase Invoice Status": None,
        }
    else:
        # Subsequent payment rows: only payment entry details
        return {
            "PINV Date": None,
            "Purchase Invoice": None,
            "Supplier ID": je.supplier,  # Keep for reference
            "Supplier Name": je.supplier_name,  # Keep for reference
            "Rounded Amount Net Payable": 0,
            "Invoice Amount": 0,
            "Taxable Amount": 0,
            "CGST Amount": 0,
            "SGST Amount": 0,
            "IGST Amount": 0,
            "Payment Date": payment.posting_date if payment else None,
            "Payment Entry": payment.payment_entry if payment else None,
            "Payment Entry Value": payment_entry_value,
            "Paid Amount": paid_amount,
            "Balance": 0,
            "Due Date": None,
            "Due in": None,
            "MSME": None,
            "Payment Delay in Days": None,
            "Payment Status": None,
            "Payment Mode": payment.mode_of_payment if payment else None,
            "Payment Entry Status": payment.pe_status if payment else None,
            "Supplier Invoice No": None,
            "Supplier Invoice Date": None,
            "GST Category": None,
            "GST": None,
            "Unpaid Amount": 0,
            "Overdue Amount": 0,
            "TDS Amount": 0,
            "TDS Account": None,
            "Currency": je.currency,
            "Purchase Order": None,
            "Purchase Receipt": None,
            "Purchase Receipt Date": None,
            "Journal Entry": je.name,  # Keep for reference
            "Journal Entry Ref": None,
            "Purchase Invoice Status": None,
        }


def _build_advance_payment_row(pe, report_date=None):
    """Build row for advance / Purchase Order Payment Entry (no PI/JE reference).

    These are:
      1. Payment Entries without any reference rows (pure advance to supplier)
      2. Payment Entries whose reference_doctype is 'Purchase Order'
    """
    # Payment Entry Value in report is always base/company currency
    # For advances/PO payments we use paid_amount (company currency or party currency,
    # depending on configuration). This is best-effort representation.
    payment_entry_value = flt(getattr(pe, "paid_amount", 0), 2)

    # Direction handling:
    # - If company is paying supplier (payment_type = "Pay"): keep value positive
    # - If supplier is paying company (payment_type = "Receive"): show value as negative
    if getattr(pe, "payment_type", None) == "Receive":
        payment_entry_value = -payment_entry_value

    # No invoice context for pure advances in this report
    # Invoice Amount must be 0.
    # Balance:
    #   - For "Pay" (advance to supplier): negative (advance / excess payment)
    #   - For "Receive" (refund from supplier): positive
    invoice_amount = 0
    unpaid_amount = 0
    overdue_amount = 0
    balance = -payment_entry_value

    # Due Date and Due In do not apply to standalone advances/PO payments
    due_date = None
    due_in = None

    return {
        "PINV Date": None,
        "Purchase Invoice": None,
        "Supplier ID": pe.supplier,
        "Supplier Name": pe.supplier_name,
        "Rounded Amount Net Payable": 0,
        "Invoice Amount": invoice_amount,
        "Taxable Amount": 0,
        "CGST Amount": 0,
        "SGST Amount": 0,
        "IGST Amount": 0,
        "Payment Date": pe.posting_date,
        "Payment Entry": pe.name,
        "Payment Entry Value": payment_entry_value,
        "Paid Amount": payment_entry_value,
        "Balance": balance,
        "Due Date": due_date,
        "Paid Date": None,
        "Due in": due_in,
        "MSME": pe.msme,
        "Payment Delay in Days": None,
        "Payment Status": None,
        "Payment Mode": pe.mode_of_payment,
        "Payment Entry Status": pe.pe_status,
        "Supplier Invoice No": None,
        "Supplier Invoice Date": None,
        "GST Category": pe.gst_category,
        "GST": pe.tax_id,
        "Unpaid Amount": unpaid_amount,
        "Overdue Amount": overdue_amount,
        "TDS Amount": 0,
        "TDS Account": None,
        "Currency": pe.currency,
        "Purchase Order": getattr(pe, "purchase_order", None),
        "Purchase Receipt": None,
        "Purchase Receipt Date": None,
        "Journal Entry": None,
        "Journal Entry Ref": None,
        "Purchase Invoice Status": None,
    }


def _add_total_row(data):
    """Add total row – Invoice Amount and Unpaid Amount counted once per voucher (no double-count).
    Also totals other currency columns."""
    if not data:
        return data
    columns = list(data[0].keys())
    total_invoice = total_paid = total_unpaid = total_overdue = 0
    total_rounded = total_taxable = total_cgst = total_sgst = total_igst = total_tds = 0
    total_balance = total_payment_entry_value = 0
    seen_vouchers = set()

    for row in data:
        # Unique voucher: PI or JE
        voucher_key = ("PI", row.get("Purchase Invoice")) if row.get("Purchase Invoice") else ("JE", row.get("Journal Entry"))
        if voucher_key not in seen_vouchers:
            seen_vouchers.add(voucher_key)
            total_invoice += flt(row.get("Invoice Amount"), 2)
            total_unpaid += flt(row.get("Unpaid Amount"), 2)
            total_overdue += flt(row.get("Overdue Amount"), 2)
            total_rounded += flt(row.get("Rounded Amount Net Payable"), 2)
            total_taxable += flt(row.get("Taxable Amount"), 2)
            total_cgst += flt(row.get("CGST Amount"), 2)
            total_sgst += flt(row.get("SGST Amount"), 2)
            total_igst += flt(row.get("IGST Amount"), 2)
            total_tds += flt(row.get("TDS Amount"), 2)
            total_balance += flt(row.get("Balance"), 2)
        total_paid += flt(row.get("Paid Amount"), 2)
        total_payment_entry_value += flt(row.get("Payment Entry Value"), 2)

    total_row = {col: "" for col in columns}
    total_row[columns[0]] = "Total"
    total_row["Rounded Amount Net Payable"] = total_rounded
    total_row["Invoice Amount"] = total_invoice
    total_row["Taxable Amount"] = total_taxable
    total_row["CGST Amount"] = total_cgst
    total_row["SGST Amount"] = total_sgst
    total_row["IGST Amount"] = total_igst
    total_row["Payment Entry Value"] = total_payment_entry_value
    total_row["Paid Amount"] = total_paid
    total_row["Balance"] = total_balance
    total_row["Unpaid Amount"] = total_unpaid
    total_row["Overdue Amount"] = total_overdue
    total_row["TDS Amount"] = total_tds
    data.append(total_row)
    return data


# ---------------------------------------------------------------------------
# COLUMNS – matches Excel format (Query Report sheet)
# ---------------------------------------------------------------------------

def get_columns():
    """Return columns matching Excel sheet exactly (36 columns)."""
    return [
        {"label": "PINV Date", "fieldname": "PINV Date", "fieldtype": "Date", "width": 100},
        {"label": "Purchase Invoice", "fieldname": "Purchase Invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
        {"label": "Supplier ID", "fieldname": "Supplier ID", "fieldtype": "Link", "options": "Supplier", "width": 120},
        {"label": "Supplier Name", "fieldname": "Supplier Name", "fieldtype": "Data", "width": 150},
        {"label": "Rounded Amount\nNet Payable\n", "fieldname": "Rounded Amount Net Payable", "fieldtype": "Currency", "width": 130},
        {"label": "(Total (INR) + Taxes & Charges)\nInvoice Amount", "fieldname": "Invoice Amount", "fieldtype": "Currency", "width": 150},
        {"label": "Taxable Amount", "fieldname": "Taxable Amount", "fieldtype": "Currency", "width": 120},
        {"label": "CGST Amount", "fieldname": "CGST Amount", "fieldtype": "Currency", "width": 100},
        {"label": "SGST Amount", "fieldname": "SGST Amount", "fieldtype": "Currency", "width": 100},
        {"label": "IGST Amount", "fieldname": "IGST Amount", "fieldtype": "Currency", "width": 100},
        {"label": "Payment Date", "fieldname": "Payment Date", "fieldtype": "Date", "width": 100},
        {"label": "Payment Entry", "fieldname": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "width": 130},
        {"label": "Payment Entry Value\n", "fieldname": "Payment Entry Value", "fieldtype": "Currency", "width": 130},
        {"label": "Paid Amount", "fieldname": "Paid Amount", "fieldtype": "Currency", "width": 120},
        {"label": "Balance\n", "fieldname": "Balance", "fieldtype": "Currency", "width": 120},
        {"label": "Due Date (Automatically updated)", "fieldname": "Due Date", "fieldtype": "Date", "width": 150},
        {"label": "Paid Date", "fieldname": "Paid Date", "fieldtype": "Date", "width": 120},
        {"label": "Due in", "fieldname": "Due in", "fieldtype": "Int", "width": 80},
        {"label": "MSME", "fieldname": "MSME", "fieldtype": "Select", "width": 80},
        {"label": "Payment Delay in Days", "fieldname": "Payment Delay in Days", "fieldtype": "Int", "width": 120},
        {"label": "Payment Status", "fieldname": "Payment Status", "fieldtype": "Select", "options": "On Time\nDelay", "width": 100},
        {"label": "Payment Mode", "fieldname": "Payment Mode", "fieldtype": "Link", "options": "Mode of Payment", "width": 120},
        {"label": "Payment Entry Status", "fieldname": "Payment Entry Status", "fieldtype": "Data", "width": 120},
        {"label": "Supplier Invoice No", "fieldname": "Supplier Invoice No", "fieldtype": "Data", "width": 120},
        {"label": "Supplier Invoice Date", "fieldname": "Supplier Invoice Date", "fieldtype": "Date", "width": 120},
        {"label": "GST Category", "fieldname": "GST Category", "fieldtype": "Select", "width": 100},
        {"label": "GST", "fieldname": "GST", "fieldtype": "Data", "width": 120},
        {"label": "Unpaid Amount", "fieldname": "Unpaid Amount", "fieldtype": "Currency", "width": 120},
        {"label": "Overdue Amount", "fieldname": "Overdue Amount", "fieldtype": "Currency", "width": 120},
        {"label": "TDS Amount", "fieldname": "TDS Amount", "fieldtype": "Currency", "width": 100},
        {"label": "TDS Account", "fieldname": "TDS Account", "fieldtype": "Data", "width": 140},
        {"label": "Currency", "fieldname": "Currency", "fieldtype": "Link", "options": "Currency", "width": 80},
        {"label": "Purchase Order", "fieldname": "Purchase Order", "fieldtype": "Link", "options": "Purchase Order", "width": 130},
        {"label": "Purchase Receipt", "fieldname": "Purchase Receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 130},
        {"label": "Purchase Receipt Date", "fieldname": "Purchase Receipt Date", "fieldtype": "Date", "width": 120},
        {"label": "Journal Entry", "fieldname": "Journal Entry", "fieldtype": "Link", "options": "Journal Entry", "width": 130},
        {"label": "Journal Entry Ref\n", "fieldname": "Journal Entry Ref", "fieldtype": "Link", "options": "Journal Entry", "width": 130},
        {"label": "Purchase Invoice Status", "fieldname": "Purchase Invoice Status", "fieldtype": "Data", "width": 120},
    ]


# ---------------------------------------------------------------------------
# DEBUG HELPERS (can be removed later)
# ---------------------------------------------------------------------------

def debug_payment_entry():
    """Temporary helper to inspect a specific Payment Entry and its references.
    Hardcoded to ACC-PAY-2026-00586 for current debugging."""
    pe_name = "ACC-PAY-2026-00586"
    pe = frappe.db.get_value(
        "Payment Entry",
        pe_name,
        ["name", "posting_date", "company", "party", "party_type", "payment_type", "mode_of_payment", "status", "paid_amount"],
        as_dict=True,
    )
    refs = frappe.db.sql(
        """
        SELECT
            parent,
            reference_doctype,
            reference_name,
            allocated_amount
        FROM `tabPayment Entry Reference`
        WHERE parent = %s
        """,
        (pe_name,),
        as_dict=True,
    )
    return {"payment_entry": pe, "references": refs}


def debug_pe_with_po_and_pi():
    """Helper to inspect Payment Entries that have references to both Purchase Order and Purchase Invoice."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT pe.name
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
          AND pe.party_type = 'Supplier'
          AND EXISTS (
                SELECT 1 FROM `tabPayment Entry Reference` per
                WHERE per.parent = pe.name AND per.reference_doctype = 'Purchase Order'
          )
          AND EXISTS (
                SELECT 1 FROM `tabPayment Entry Reference` per2
                WHERE per2.parent = pe.name AND per2.reference_doctype = 'Purchase Invoice'
          )
        ORDER BY pe.posting_date DESC
        LIMIT 10
        """,
        as_dict=True,
    )
    details = []
    for r in rows:
        refs = frappe.db.sql(
            """
            SELECT
                parent,
                reference_doctype,
                reference_name,
                allocated_amount,
                exchange_rate
            FROM `tabPayment Entry Reference`
            WHERE parent = %s
            """,
            (r.name,),
            as_dict=True,
        )
        pe = frappe.db.get_value(
            "Payment Entry",
            r.name,
            ["name", "posting_date", "company", "party", "party_type", "payment_type", "mode_of_payment", "status", "paid_amount"],
            as_dict=True,
        )
        details.append({"payment_entry": pe, "references": refs})
    return details

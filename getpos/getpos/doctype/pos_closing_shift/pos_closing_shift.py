# -*- coding: utf-8 -*-
# Copyright (c) 2020, NestorBird and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class POSClosingShift(Document):
    def validate(self):
        user = frappe.get_all('POS Closing Shift',
                              filters={'user': self.user, 'docstatus': 1},
                              or_filters={
                                  'period_start_date': ('between', [self.period_start_date, self.period_end_date]),
                                  'period_end_date': ('between', [self.period_start_date, self.period_end_date])
                              })

        if user:
            frappe.throw(_("POS Closing Shift {} against {} between selected period"
                           .format(frappe.bold("already exists"), frappe.bold(self.user))), title=_("Invalid Period"))

        if frappe.db.get_value("POS Opening Shift", self.pos_opening_shift, "status") != "Open":
            frappe.throw(_("Selected POS Opening Shift should be open."), title=_(
                "Invalid Opening Entry"))
        self.update_payment_reconciliation()
    
    def update_payment_reconciliation(self):
        # update the difference values in Payment Reconciliation child table
        # get default precision for site
        precision = frappe.get_cached_value('System Settings', None, 'currency_precision') or 3
        for d in self.payment_reconciliation:
            d.difference = flt(d.opening_amount, precision) + flt(d.closing_amount, precision) - flt(d.expected_amount, precision)

    def on_submit(self):
        opening_entry = frappe.get_doc(
            "POS Opening Shift", self.pos_opening_shift)
        opening_entry.pos_closing_shift = self.name
        opening_entry.set_status()
        # self.delete_draft_invoices()
        opening_entry.save()

    def delete_draft_invoices(self):
        if frappe.get_value("POS Profile", self.pos_profile, "posa_allow_delete"):
            data = frappe.db.sql("""
                select
                    name
                from
                    `tabSales Invoice`
                where
                    docstatus = 0 and posa_is_printed = 0 and posa_pos_opening_shift = %s
                """, (self.pos_opening_shift), as_dict=1)

            for invoice in data:
                frappe.delete_doc("Sales Invoice", invoice.name, force=1)

    def get_payment_reconciliation_details(self):
        currency = frappe.get_cached_value(
            'Company', self.company,  "default_currency")
        return frappe.render_template("getpos/getpos/doctype/pos_closing_shift/closing_shift_details.html",
                                      {"data": self, "currency": currency})


@frappe.whitelist()
def get_cashiers(doctype, txt, searchfield, start, page_len, filters):
    cashiers_list = frappe.get_all(
        "POS Profile User", filters=filters, fields=['user'])
    return [c['user'] for c in cashiers_list]


@frappe.whitelist()
def get_pos_invoices(pos_opening_shift):
    submit_printed_invoices(pos_opening_shift)
    data = frappe.db.sql("""
	select
		name
	from
		`tabSales Invoice`
	where
		docstatus = 1 and posa_pos_opening_shift = %s
	""", (pos_opening_shift), as_dict=1)

    data = [frappe.get_doc("Sales Invoice", d.name).as_dict() for d in data]

    return data


@frappe.whitelist()
def make_closing_shift_from_opening(opening_shift):
    res = frappe._dict()
    if isinstance(opening_shift, str):
        opening_shift = json.loads(opening_shift)
    submit_printed_invoices(opening_shift.get("name"))
    closing_shift = frappe.new_doc("POS Closing Shift")
    closing_shift.pos_opening_shift = opening_shift.get("name")
    closing_shift.period_start_date = opening_shift.get("period_start_date")
    closing_shift.period_end_date = frappe.utils.get_datetime()
    closing_shift.pos_profile = opening_shift.get("pos_profile")
    closing_shift.user = opening_shift.get("user")
    closing_shift.company = opening_shift.get("company")
    closing_shift.grand_total = 0
    closing_shift.net_total = 0
    closing_shift.total_quantity = 0

    invoices = get_pos_invoices(opening_shift.get("name"))

    pos_transactions = []
    taxes = []
    payments = []
    for detail in opening_shift.get("balance_details"):
        payments.append(frappe._dict({
            'mode_of_payment': detail.get("mode_of_payment"),
            'opening_amount': detail.get("amount") or 0,
            'expected_amount': detail.get("amount") or 0
        }))

    for d in invoices:
        pos_transactions.append(frappe._dict({
            'sales_invoice': d.name,
            'posting_date': d.posting_date,
            'grand_total': d.grand_total,
            'customer': d.customer
        }))
        closing_shift.grand_total += flt(d.grand_total)
        closing_shift.net_total += flt(d.net_total)
        closing_shift.total_quantity += flt(d.total_qty)

        for t in d.taxes:
            existing_tax = [tx for tx in taxes if tx.account_head ==
                            t.account_head and tx.rate == t.rate]
            if existing_tax:
                existing_tax[0].amount += flt(t.tax_amount)
            else:
                taxes.append(frappe._dict({
                    'account_head': t.account_head,
                    'rate': t.rate,
                    'amount': t.tax_amount
                }))

        for p in d.payments:
            existing_pay = [
                pay for pay in payments if pay.mode_of_payment == p.mode_of_payment]
            if existing_pay:
                cash_mode_of_payment = frappe.get_value(
                    "POS Profile", opening_shift.get("pos_profile"), "posa_cash_mode_of_payment")
                if not cash_mode_of_payment:
                    cash_mode_of_payment = "Cash"
                if existing_pay[0].mode_of_payment == cash_mode_of_payment:
                    amount = p.amount - d.change_amount
                else:
                    amount = p.amount
                existing_pay[0].expected_amount += flt(amount)
            else:
                payments.append(frappe._dict({
                    'mode_of_payment': p.mode_of_payment,
                    'opening_amount': 0,
                    'expected_amount': p.amount
                }))

    closing_shift.set("pos_transactions", pos_transactions)
    closing_shift.set("payment_reconciliation", payments)
    closing_shift.set("taxes", taxes)
    
    return closing_shift


@frappe.whitelist()
def submit_closing_shift(closing_shift):
    if isinstance(closing_shift, str):
        closing_shift = json.loads(closing_shift)
    closing_shift_doc = frappe.get_doc(closing_shift)
    closing_shift_doc.flags.ignore_permissions = True
    closing_shift_doc.save()
    closing_shift_doc.submit()
    return closing_shift_doc.name

@frappe.whitelist()
def get_shift_details(opening_shift):
    res = frappe._dict()
    closing_balance = frappe.db.sql(
            """SELECT   
            IFNULL(SUM(CASE WHEN si.is_return = 0 THEN sii.base_net_amount ELSE 0 END),0) AS sales_order_amount,
            IFNULL(SUM(CASE WHEN si.is_return = 1 THEN sii.base_net_amount ELSE 0 END),0) AS return_order_amount,
            IFNULL(SUM(CASE WHEN si.is_return = 0 and si.mode_of_payment="Cash" THEN si.base_net_total ELSE 0 END) + SUM(CASE WHEN si.is_return = 1 and si.mode_of_payment="Cash" THEN si.base_net_total ELSE 0 END),0) AS cash_collected,
            IFNULL(SUM(CASE WHEN si.is_return = 0 and si.mode_of_payment="Credit" THEN si.base_net_total ELSE 0 END) + SUM(CASE WHEN si.is_return = 1 and si.mode_of_payment="Credit" THEN si.base_net_total ELSE 0 END),0) AS credit_collected,           
            IFNULL(SUM(CASE WHEN si.is_return = 0 THEN si.base_net_total ELSE 0 END) + SUM(CASE WHEN si.is_return = 1 THEN si.base_net_total ELSE 0 END),0) AS total_sales_order_amount
        FROM 
            `tabPOS Opening Shift` pos
            LEFT JOIN `tabSales Order` so ON pos.name = so.custom_pos_shift
            LEFT JOIN `tabSales Invoice Item` sii ON sii.sales_order = so.name
            LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent
            LEFT JOIN `tabSales Invoice Payment` sip ON si.name = sip.parent
            LEFT JOIN `tabPOS Opening Shift Detail` posd ON pos.name = posd.parent
        WHERE          
             pos.name=%s""",
            (opening_shift.get("name")), as_dict=True
        )
    
    res['opening_balance']=frappe.db.get_value("POS Opening Shift Detail", {"parent":opening_shift.get("name")}, ["mode_of_payment","amount"])
    res['Shift_Detail']=closing_balance
    return res

def submit_printed_invoices(pos_opening_shift):
    invoices_list = frappe.get_all("Sales Invoice", filters={
        "posa_pos_opening_shift": pos_opening_shift,
        "docstatus": 0,
        "posa_is_printed": 1
    })
    for invoice in invoices_list:
        invoice_doc = frappe.get_doc("Sales Invoice", invoice.name)
        invoice_doc.submit()

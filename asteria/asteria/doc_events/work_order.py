import frappe

def validate(self, method):
    trigger_method = "validate"
    update_order_quantity(self, trigger_method)

def on_submit(self, method=None):
    trigger_method = "on_submit"
    update_order_quantity(self, trigger_method)

def on_cancel(self, method=None):
    trigger_method = "on_cancel"
    update_order_quantity(self, trigger_method)

def on_trash(self, method=None):
    trigger_method = "on_trash"
    update_order_quantity(self, trigger_method)

def update_order_quantity(self, trigger_method):
    if not self.production_plan:
        return
    
    condition = ''
    if self.production_plan_sub_assembly_item:
        condition += f" and production_plan_sub_assembly_item = '{self.production_plan_sub_assembly_item}'"
    
    if self.production_plan_item:
        condition += f" and production_plan_item = '{self.production_plan_item}'"
    
    # Get draft work orders quantity (excluding current document if it's in draft)
    # For on_trash, we don't exclude current document since it's being deleted
    name_condition = f"and name != '{self.name}'" if trigger_method != "on_trash" else ""
    
    work_order_data_draft = frappe.db.sql(f"""
                        Select sum(qty) as qty
                        From `tabWork Order`
                        Where docstatus = 0 {name_condition}
                        {condition}
                    """, as_dict=1)
    
    draft_qty = work_order_data_draft[0].qty or 0
    
    # Get submitted work orders quantity for remaining calculation
    work_order_data_submitted = frappe.db.sql(f"""
                        Select sum(qty) as qty
                        From `tabWork Order`
                        Where docstatus = 1 {name_condition}
                        {condition}
                    """, as_dict=1)
    
    submitted_qty = work_order_data_submitted[0].qty or 0
    
    # If current document is being submitted (changing from draft to submitted)
    if trigger_method == "on_submit" and self.docstatus == 1:
        # Remove this work order's quantity from ordered_in_draft
        if self.production_plan_item:
            current_ordered_draft = frappe.db.get_value("Production Plan Item", 
                                                       self.production_plan_item, 
                                                       "ordered_in_draft") or 0
            new_ordered_draft = max(0, current_ordered_draft - self.qty)
            frappe.db.set_value("Production Plan Item", 
                              self.production_plan_item, 
                              "ordered_in_draft", 
                              new_ordered_draft)
            
            # Update remaining quantity
            update_remaining_qty_for_plan_item(self, trigger_method)
        
        if self.production_plan_sub_assembly_item:
            current_ordered_draft = frappe.db.get_value("Production Plan Sub Assembly Item", 
                                                       self.production_plan_sub_assembly_item, 
                                                       "ordered_in_draft") or 0
            new_ordered_draft = max(0, current_ordered_draft - self.qty)
            frappe.db.set_value("Production Plan Sub Assembly Item", 
                              self.production_plan_sub_assembly_item, 
                              "ordered_in_draft", 
                              new_ordered_draft)
            
            # Update remaining quantity
            update_remaining_qty_for_sub_assembly_item(self, trigger_method)
    
    # For draft documents, update ordered_in_draft with total draft quantity
    elif self.docstatus == 0 and trigger_method == "validate":
        # Calculate total draft quantity including current document
        total_draft_qty = draft_qty + self.qty
        
        if self.production_plan_item:
            planned_qty = frappe.db.get_value("Production Plan Item", 
                                            self.production_plan_item, 
                                            "planned_qty")
            if total_draft_qty and planned_qty and total_draft_qty > planned_qty:
                frappe.throw(f"Planned quantity is {planned_qty}. Work Order is already created for {abs(total_draft_qty - self.qty)} in draft.")
            
            frappe.db.set_value("Production Plan Item", 
                              self.production_plan_item, 
                              "ordered_in_draft", 
                              total_draft_qty)
            
            # Update remaining quantity
            update_remaining_qty_for_plan_item(self, trigger_method)
        
        if self.production_plan_sub_assembly_item:
            planned_qty = frappe.db.get_value("Production Plan Sub Assembly Item", 
                                            self.production_plan_sub_assembly_item, 
                                            "qty")
            if total_draft_qty and planned_qty and total_draft_qty > planned_qty:
                frappe.throw(f"Planned quantity is {planned_qty}. Work Order is already created for {abs(total_draft_qty - self.qty)} in draft.")
            
            frappe.db.set_value("Production Plan Sub Assembly Item", 
                              self.production_plan_sub_assembly_item, 
                              "ordered_in_draft", 
                              total_draft_qty)
            
            # Update remaining quantity
            update_remaining_qty_for_sub_assembly_item(self, trigger_method)
    
    # For cancelled documents
    elif trigger_method == "on_cancel" and self.docstatus == 2:
        remove_work_order_quantity(self, trigger_method)
    
    # For permanent deletion
    elif trigger_method == "on_trash":
        remove_work_order_quantity(self, trigger_method)

def remove_work_order_quantity(self, trigger_method):
    """Common method to remove work order quantity from plan items"""
    # Remove quantity from ordered_in_draft for draft documents
    if self.docstatus == 0:  # If it was a draft
        if self.production_plan_item:
            current_ordered_draft = frappe.db.get_value("Production Plan Item", 
                                                       self.production_plan_item, 
                                                       "ordered_in_draft") or 0
            new_ordered_draft = max(0, current_ordered_draft - self.qty)
            frappe.db.set_value("Production Plan Item", 
                              self.production_plan_item, 
                              "ordered_in_draft", 
                              new_ordered_draft)
        
        if self.production_plan_sub_assembly_item:
            current_ordered_draft = frappe.db.get_value("Production Plan Sub Assembly Item", 
                                                       self.production_plan_sub_assembly_item, 
                                                       "ordered_in_draft") or 0
            new_ordered_draft = max(0, current_ordered_draft - self.qty)
            frappe.db.set_value("Production Plan Sub Assembly Item", 
                              self.production_plan_sub_assembly_item, 
                              "ordered_in_draft", 
                              new_ordered_draft)
    
    # If it was a submitted document being cancelled/deleted
    elif self.docstatus == 1:  # If it was submitted
        # No need to adjust ordered_in_draft as submitted docs don't count in draft
        pass
    
    # Update remaining quantity for both plan items
    if self.production_plan_item:
        update_remaining_qty_for_plan_item(self, trigger_method)
    
    if self.production_plan_sub_assembly_item:
        update_remaining_qty_for_sub_assembly_item(self, trigger_method)

def update_remaining_qty_for_plan_item(self, trigger_method):
    """Update remaining quantity for Production Plan Item"""
    if not self.production_plan_item:
        return
    
    # For on_trash, we don't exclude current document since it's being deleted
    name_condition = "and name != %s" if self.name and trigger_method != "on_trash" else ""
    params = [self.production_plan_item]
    if name_condition:
        params.append(self.name)
    
    work_order_data = frappe.db.sql(f"""
                        Select 
                            sum(case when docstatus = 0 then qty else 0 end) as draft_qty,
                            sum(case when docstatus = 1 then qty else 0 end) as submitted_qty
                        From `tabWork Order`
                        Where production_plan_item = %s
                        {name_condition}
                    """, tuple(params), as_dict=1)
    
    draft_qty = work_order_data[0].draft_qty or 0
    submitted_qty = work_order_data[0].submitted_qty or 0
    
    # Get planned quantity
    plan_item = frappe.db.get_value("Production Plan Item", 
                                   self.production_plan_item, 
                                   ["planned_qty", "ordered_qty"], 
                                   as_dict=1)
    
    if plan_item:
        # Calculate remaining quantity
        # remaining = planned_qty - (submitted_qty + draft_qty)
        remaining_qty = max(0, (plan_item.planned_qty or 0) - (submitted_qty + draft_qty))
        
        # Update remaining_qty field
        frappe.db.set_value("Production Plan Item", 
                          self.production_plan_item, 
                          "remaining_qty", 
                          remaining_qty)
        
        # Update ordered_qty (total submitted)
        frappe.db.set_value("Production Plan Item", 
                          self.production_plan_item, 
                          "ordered_qty", 
                          submitted_qty)

def update_remaining_qty_for_sub_assembly_item(self, trigger_method):
    """Update remaining quantity for Production Plan Sub Assembly Item"""
    if not self.production_plan_sub_assembly_item:
        return
    
    # For on_trash, we don't exclude current document since it's being deleted
    name_condition = "and name != %s" if self.name and trigger_method != "on_trash" else ""
    params = [self.production_plan_sub_assembly_item]
    if name_condition:
        params.append(self.name)
    
    work_order_data = frappe.db.sql(f"""
                        Select 
                            sum(case when docstatus = 0 then qty else 0 end) as draft_qty,
                            sum(case when docstatus = 1 then qty else 0 end) as submitted_qty
                        From `tabWork Order`
                        Where production_plan_sub_assembly_item = %s
                        {name_condition}
                    """, tuple(params), as_dict=1)
    
    draft_qty = work_order_data[0].draft_qty or 0
    submitted_qty = work_order_data[0].submitted_qty or 0
    
    # Get planned quantity
    sub_assembly_item = frappe.db.get_value("Production Plan Sub Assembly Item", 
                                           self.production_plan_sub_assembly_item, 
                                           ["qty", "ordered_qty"], 
                                           as_dict=1)
    
    if sub_assembly_item:
        # Calculate remaining quantity
        # remaining = planned_qty - (submitted_qty + draft_qty)
        remaining_qty = max(0, (sub_assembly_item.qty or 0) - (submitted_qty + draft_qty))
        
        # Update remaining_qty field
        frappe.db.set_value("Production Plan Sub Assembly Item", 
                          self.production_plan_sub_assembly_item, 
                          "remaining_qty", 
                          remaining_qty)
        
        # Update ordered_qty (total submitted)
        frappe.db.set_value("Production Plan Sub Assembly Item", 
                          self.production_plan_sub_assembly_item, 
                          "ordered_qty", 
                          submitted_qty)
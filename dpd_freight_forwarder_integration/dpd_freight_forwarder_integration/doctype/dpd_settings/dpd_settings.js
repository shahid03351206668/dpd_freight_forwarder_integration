// Copyright (c) 2026, Codes Soft and contributors
// For license information, please see license.txt

frappe.ui.form.on("DPD Settings", {
    refresh(frm){
        if (!frm.doc.__local && frm.doc.enabled){
            frm.add_custom_button(("Establish Connection"), ()=>{
                let is_valid = validate_current_auth_token(frm)
                if (!is_valid){
                    test_connection(frm)
                }
                else{
                    frappe.msgprint({title:'Token Validation', indicator:"green", message:"Current Authentication Token is Valid"})
                }
            })    
        }
    }

});

function test_connection(frm){
    if(frm.doc.delis_id && frm.doc.password && frm.doc.message_language && frm.doc.api_environment){
        frappe.call({
            method:"dpd_freight_forwarder_integration.dpd_freight_forwarder_integration.doctype.dpd_settings.dpd_settings.test_connection",
            args:{
                doc:frm.doc
            },
            callback:function(res){
                let data = res.message;
                let indicator, message;
                if(data){
                    indicator = 'green';
                    message = "Connection Established Successfully"; 
                }
                else{
                    indicator = 'red';
                    message = "Failed to Establish Connection";
                }
                frappe.msgprint({
                    title:("Connection Response"),
                    indicator: indicator,
                    message: message
                })
            }
        })
    }
    else{
        frappe.msgprint("DELIS ID, Password, API Environment, Message Language is Required to Establish a Connection")
    }
}

function validate_current_auth_token(frm){
    if (frm.doc.token_expires_on){
        let from_date = new Date(frm.doc.token_expires_on);
        let today = new Date()
        if (from_date < today){
            return false // returns false when token expires
        }
        else if(from_date > today){
            return true // returns true when token is valid
        }
        else if(from_date == today){
            if (from_date.getTime() < today.getTime()){
                return true // returns true when token is valid
            }
            else{
                return false // returns false when token expires
            }
        }
    }
}
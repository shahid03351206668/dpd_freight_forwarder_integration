# Copyright (c) 2026, Codes Soft and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cstr, cint, flt
import requests
import json

class DPDSettings(Document):
    def validate(self):
        check_mandatory(self)
    
def check_mandatory(self):
    if not self.delis_id:
        frappe.throw("DELIS ID is Required to Establish Connection")	
    if not self.password:
        frappe.throw("Password is Required to Establish Connection")	
    if not self.message_language:
        frappe.throw("Message Language is Required")

def make_call(
    url, method, headers=None, payload=None, throw_error=True, json_response=True
):
    if payload:
        payload = json.dumps(payload)
    response = requests.request(method, url, headers=headers, data=payload)
    if response.status_code == 200:
        return response.json() if json_response else response.text
    else:
        frappe.log_error(
            "DPD Call failed",
            f"URL:{url},\nMethod:{method},\nHeaders:{headers},\nPayload:{payload},\nReason:{response.reason},\nText:{response.text}",
        )
        if throw_error:
            frappe.throw(str(response.text) + "<br><b>PayLoad</b>: " + str(payload))
            return False
        else:
            return {}

@frappe.whitelist()
def test_connection(doc=None):
    status = False
    if not doc:
        return status
    try:
        doc = frappe.get_doc("DPD Settings", "DPD Settings")
        if doc.rest_api_base_url and doc.message_language and doc.password and doc.delis_id:
            error_message = None
            status = True
            headers = {"Content-Type": "application/json"}
            doc.auth_token = ""
            doc.token_expires_on = None
            payload = {"delisID": doc.delis_id, "password": doc.password, "messageLanguage": doc.message_language}
            response_json = make_call(cstr(doc.rest_api_base_url), "POST", headers, payload)
            timestamp = frappe.utils.now()
            if response_json:
                filters = {
                    "method": f"{doc.rest_api_base_url}",
                    "response_status": None,
                    "request_payload": payload,
                    "response_json": response_json,
                    "timestamp": timestamp,
                    "error_message": None,
                    "dpd_settings": True
                }
                response_object = response_json.get("getAuthResponse").get("return")
                token = response_object.get("authToken")
                expires_on = response_object.get("authTokenExpires")
                if response_object.get("status"):
                    error_message = response_object.get("status").get("message")
                if token and expires_on:
                    filters['response_status'] = "Success"
                    doc.auth_token = token
                    doc.token_expires_on = expires_on
                    if response_object.get("customerUid"):
                        doc.customer_id = response_object.get("customerUid")
                    if response_object.get("depot"):
                        doc.depot = response_object.get("depot")
                    doc.flags.ignore_permissions = True
                    doc.save()
                    create_api_log(filters)
                else:
                    filters['response_status'] = "Failed"
                    filters["error_message"] = error_message
                    create_api_log(filters)
    except Exception as e:
        frappe.log_error(message=f"Error Testing Connection:{e}", title="DPD Settings Connection Error")
        status = False
    return status	

def create_api_log(filters=None):
    if filters:
        if filters.get("method") and filters.get("response_status") and filters.get("request_payload") and filters.get("response_json") and filters.get("timestamp"):    
            try:
                doc = frappe.new_doc("DPD API Log")
                doc.method = filters.get("method")
                doc.status = filters.get("response_status")
                doc.request_payload = json.dumps(filters.get("request_payload"))
                doc.response_payload = json.dumps(filters.get("response_json"))
                doc.timestamp = filters.get("timestamp")
                if filters.get("reference_document") and filters.get("reference_record"):
                    doc.reference_document = filters.get("reference_document")
                    doc.reference_record = filters.get("reference_record")
                if filters.get("dpd_settings"):
                    doc.dpd_settings = 1
                if filters.get("error_message"):
                    doc.error_message = filters.get("error_message")
                doc.flags.ignore_permissions = True
                doc.save()
                return doc.name
            except Exception as e:
                frappe.log_error(message=f"""Error Creating DPD API Log From DPD: {e}""", title="Creation of DPD API Log From DPD Settings")
    else:
        frappe.msgprint("Failed to Create API Log")
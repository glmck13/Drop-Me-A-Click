#!/usr/bin/env python3

import sys, os, json
import requests
from urllib.parse import parse_qs
from getenv import *

# Disable IPv6 for Soracom API
requests.packages.urllib3.util.connection.HAS_IPV6 = False

def insert_html_header():
    with open("header.html") as f:
        print(f.read())

def insert_html_footer():
    with open("footer.html") as f:
        print(f.read())

def insert_html_login():
    with open("login.html") as f:
        print(f.read())

def delete_group():
    global groupId, authKeyId

    requests.delete("{}/operators/{}/auth_keys/{}".format(SORACOM_URL, OperatorId, authKeyId), headers=auth_hdr)
    authKeyId = ""
    requests.delete("{}/groups/{}".format(SORACOM_URL, groupId), headers=auth_hdr)
    groupId = ""
    for n, s in enumerate(sims):
        id = s["simId"]
        for k in ("name", "cellids", "contacts", "webhooks"):
            if k in s["tags"]:
                requests.delete("{}/sims/{}/tags/{}".format(SORACOM_URL, id, k), headers=auth_hdr)

def make_group():
    global groupId, authKeyId

    if groupId:
        return

    rsp = requests.post("{}/operators/{}/auth_keys".format(SORACOM_URL, OperatorId), headers=auth_hdr).json()
    if "code" in rsp:
        print(rsp)
        return
    auth_keys = rsp

    newgrp = {
        "configuration": {
            "SoracomAir": {
                "binaryParserEnabled": True,
                "binaryParserFormat": "@soracom.button"
            },
            "SoracomBeam": {
                "udp://beam.soracom.io:23080": {
                    "name": "UDPToHTTP",
                    "enabled": True,
                    "destination": "https://drop-me-a-click.com/button.cgi",
                    "addSimIdHeader": True,
                    "customHeaders": {
                        "X-SORACOM-KEYS": {
                            "action": "append",
                            "headerKey": "X-SORACOM-KEYS",
                            "headerValue": "{},{}".format(auth_keys["authKeyId"], auth_keys["authKey"])
                        }
                    }
                }
            }
        },
        "tags": {
            "name": SORACOM_GRPNAME,
            "authKeyId" : auth_keys["authKeyId"]
        }
    }

    rsp = requests.post("{}/groups".format(SORACOM_URL), headers=auth_hdr, json=newgrp).json()
    if "code" in rsp:
        print(rsp)
        return
    groupId = rsp.get("groupId", "")
    authKeyId = rsp.get("tags", "{}").get("authKeyId", "")

HTTP_HOST = "https://" + os.getenv("HTTP_HOST", "")
CGI_FILE = HTTP_HOST + os.getenv("REQUEST_URI", "").split('?')[0]
if os.getenv("REQUEST_METHOD", "") == "GET":
    QUERY_STRING = os.getenv("QUERY_STRING", "")
else:
    QUERY_STRING = sys.stdin.read()

Fields = parse_qs(QUERY_STRING)
Action = Fields.get("Action", [""])[0]

COOKIE_SECS = 1800

try:
    Cookies = dict(v.split('=', 1) for v in os.getenv("HTTP_COOKIE").split('; '))
except:
    Cookies = {}

loggedin = False
if Action == "Login":
    Email = Fields.get("Email", [""])[0]
    Password = Fields.get("Password", [""])[0]
    if Email and Password:
        auth_body = {}
        auth_body["email"] = Email
        auth_body["password"] = Password

        rsp = requests.post("{}/auth".format(SORACOM_URL), json=auth_body).json()
        if "code" not in rsp:
            auth_body = rsp
            ApiKey = auth_body.get("apiKey")
            Token = auth_body.get("token")
            OperatorId = auth_body.get("operatorId")
            if ApiKey and Token and OperatorId:
                loggedin = True 
                print('Set-Cookie: ApiKey={}; Max-Age={};'.format(ApiKey, COOKIE_SECS))
                print('Set-Cookie: Token={}; Max-Age={};'.format(Token, COOKIE_SECS))
                print('Set-Cookie: OperatorId={}; Max-Age={};'.format(OperatorId, COOKIE_SECS))

elif Action == "Logout":
    print('Set-Cookie: ApiKey=; Max-Age=0;')
    print('Set-Cookie: Token=; Max-Age=0;')
    print('Set-Cookie: OperatorId=; Max-Age=0;')

else:
    ApiKey = Cookies.get("ApiKey", "")
    Token = Cookies.get("Token", "")
    OperatorId = Cookies.get("OperatorId", "")
    if ApiKey and Token and OperatorId:
        loggedin = True 

print('Content-Type: text/html\n')
insert_html_header()

if not Action or Action == "Login":
    Action = "Summary"

done = False
while not done:
    done = True

    if not loggedin:
        insert_html_login()
        break

    auth_hdr = {}
    auth_hdr["X-Soracom-API-Key"] = ApiKey
    auth_hdr["X-Soracom-Token"] = Token

    groupId = ""
    authKeyId = ""

    rsp = requests.get("{}/sims".format(SORACOM_URL), headers=auth_hdr).json()
    if "code" in rsp:
        print(rsp)
        break
    sims = rsp

    rsp = requests.get("{}/groups".format(SORACOM_URL), headers=auth_hdr).json()
    if "code" in rsp:
        print(rsp)
        break
    groups = rsp

    for g in groups:
        if g["tags"]["name"] == SORACOM_GRPNAME:
            groupId = g["groupId"]
            authKeyId = g["tags"].get("authKeyId", "")
            break

    if Action == "Summary":
        cleanup = True
        print('<h2>Buttons</h2><hr>')
        print('<form method="POST">')
        for n, s in enumerate(sims):
            if s["groupId"] and s["groupId"] == groupId:
                checked = "checked"
                cleanup = False
            else:
                checked = ""
            id = s["simId"]
            button = s["tags"].get("name", "")
            cellids = s["tags"].get("cellids", "")
            contacts = s["tags"].get("contacts", "")
            webhooks = s["tags"].get("webhooks", "")
            print('''
            <input type="hidden" name="sim-{n}" value={id}>
            <table>
            <tr>
            <td valign="middle">SIM: {id}</td>
            <td valign="middle"><table>
            <tr><td>Status</td><td><label><input type="checkbox" name="enable-{n}" {checked}><span class="checkable">Enabled for Drop-Me-A-Click</span></label></td></tr>
            <tr><td>Button Name</td><td><input type="text" name="name-{n}" value="{button}" size=60></td></tr>
            <tr><td>CellId Mapping</td><td><textarea name="cellids-{n}" placeholder="Format = tower#:name ... For example: 17924112:SCHOOL 20334097:WORK">{cellids}</textarea></td></tr>
            <tr><td>Email/SMS Contacts</td><td><textarea name="contacts-{n}" placeholder="Format = [click-type:]address[,address] ... For example: user@mail.com DOUBLE:6105551212@txt.sms.net,myid@cloud.io">{contacts}</textarea></td></tr>
            <tr><td>Webhooks</td><td><textarea name="webhooks-{n}" placeholder="Format = [click-type:]https://...">{webhooks}</textarea></td></tr>
            </table></td>
            </tr>
            </table>
            <hr>
            '''.format(n=n, checked=checked, button=button, id=id, contacts=contacts, cellids=cellids, webhooks=webhooks))

        if cleanup:
            delete_group()
        print('<input type="submit" name="Action" value="Update"> <a class="button warning" href="{}?Action=Logout">Logout</a></form>'.format(CGI_FILE))

    elif Action == "Update":
        cleanup = True
        n = 0
        while True:
            id = Fields.get("sim-{}".format(n), [""])[0]
            if not id:
                break

            rsp = requests.get("{}/sims/{}".format(SORACOM_URL, id), headers=auth_hdr).json()
            if "code" in rsp:
                print(rsp)
                cleanup = False
                break
            s = rsp

            enable = Fields.get("enable-{}".format(n), [""])[0]

            if enable:
                cleanup = False
                make_group()
                if s["groupId"] != groupId:
                    rsp = requests.post("{}/sims/{}/set_group".format(SORACOM_URL, id), headers=auth_hdr, json={"groupId":groupId}).json()
                    if "code" in rsp:
                        print(rsp)
                    s["groupId"] = groupId
            else:
                if s["groupId"]:
                    rsp = requests.post("{}/sims/{}/unset_group".format(SORACOM_URL, id), headers=auth_hdr).json()
                    if "code" in rsp:
                        print(rsp)
                    s["groupId"] = ""

            tags = []

            for k in ("name", "cellids", "contacts", "webhooks"):
                if s["groupId"]:
                    v = Fields.get("{}-{}".format(k, n), [""])[0]
                else:
                    v = ""

                if v:
                    if v != s["tags"].get(k, ""):
                        tags.append({"tagName" : k, "tagValue" : v})
                else:
                    if k in s["tags"]:
                        requests.delete("{}/sims/{}/tags/{}".format(SORACOM_URL, id, k), headers=auth_hdr)

            if tags:
                    rsp = requests.put("{}/sims/{}/tags".format(SORACOM_URL, id), headers=auth_hdr, json=tags).json()
                    if "code" in rsp:
                        print(rsp)

            n += 1

        if cleanup:
            delete_group()
        print('<p>Complete!</p>')
        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

    else:
        print('<p>Input not valid</p>')
        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

insert_html_footer()

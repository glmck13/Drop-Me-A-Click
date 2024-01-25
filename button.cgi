#!/usr/bin/env python3

import sys, os, json

SORACOM_SIM = os.getenv("HTTP_X_SORACOM_SIM_ID")
SORACOM_KEYS = os.getenv("HTTP_X_SORACOM_KEYS")

if not SORACOM_SIM or not SORACOM_KEYS:
    exit()

import requests
from urllib.parse import parse_qs
from datetime import datetime, timezone
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote
from datetime import datetime
from getenv import *

import urllib3
urllib3.disable_warnings()

print("Content-Type: text/plain\n")

SORACOM_KEYS = SORACOM_KEYS.split(',')
auth_body = {}
auth_body["authKeyId"] = SORACOM_KEYS[0]
auth_body["authKey"] = SORACOM_KEYS[1]

rsp = requests.post("{}/auth".format(SORACOM_URL), json=auth_body).json()
if "code" in rsp:
    print(rsp, file=sys.stderr)
    exit()

auth_body = rsp
auth_hdr = {}
auth_hdr["X-Soracom-API-Key"] = auth_body.get("apiKey")
auth_hdr["X-Soracom-Token"] = auth_body.get("token")

event = json.loads(sys.stdin.read())

rsp = requests.get("{}/sims/{}".format(SORACOM_URL, SORACOM_SIM), headers=auth_hdr).json()
if "code" in rsp:
    print(rsp, file=sys.stderr)
    exit()
sim = rsp

rsp = requests.get("{}/sims/{}/events/sessions?limit=1".format(SORACOM_URL, SORACOM_SIM), headers=auth_hdr).json()
if "code" in rsp:
    print(rsp, file=sys.stderr)
    exit()
last_session = rsp[0]

tags = sim["tags"]
name = tags.get("name", "Unknown")
cellids = tags.get("cellids", "").replace(',', ' ').split()
contacts = tags.get("contacts", "").replace(',', ' ').split()
webhooks = tags.get("webhooks", "").replace(',', ' ').split()
tower = last_session["cell"]

ClickType = event["detect_type"].upper()
if "LONG" in ClickType:
    ClickType = "LONG"
else:
    ClickType = ClickType.split()[0]
Who = name
When = datetime.fromtimestamp(last_session["time"]/1000).strftime('%Y-%m-%d %H:%M:%S')
CellId = tower.get("eci", tower.get("cid", ""))
LacId = tower.get("tac", tower.get("lac", ""))

cid = str(CellId)
for item in cellids:
    item += ':'
    item = item.split(':')
    if cid == item[0]:
        Where = item[1]
        break
else:
    try:
        rsp = requests.post(UNWIRED_URL, json={"token":UNWIRED_TOKEN,"radio":tower.get("radioType","").lower(),"mcc":tower.get("mcc",""),"mnc":tower.get("mnc",""),"cells":[{"cid":CellId, "lac":LacId}],"address":1})
        Where = rsp.json().get("address")
    except:
        Where = "Unknown"

Notification = "{} click from {} on {}: {}".format(ClickType, Who, datetime.strptime(When, "%Y-%m-%d %H:%M:%S").strftime("%A, %B %-d at %-I:%M %p"), Where)
Subject = "{ClickType} click from {Who}".format(ClickType=ClickType, Who=Who)
Body = "CellId {CellId}: {Where}".format(CellId=CellId, Where=Where)
Message = Subject + ': ' + Body

print(event, Who, When, Where, ClickType, CellId, Subject, Body, Message, Notification, sep='\n', file=sys.stderr)

recipients = []
for item in contacts:
    item = item.split(':', 1)
    if len(item) > 1 and item.pop(0).upper() != ClickType:
        continue
    elif not item[0]:
        continue
    else:
        recipients.append(item[0])

if recipients:
    eml = EmailMessage()
    eml['Subject'] = Subject
    eml['From'] = GMAIL_FROM
    eml['To'] = ', '.join(recipients)
    eml.set_content(Body)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(GMAIL_SMTP, GMAIL_PORT, context=context) as server:
            server.login(GMAIL_FROM, GMAIL_KEY)
            server.send_message(eml)
    except:
        pass

for item in webhooks:
    item = item.split(':', 1)
    if item[0].upper() in ("HTTP", "HTTPS"):
        url = ':'.join(item)
    elif len(item) > 1 and item.pop(0).upper() != ClickType:
        continue
    elif not item[0]:
        continue
    else:
        url = item[0]

    try:
        url = url.format(ClickType=ClickType, CellId=CellId, Who=Who, When=When, Where=quote(Where), Notification=quote(Notification))
        rsp = requests.post(url, verify=False)
        print(rsp.text, file=sys.stderr)
    except:
        pass

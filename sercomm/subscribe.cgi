#!/usr/bin/env python3

import sys
import os
import json
import base64
from urllib.parse import parse_qs
import botocore
import boto3
import subprocess
import re
import smtplib
import ssl
from email.message import EmailMessage
from pprint import pprint
from getenv import *

def insert_html_header():
    with open("header.html") as f:
        print(f.read())

def insert_html_footer():
    with open("footer.html") as f:
        print(f.read())

def insert_html_claim():
    with open("claim.html") as f:
        print(f.read())

HTTP_HOST = "https://" + os.getenv("HTTP_HOST", "")
CGI_FILE = HTTP_HOST + os.getenv("REQUEST_URI", "").split('?')[0]

if os.getenv("REQUEST_METHOD", "") == "GET":
    QUERY_STRING = os.getenv("QUERY_STRING", "")
else:
    QUERY_STRING = sys.stdin.read()
Fields = parse_qs(QUERY_STRING)
Username = Fields.get("Username", [""])[0]
DeviceId = Fields.get("DeviceId", [""])[0]
Button = Fields.get("Button", [""])[0]
Action = Fields.get("Action", ["Start"])[0]
Error = ""
INCLUDE_HEADER = "header.html"
INCLUDE_FOOTER = "footer.html"
PROJECT_LAMBDA = "arn:aws:lambda:us-west-2:020864268877:function:drop-me-a-click"
HTPASSWD = ".htpasswd"
GMAIL_FROM = "dropmeaclick@gmail.com"
WELCOME_SUBJECT = "Welcome to Drop-Me-A-Click!"
WELCOME_BODY = "Congratulations!  You have successfully subscribed to Drop-Me-A-Click. Your password has been set to: {Password}"

boto_iot1click_devices = boto3.client('iot1click-devices')
boto_iot1click_projects = boto3.client('iot1click-projects')

print('Content-Type: text/html\n')
insert_html_header()

done = False
while not done:
    done = True

    if Action == "Start":

        insert_html_claim()

    elif Action == "Initiate":

        for var, expr in [("Username", '\S+@\S+'), ("DeviceId", '[\w]+'), ("Button", '[\w-]+')]:
            my = eval(var)
            if not re.fullmatch(expr, my):
                Error = "{} invalid: {}".format(var, my)
                break

        if Error:
            break
        try:
            rsp = boto_iot1click_devices.initiate_device_claim(DeviceId=DeviceId)
            print('''
                <p>Press your button once, wait until the LED turns solid green, then click Finalize.</p>
                <form method="POST">
                <input type="hidden" name="Username" value="{Username}" />
                <input type="hidden" name="DeviceId" value="{DeviceId}" />
                <input type="hidden" name="Button" value="{Button}" />
                <input type="submit" name="Action" value="Finalize" />
                </div>
            '''.format(Username=Username, DeviceId=DeviceId, Button=Button))
        except botocore.exceptions.ClientError as error:
            Error = error.response["Error"]["Message"]
            break

    elif Action == "Finalize":

        try:
            rsp = boto_iot1click_devices.finalize_device_claim(DeviceId=DeviceId)
            rsp = boto_iot1click_devices.update_device_state(DeviceId=DeviceId, Enabled=True)
        except botocore.exceptions.ClientError as error:
            Error = error.response["Error"]["Message"]
            break

        Attributes = {"Places" : "{}", "Contacts" : json.dumps({"Emails":[], "WebHooks":[]})}
        ProjectName = base64.urlsafe_b64encode(Username.encode()).decode().replace('=', '')
        Template = {
            "defaultAttributes" : Attributes,
            "deviceTemplates" : {"ClickEvent":{"deviceType":"button","callbackOverrides":{"onClickCallback":PROJECT_LAMBDA}}}
        }

        try:
            rsp = boto_iot1click_projects.create_project(projectName=ProjectName, description=Username, placementTemplate=Template)
            rsp = boto_iot1click_projects.create_placement(placementName=Button, projectName=ProjectName)
            rsp = boto_iot1click_projects.associate_device_with_placement(placementName=Button, projectName=ProjectName, deviceId=DeviceId, deviceTemplateName="ClickEvent")
        except botocore.exceptions.ClientError as error:
            Error = error.response["Error"]["Message"]
            break

        rsp = subprocess.run(["pwgen", "-Bcny", "16", "1"], capture_output=True)
        if rsp.returncode != 0:
            Error = "pwgen failed!"
            break
        Password = rsp.stdout.decode().strip()
        rsp = subprocess.run(["htpasswd", "-b", HTPASSWD, Username, Password], capture_output=True)
        if rsp.returncode != 0:
            Error = "htpasswd failed!"
            break

        eml = EmailMessage()
        eml['Subject'] = WELCOME_SUBJECT
        eml['From'] = GMAIL_FROM
        eml['To'] = Username
        eml.set_content(WELCOME_BODY.format(Password=Password))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(GMAIL_FROM, GMAIL_KEY)
            server.send_message(eml, from_addr=GMAIL_FROM, to_addrs=Username)

        print("<p>Success! Please check your email for a login password. Welcome to Drop-Me-A-Click!</p>")
        print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))

if Error:
        print('<p>{Error}</p>'.format(Error=Error))
        print('<a class="button" href="{}">Retry</a>'.format(CGI_FILE))

insert_html_footer()

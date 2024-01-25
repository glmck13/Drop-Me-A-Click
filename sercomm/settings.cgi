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

def insert_html_login():
    with open("login.html") as f:
        print(f.read())

HTTP_HOST = "https://" + os.getenv("HTTP_HOST", "")
CGI_FILE = HTTP_HOST + os.getenv("REQUEST_URI", "").split('?')[0]
if os.getenv("REQUEST_METHOD", "") == "GET":
    QUERY_STRING = os.getenv("QUERY_STRING", "")
else:
    QUERY_STRING = sys.stdin.read()
Fields = parse_qs(QUERY_STRING)
Action = Fields.get("Action", [""])[0]
Place = Fields.get("Place", [""])[0]
Button = Fields.get("Button", [""])[0]
DeviceId = Fields.get("DeviceId", [""])[0]
Account = Fields.get("Account", [""])[0]
Password = Fields.get("Password", [""])[0]
NewPassword = Fields.get("NewPassword", [""])[0]
RepeatPassword = Fields.get("RepeatPassword", [""])[0]
Username = ""
Message = ""
PROJECT_LAMBDA = "arn:aws:lambda:us-west-2:020864268877:function:drop-me-a-click"
HTPASSWD = ".htpasswd"
MAX_CELLIDS = 6
MAX_EMAILS = 8
MAX_WEBHOOKS = 3
COOKIE_SECS = 900
GMAIL_FROM = "dropmeaclick@gmail.com"
WELCOME_SUBJECT = "Password reset for Drop-Me-A-Click"
WELCOME_BODY = "Your password has been set to: {Password}"

try:
    Cookies = dict(v.split('=', 1) for v in os.getenv("HTTP_COOKIE").split('; '))
except:
    Cookies = {}

boto_iot1click_devices = boto3.client('iot1click-devices')
boto_iot1click_projects = boto3.client('iot1click-projects')

loggedin = False
ProjectName = ""
if Action == "Login":
    Username = Fields.get("Username", [""])[0]
    Password = Fields.get("Password", [""])[0]
    if Username and Password:
        rsp = subprocess.run(["htpasswd", "-bv", HTPASSWD, Username, Password], capture_output=True)
        if rsp.returncode == 0:
            loggedin = True 
            ProjectName = base64.urlsafe_b64encode(Username.encode()).decode().replace('=', '')
            print('Set-Cookie: ProjectName={}; Max-Age={};'.format(ProjectName, COOKIE_SECS))

elif Action == "Reset Password":
    Username = Fields.get("Username", [""])[0]
    if Username:
        rsp = subprocess.run(["grep", "^{}:".format(Username), HTPASSWD], capture_output=True)
        if rsp.returncode == 0:
            ProjectName = base64.urlsafe_b64encode(Username.encode()).decode().replace('=', '')

elif Action == "Logout":
    print('Set-Cookie: ProjectName=; Max-Age=0;')

else:
    ProjectName = Cookies.get("ProjectName", "")
    if ProjectName:
        loggedin = True 

print('Content-Type: text/html\n')
insert_html_header()

if not Action or Action == "Login":
    Action = "Summary"

done = False
while not done:
    done = True

    if not loggedin and Action != "Reset Password":
        insert_html_login()
        break

    try:
        rsp = boto_iot1click_projects.describe_project(projectName=ProjectName)
        rsp = rsp['project']
        Username = rsp['description']
        places = json.loads(rsp['placementTemplate']['defaultAttributes']['Places'])
    except botocore.exceptions.ClientError as error:
        Message = error.response["Error"]["Message"]
        print('<p>{Message}</p>'.format(Message=Message))
        print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))
        break

    if Action == "Summary":

        try:
            rsp = boto_iot1click_projects.list_placements(projectName=ProjectName)
            rsp = rsp['placements']
            placements = rsp
        except botocore.exceptions.ClientError as error:
            Message = error.response["Error"]["Message"]
            print('<p>{Message}</p>'.format(Message=Message))
            print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))
            break

        buttons = []
        for button in placements:
            my = button['placementName']
            try:
                rsp = boto_iot1click_projects.describe_placement(projectName=ProjectName, placementName=my)
                rsp = rsp['placement']
                contacts = json.loads(rsp['attributes'].get('Contacts', "{}"))
                emails = contacts.get('Emails', [])
                webhooks = contacts.get('WebHooks', [])
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]
                break

            try:
                rsp = boto_iot1click_projects.get_devices_in_placement(projectName=ProjectName, placementName=my)
                rsp = rsp['devices']
                deviceId = rsp['ClickEvent']
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]
                break

            try:
                rsp = boto_iot1click_devices.describe_device(DeviceId=deviceId)
                rsp = rsp['DeviceDescription']
                battery = rsp['RemainingLife']
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]
                break

            buttons.append('{}: {} ({}%)'.format(my, deviceId, battery))

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))
            print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))
            break

        print('<h2>Account</h2>')
        print('<table>')
        print('<tr>')
        print('<td>')
        print('<a href="{}?Action=Update&Account={}"><i class="icon-pencil"></i></a>'.format(CGI_FILE, Username))
        print('<a href="{}?Action=Delete&Account={}" onclick="return confirm(\'Are you sure you want to delete your account?\');"><i class="icon-trash"></i></a>'.format(CGI_FILE, Username))
        print('</td>')
        print('<td>&emsp;{}</td>'.format(Username))
        print('</tr>')
        print('</table>')
        print('<a class="button warning" href="{}?Action=Logout">Logout</a>'.format(CGI_FILE))

        print('<hr>')

        print('<h2>Places</h2>')
        print('<form>')
        print('<table>')
        for k, v in places.items():
            print('<tr>')
            print('<td>')
            print('<a href="{}?Action=Describe&Place={}"><i class="icon-pencil"></i></a>'.format(CGI_FILE, k))
            print('<a href="{}?Action=Delete&Place={}" onclick="return confirm(\'Are you sure you want to delete {}?\');"><i class="icon-trash"></i></a>'.format(CGI_FILE, k, k))
            print('</td>')
            print('<td>{}</td>'.format(k))
            print('</tr>')
        print('<tr>')
        print('<td><input class="success" type="submit" name="Action" value="Add" /></td>')
        print('<td><input type="text" name="Place" placeholder="Enter place name" /></td>')
        print('</tr>')
        print('</table>')
        print('</form>')

        print('<hr>')

        print('<h2>Buttons</h2>')
        print('<form>')
        print('<table>')
        for k in buttons:
            v = k.split(':')[0]
            print('<tr>')
            print('<td>')
            print('<a href="{}?Action=Describe&Button={}"><i class="icon-pencil"></i></a>'.format(CGI_FILE, v))
            print('<a href="{}?Action=Delete&Button={}" onclick="return confirm(\'Are you sure you want to delete {}?\');"><i class="icon-trash"></i></a>'.format(CGI_FILE, v, v))
            print('</td>')
            print('<td>{}</td>'.format(k))
            print('</tr>')
        print('<tr>')
        print('<td><input class="success" type="submit" name="Action" value="Add" /></td>')
        print('<td><input type="text" name="Button" placeholder="Enter button name" /></td>')
        print('</tr>')
        print('</table>')
        print('</form>')

    elif Action == "Update" and Account:

        print('''
            <h2>{} password</h2>
            <div class="half">
            <form method="POST">
            <input type="password" name="Password" placeholder="Enter current password" />
            <input type="password" name="NewPassword" placeholder="Enter new password" />
            <input type="password" name="RepeatPassword" placeholder="Repeat new password" />
            <input type="submit" name="Action" value="Change" />
            </form>
            </div>
        '''.format(Account))

    elif Action == "Change" and Password and NewPassword and RepeatPassword:

        block = True
        while block:
            block = False

            if NewPassword != RepeatPassword:
                Message = "New passwords do not match"
                break

            rsp = subprocess.run(["htpasswd", "-bv", HTPASSWD, Username, Password], capture_output=True)
            if rsp.returncode != 0:
                Message = "Password incorrect"
                break

            rsp = subprocess.run(["htpasswd", "-b", HTPASSWD, Username, NewPassword], capture_output=True)
            if rsp.returncode != 0:
                Message = "htpasswd failed!"
                break

            Message = "Complete!"

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}?Action=Logout">Back</a>'.format(CGI_FILE))

    elif Action == "Reset Password":

        block = True
        while block:
            block = False

            rsp = subprocess.run(["pwgen", "-Bcny", "16", "1"], capture_output=True)
            if rsp.returncode != 0:
                Message = "pwgen failed!"
                break

            Password = rsp.stdout.decode().strip()
            rsp = subprocess.run(["htpasswd", "-b", HTPASSWD, Username, Password], capture_output=True)
            if rsp.returncode != 0:
                Message = "htpasswd failed!"
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

            Message = "Complete! Please check your email for a login password."

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}?Action=Logout">Back</a>'.format(CGI_FILE))

    elif Action == "Delete" and Account:

        try:
            rsp = boto_iot1click_projects.delete_project(projectName=ProjectName)
            rsp = subprocess.run(["htpasswd", "-D", HTPASSWD, Username], capture_output=True)
            Message = "Complete!"
        except botocore.exceptions.ClientError as error:
            Message = error.response["Error"]["Message"]

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}?Action=Logout">Home</a>'.format(CGI_FILE))

    elif Action == "Add" and Place:

        my = Place
        if not re.fullmatch('[\w-]+', my):
            Message = "Place names may only contain letters, numbers, dashes, or underscores: {}".format(my)
            my = None

        else:
            places[my] = []
            template = {"defaultAttributes": {"Places": json.dumps(places)}}

            try:
                rsp = boto_iot1click_projects.update_project(projectName=ProjectName, placementTemplate=template)
                Message = "Complete!"

            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]
                my = None

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))

        if my:
            print('<a class="button" href="{}?Action=Describe&Place={}">Back</a>'.format(CGI_FILE, my))
        else:
            print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

    elif Action == "Delete" and Place:

        my = Place

        if my not in places:
            Message = "{} not found".format(my)

        else:
            places.pop(my)
            template = {"defaultAttributes": {"Places": json.dumps(places)}}

            try:
                rsp = boto_iot1click_projects.update_project(projectName=ProjectName, placementTemplate=template)
                Message = "Complete!"

            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

    elif Action == "Describe" and Place:

        my = Place
        if my not in places:
            Message = "{} not found".format(my)
            print('<p>{Message}</p>'.format(Message=Message))
            print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))
            break

        cellids = places[my]

        print('<form method="POST">')
        print('<h2>{} cell tower ids</h2>'.format(my))
        print('<fieldset class="flex six">')
        for n in range(MAX_CELLIDS):
            if n < len(cellids):
                v = str(cellids[n])
            else:
                v = ""
            print('<input type="text" name="CellIds" value="{}" />'.format(v))
        print('</fieldset>')
        print('<input type="hidden" name="Place" value="{}" />'.format(my))
        print('<input type="submit" name="Action" value="Update" />')
        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))
        print('</form">')

    elif Action == "Update" and Place:

        my = Place
        if my not in places:
            Message = "Place not found: {}".format(my)
            print('<p>{Message}</p>'.format(Message=Message))
            print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))
            break

        CellIds = Fields.get("CellIds", [])
        cellids = []
        while CellIds:
            c = CellIds.pop(0)
            if not re.fullmatch('\d+', c):
                Message = "CellId should be a positive number: {}".format(c)
                break
            cellids.append(int(c))

        cellids = list(set(cellids))
        cellids.sort()

        if not Message:
            places[my] = cellids
            template = {"defaultAttributes": {"Places": json.dumps(places)}}

            try:
                rsp = boto_iot1click_projects.update_project(projectName=ProjectName, placementTemplate=template)
                Message = "Complete!"
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]

        if Message:
                print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}?Action=Describe&Place={}">Back</a>'.format(CGI_FILE, my))

    elif Action == "Add" and Button:

        my = Button
        if not re.fullmatch('[\w-]+', my):
            Message = "Button names may only contain letters, numbers, dashes, or underscores: {}".format(my)
            my = None

        if Message:
                print('<p>{Message}</p>'.format(Message=Message))
                print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))
                break

        print('''
            <div class="half">
            <form method="POST">
            <input type="text" name="DeviceId" placeholder="Enter device serial # (DSN)" />
            <input type="hidden" name="Button" value="{Button}" />
            <input type="submit" name="Action" value="Initiate" />
            </form>
            </div>
        '''.format(Button=my))

    elif Action == "Initiate":

        my = Button
        for var, expr in [("DeviceId", '\w+'), ("Button", '[\w-]+')]:
            my = eval(var)
            if not re.fullmatch(expr, my):
                Message = "{} not valid: {}".format(var, my)
                break

        if not Message:
            try:
                rsp = boto_iot1click_devices.initiate_device_claim(DeviceId=DeviceId)
                print('''
                    <p>Press your button once, wait until the LED turns solid green, then click Finalize.</p>
                    <form method="POST">
                    <input type="hidden" name="DeviceId" value="{DeviceId}" />
                    <input type="hidden" name="Button" value="{Button}" />
                    <input type="submit" name="Action" value="Finalize" />
                    </form>
                '''.format(DeviceId=DeviceId, Button=my))
    
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]

        if Message:
            print('<p>{Message}</p>'.format(Message=Message))
            print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

    elif Action == "Finalize":

        my = Button
        try:
            rsp = boto_iot1click_devices.finalize_device_claim(DeviceId=DeviceId)
            rsp = boto_iot1click_devices.update_device_state(DeviceId=DeviceId, Enabled=True)
        except botocore.exceptions.ClientError as error:
            Message = error.response["Error"]["Message"]
            my = None

        if not Message:
            Attributes = {"Places" : "{}", "Contacts" : json.dumps({"Emails":[], "WebHooks":[]})}
            ProjectName = base64.urlsafe_b64encode(Username.encode()).decode().replace('=', '')
            Template = {
                "defaultAttributes" : Attributes,
                "deviceTemplates" : {"ClickEvent":{"deviceType":"button","callbackOverrides":{"onClickCallback":PROJECT_LAMBDA}}}
            }

            try:
                rsp = boto_iot1click_projects.disassociate_device_from_placement(projectName=ProjectName, placementName=my, deviceTemplateName="ClickEvent")
            except:
                rsp = boto_iot1click_projects.create_placement(placementName=my, projectName=ProjectName)

            try:
                rsp = boto_iot1click_projects.associate_device_with_placement(placementName=my, projectName=ProjectName, deviceId=DeviceId, deviceTemplateName="ClickEvent")
                Message = "Complete!"
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]
                my = None

        if Message:
                print('<p>{Message}</p>'.format(Message=Message))

        if my:
            print('<a class="button" href="{}?Action=Describe&Button={}">Back</a>'.format(CGI_FILE, my))
        else:
            print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

    elif Action == "Describe" and Button:

        my = Button
        try:
            rsp = boto_iot1click_projects.describe_placement(projectName=ProjectName, placementName=my)
            rsp = rsp['placement']
            contacts = json.loads(rsp['attributes'].get('Contacts', "{}"))
            emails = contacts.get('Emails', [])
            webhooks = contacts.get('WebHooks', [])
        except botocore.exceptions.ClientError as error:
            Message = error.response["Error"]["Message"]
            print('<p>{Message}</p>'.format(Message=Message))
            print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))
            break

        print('<form method="POST">')

        print('<h2>{} email addresses</h2>'.format(my))

        print('<fieldset class="flex four">')
        for n in range(MAX_EMAILS):
            if n < len(emails):
                v = emails[n]
            else:
                v = ""
            print('<input type="email" name="Emails" value="{}" />'.format(v))
        print('</fieldset>')

        print('<h2>{} webhooks</h2>'.format(my))

        print('<fieldset>')
        for n in range(MAX_WEBHOOKS):
            if n < len(webhooks):
                v = webhooks[n]
            else:
                v = ""
            print('<textarea name="WebHooks">{}</textarea>'.format(v))
        print('</fieldset>')

        print('<h2>{} button to copy</h2>'.format(my))
        print('<input type="text" name="ButtonClone" placeholder="Enter button name" />')
        print('<input type="hidden" name="Button" value="{Button}" />'.format(Button=my))
        print('<input type="submit" name="Action" value="Update" />')
        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))
        print('</form">')

    elif Action == "Update" and Button:

        my = Button
        try:
            rsp = boto_iot1click_projects.describe_placement(projectName=ProjectName, placementName=my)
        except botocore.exceptions.ClientError as error:
            Message = error.response["Error"]["Message"]

        ButtonClone = Fields.get("ButtonClone", [""])[0]
        Emails = Fields.get("Emails", [])
        WebHooks = Fields.get("WebHooks", [])

        Emails = list(set(Emails))
        Emails.sort()

        if ButtonClone:
            yours = ButtonClone
            try:
                rsp = boto_iot1click_projects.describe_placement(projectName=ProjectName, placementName=yours)
                rsp = rsp['placement']
                contacts = json.loads(rsp['attributes'].get('Contacts', "{}"))
                Emails = contacts.get('Emails', [])
                WebHooks = contacts.get('WebHooks', [])
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]

        if not Message:
            attributes = {"Contacts": json.dumps({"Emails" : Emails, "WebHooks" : WebHooks})}

            try:
                rsp = boto_iot1click_projects.update_placement(projectName=ProjectName, placementName=my, attributes=attributes)
                Message = "Complete!"
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]

        if Message:
                print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}?Action=Describe&Button={}">Back</a>'.format(CGI_FILE, my))

    elif Action == "Delete" and Button:

        my = Button
        try:
            rsp = boto_iot1click_projects.describe_placement(projectName=ProjectName, placementName=my)
        except botocore.exceptions.ClientError as error:
            Message = error.response["Error"]["Message"]

        if not Message:

            try:
                rsp = boto_iot1click_projects.disassociate_device_from_placement(projectName=ProjectName, placementName=my, deviceTemplateName="ClickEvent")
                rsp = boto_iot1click_projects.delete_placement(projectName=ProjectName, placementName=my)
                Message = "Complete!"
            except botocore.exceptions.ClientError as error:
                Message = error.response["Error"]["Message"]

        if Message:
                print('<p>{Message}</p>'.format(Message=Message))

        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

    else:
        print('<p>Input not valid</p>')
        print('<a class="button" href="{}">Back</a>'.format(CGI_FILE))

insert_html_footer()

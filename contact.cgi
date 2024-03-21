#!/usr/bin/env python3

import sys
import os
import json
import base64
from urllib.parse import parse_qs
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

HTTP_HOST = "https://" + os.getenv("HTTP_HOST", "")
CGI_FILE = HTTP_HOST + os.getenv("REQUEST_URI", "").split('?')[0]
QUERY_STRING = os.getenv("QUERY_STRING", "")
if not QUERY_STRING and os.getenv("REQUEST_METHOD", "") != "GET":
    QUERY_STRING = sys.stdin.read().strip()

Fields = parse_qs(QUERY_STRING)
Contact = Fields.get("Contact", [""])[0]
Email = Fields.get("Email", [""])[0]
Note = Fields.get("Note", [""])[0]
Action = Fields.get("Action", ["Start"])[0]
Message = ""

print('Content-Type: text/html\n')
insert_html_header()

done = False
while not done:
    done = True

    if Action == "Send":

        for var, expr in [("Email", '\S+@\S+'), ("Contact", '.*\S.*')]:
            my = eval(var)
            if not re.fullmatch(expr, my):
                Message = "{} invalid: {}".format(var, my)
                break

        if Message:
            break

        eml = EmailMessage()
        eml['Subject'] = "User contact from Drop Me A Click"
        eml['From'] = GMAIL_FROM
        eml['To'] = GMAIL_TO
        eml.set_content('From: {}\nEmail: {}\n\n'.format(Contact, Email) + Note)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(GMAIL_SMTP, GMAIL_PORT, context=context) as server:
            server.login(GMAIL_FROM, GMAIL_KEY)
            server.send_message(eml, from_addr=GMAIL_FROM, to_addrs=GMAIL_TO)

        Message = "I'll review your message and get back to you shortly.  Thanks for using Drop-Me-A-Click!"

print("<p>{}</p>".format(Message))
print('<a class="button" href="{}">Home</a>'.format(HTTP_HOST))

insert_html_footer()

#!/usr/bin/env python3

import sys, os, json
import requests
from urllib.parse import parse_qs
from getenv import *

import sqlite3
from contextlib import closing
from datetime import datetime

# Disable IPv6 for Soracom API
requests.packages.urllib3.util.connection.HAS_IPV6 = False

def insert_html_header():
    with open("map_header.html") as f:
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
    Action = "Map"

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
    towers = {}
    qlist = set()

    for s in sims:
        sid = s["simId"]
        button = s["tags"].get("name", "")
        link = ""
        while True:
            api = requests.get("{}/sims/{}/events/sessions?{}".format(SORACOM_URL, sid, link), headers=auth_hdr)
            hdr = api.headers
            rsp = api.json()
            if "code" in rsp:
                print(rsp)
                break
            sessions = rsp
            for e in sessions:
                if e["event"] == "Created":
                    cell = e["cell"]
                    eci = str(cell["eci"])
                    tac = str(cell["tac"])
                    mcc = str(cell["mcc"])
                    mnc = str(cell["mnc"])
                    radio = str(cell["radioType"])
                    tstamp = str(e["time"])
                    key = "{}|{}|{}|{}".format(mcc, mnc, tac, eci)
                    if key in towers:
                        towers[key]["events"].append({"sid" : sid, "button" : button, "tstamp" : tstamp})
                    else:
                        towers[key] = {"s_radio" : radio, "events": [{"sid" : sid, "button" : button, "tstamp" : tstamp}]}
                    qlist.add(eci)

            link = hdr.get("x-soracom-next-key", "")
            if not link:
                break
            link = "last_evaluated_key=" + link

    geo = {}
    with closing(sqlite3.connect("towers.db")) as connection:
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("select * from towers where cell in (select value from json_each(?))",
                (json.dumps([q for q in qlist]),)).fetchall()
            for r in rows:
                geo["{}|{}|{}|{}".format(r[1], r[2], r[3], r[4])] = {"lat" : r[7], "lon" : r[6], "m_radio" : r[0]}
    #print(json.dumps(geo, indent=4))

    pin = {}
    for k, v in towers.items():
        if k in geo:
            pin = geo[k]
            towers[k].update(pin)
        else:
            c = k.split('|')
            rsp = requests.post(UNWIRED_URL, json={"token":UNWIRED_TOKEN,"radio":v["s_radio"].lower(),"mcc":c[0],"mnc":c[1],"cells":[{"cid":c[3], "lac":c[2]}],"address":1}).json()
            lat = rsp.get("lat", "")
            lon = rsp.get("lon", "")
            if lat and lon:
                pin = {"lat" : lat, "lon" : lon, "m_radio" : "-"}
                towers[k].update(pin)

    #print(json.dumps(towers, indent=4))

    if not pin:
        break

    if Action == "Map":
        print('''
        <center>

        <div id="map" style="width: 1000px; height: 800px;"></div>
        <div id="csv"></div>

        <script>
            const map = L.map('map').setView([{lat}, {lon}], 6);
            const tiles = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                }}).addTo(map);
            var marker;
        '''.format(lat=pin["lat"], lon=pin["lon"])
        )

        for k, v in towers.items():
            if "lat" in v:
                e = v["events"][0]
                print('''
                marker = L.marker([{lat}, {lon}]).addTo(map);
                marker.bindPopup("{button}: {key}: {tstamp}");
                '''.format(lat=v["lat"], lon=v["lon"], button=e["button"], key=k, tstamp=datetime.fromtimestamp(int(e["tstamp"])/1000).strftime('%c'))
                )

        print('</script>')

        print('<script>')
        print("var csvContent='", end='')
        print('Button,Sim,MCC,MNC,TAC,CellId,S-Radio,M-Radio,Lat,Lon,Tstamp\\n', end='')
        for k, v in towers.items():
            lat = v.get("lat", "")
            lon = v.get("lon", "")
            m_radio = v.get("m_radio", "")
            s_radio = v.get("s_radio", "")
            for e in v["events"]:
                sid = e["sid"]
                button = e["button"]
                tstamp = e["tstamp"]
                print('{button},{sid},{key},{s_radio},{m_radio},{lat},{lon},{tstamp}\\n'.format(button=button, sid=sid, key=k.replace('|', ','), s_radio=s_radio, m_radio=m_radio, lat=lat, lon=lon, tstamp=tstamp), end='')
        print("';")

        print('''
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8,' });
        const objUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', objUrl);
        link.setAttribute('class', 'button');
        link.setAttribute('download', 'clicks.csv');
        link.textContent = 'Download CSV file';
        document.querySelector('#csv').append(link);
        ''')
        print('</script>')

        print('</center>')

insert_html_footer()

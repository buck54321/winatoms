#!/usr/bin/env python
import atexit
import hashlib
import html
import imghdr
import json
import os
from pathlib import Path
import time
from collections import deque

from decred.crypto.rando import newHash
from decred.util import helpers
from decred.util.encode import ByteArray
from decred.dcr.wire import msgtx
from flask import Flask, jsonify, render_template, request, abort

from tcp import ConnectionPool

MEDIA_ROOT = Path("./static")

ChallengeServerPort = 54345

MebiByte = 1024 * 1024

MaxChallengesPerRequest = 20

log = helpers.getLogger("WINATOMS")

app = Flask(__name__)

print("WARNING: Running with template auto-reload enabled. Disable this feature in production")
app.config['TEMPLATES_AUTO_RELOAD'] = True

users = {}
backlog = deque(maxlen=10)

pool = ConnectionPool("localhost", ChallengeServerPort)

def sendObj(conn, obj):
    send(conn, json.dumps(obj).encode("utf-8"))

def send(conn, msg):
    packet = ByteArray(len(msg), length=2) + msg
    conn.send(packet)

def recv(conn):
    lenB = conn.readN(2)
    return conn.readN(lenB.int())

def relay(conn, route, payload):
    sendObj(conn, dict(
        route=route,
        payload=payload,
    ))
    msgB = recv(conn)
    return json.loads(msgB.b)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/live-challenge-index')
def liveChallengeIndex():
    with pool.conn() as conn:
        resp = relay(conn, "liveChallengeList", {})

        return jsonify({
            "ok": "error" not in resp,
            "payload": resp,
        })

@app.route('/create')
def create():
    return render_template('create.html')

@app.route('/challenge/<chid>')
def challenge(chid):
    with pool.conn() as conn:
        resp = relay(conn, "challenge", dict(chid=chid))
        if "error" in resp:
            log.error(f"error retrieving challenge: {resp}")
            abort(404)

        return render_template('challenge.html', **resp)

@app.route('/how')
def how():
    return render_template('how.html')

@app.route('/api/contract', methods=['POST'])
def contract():
    d = request.form
    
    if "prompt" not in d or not isinstance(d["prompt"], str):
        return jsonify(apiError("prompt cannot be empty"))
    rawPrompt = d["prompt"].strip()
    if rawPrompt == "":
        return jsonify(apiError("prompt cannot be just whitespace"))
    if len(rawPrompt) > 1e4:
        return jsonify(apiError("prompt cannot be > 10,000 characters"))
    if "doubleHash" not in d or not isinstance(d["doubleHash"], str) or len(d["doubleHash"]) != 64:
        return jsonify(apiError("invalid answer hash format"))
    if "nonce" not in d or not isinstance(d["nonce"], str) or len(d["nonce"]) != 32:
        return jsonify(apiError("invalid nonce"))
    if "proof" not in d or not isinstance(d["proof"], str) or len(d["proof"]) != 64:
        return jsonify(apiError("invalid proof"))

    imgFile = None
    if "img" in request.files:
        img = request.files["img"]
        img.stream.seek(0, 2)
        size = img.stream.tell()
        img.stream.seek(0)
        
        print("--size", size)

        if size > MebiByte:
            return jsonify(apiError(f"img size, {size}, is greater than max allowed, {MebiByte} "))
        # If we allow files > 2.5 MB, hould not use read to get the data, should
        # call chunk in a loop.
        imgB = img.stream.read()
        imgType = imghdr.what(None, h=imgB)
        if imgType not in ("gif", "jpeg", "png"):
            return jsonify(apiError("not a supported image type"))

        h = hashlib.sha256()
        h.update(imgB)
        imgHash = ByteArray(h.digest()).hex()
        imgFile = f"{imgHash[:16]}.{imgType}"
        imgPath = str(MEDIA_ROOT / "img" / "uu" / imgFile)
        with open(imgPath, 'wb+') as f:
            f.write(imgB)

    with pool.conn() as conn:
        resp = relay(conn, "contract", dict(
            prompt=html.escape(rawPrompt),
            doubleHash=d["doubleHash"],
            nonce=d["nonce"],
            proof=d["proof"],
            imgPath=imgFile,
        ))

        return jsonify({
            "ok": "error" not in resp,
            "payload": resp,
        })

@app.route('/api/solve', methods=['POST'])
def solve():
    d = request.json
    if "proof" not in d or not isinstance(d["proof"], str) or len(d["proof"]) != 64:
        return jsonify(apiError("invalid proof"))
    if "addr" not in d or not isinstance(d["addr"], str) or d["addr"] == "":
        return jsonify(apiError("no address provided"))
    if "redemptionAddr" not in d or not isinstance(d["redemptionAddr"], str) or d["redemptionAddr"] == "":
        return jsonify(apiError("no redemption address provided"))
    
    with pool.conn() as conn:
        resp = relay(conn, "solve", d)

        return jsonify({
            "ok": "error" not in resp,
            "payload": resp,
        })

@app.route('/api/relay', methods=['POST'])
def relayTx():
    d = request.json
    # broadcast sends the hex string blindly, so we'll need to decode to get a 
    # a tx ID.
    if "txHex" not in d or not isinstance(d["txHex"], str):
        return jsonify(apiError("invalid txHex"))
    if len(d["txHex"]) > 2 * MebiByte:
        return jsonify(apiError("transaction larger than maximum allowed transaction size"))

    with pool.conn() as conn:
        resp = relay(conn, "relay", d)
        
        return jsonify({
            "ok": "error" not in resp,
            "payload": resp,
        })

@app.route('/api/challenges', methods=['POST'])
def challenges():
    d = request.json
    if "challenges" not in d or not isinstance(d["challenges"], list):
        return jsonify(apiError("invalid request format"))
    if len(d["challenges"]) == 0:
        return jsonify(apiError("no challenges requested"))
    if len(d["challenges"]) > MaxChallengesPerRequest:
        return jsonify(apiError(f"cannot request more than {MaxChallengesPerRequest} challenges"))

    with pool.conn() as conn:
        resp = relay(conn, "challenges", d)
        
        return jsonify({
            "ok": "error" not in resp,
            "payload": resp,
        })

@app.route('/api/flag', methods=['POST'])
def flag():
    d = request.json
    if "addr" not in d or not isinstance(d["addr"], str):
        return jsonify(apiError("no address provided"))
    if "reason" in d: 
        if not isinstance(d["reason"], str):
            return jsonify(apiError("invalid reason"))
        if len(d["reason"]) > 250:
            return jsonify(apiError("reason longer than maximum of 250 characters"))
    
    with pool.conn() as conn:
        resp = relay(conn, "flag", d)
        
        return jsonify({
            "ok": resp is True,
            "payload": resp,
        })

def apiError(msg):
    return {
        "ok": False,
        "msg": msg,
    }
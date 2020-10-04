import asyncio
import logging

import asyncio_redis
from decred.util import helpers
from flask import Flask, jsonify, render_template
from flask_uwsgi_websocket import AsyncioWebSocket

from challenges import FEED_CHANNEL

app = Flask(__name__)
ws = AsyncioWebSocket(app)

helpers.prepareLogging(logLvl=logging.DEBUG)
log = helpers.getLogger("WS")

@ws.route('/ws')
async def feed(ws):
    # yield from ws.send("sup")
    asyncio.get_event_loop().create_task(redis_subscribe(ws, FEED_CHANNEL))
    await asyncio_redis.Connection.create()
    while True:
        msg = await ws.receive()
        if msg is not None:
            log.warn(f"received unexpected message from websocket client: {msg}")
        else:
            break

async def redis_subscribe(ws, channel):
    conn = await asyncio_redis.Connection.create()
    sub = await conn.start_subscribe()
    await sub.subscribe([FEED_CHANNEL])
    while ws.connected:
        reply = await sub.next_published()
        await ws.send(reply.value.encode('utf-8'))
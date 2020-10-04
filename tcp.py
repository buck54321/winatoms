"""
Copyright (c) 2020, The Decred developers
See LICENSE for details.
"""

import socket
import threading
from queue import Queue

from decred.util.encode import ByteArray


class Addr:
    """ Addr is a mimic of Go's net.TCPAddr. """

    def __init__(self, ip, port, zone=None):
        """
        Args:
            ip (str or bytes-like): The IP.
            port (int): The port.
            zone (str): The IPv6 scoped addressing zone.
        """
        if isinstance(ip, str):
            ip = decodeStringIP(ip)
        self.ip = ip
        self.port = port
        self.zone = zone


class AddrInfo:
    def __init__(self, ai):
        self.family = ai[0]
        self.type = ai[1]
        self.proto = ai[2]
        self.canonname = ai[3]
        self.sockaddr = ai[4]


def acceptableAddrInfo(ai):
    return ai[0] in (socket.AF_INET, socket.AF_INET6) and ai[1] == socket.SOCK_STREAM


class Connection:

    def __init__(self, host, port):
        """
        Args:
            addr (Addr): The remote address.
        """
        addrInfos = socket.getaddrinfo(host, port)
        if not addrInfos:
            raise Exception(f"failed to resolve address info for {host}:{port}")
        # We're only using the first one right now, but store them all anyway.
        self.addrInfos = [AddrInfo(ai) for ai in addrInfos if acceptableAddrInfo(ai)]
        if not self.addrInfos:
            raise Exception(f"no acceptable address types for {host}:{port}")
        self.sendThread = None
        self.sendQ = Queue()
        self.closeEvent = threading.Event()
        self.sock = None


    def connect(self):
        if not self.addrInfos:
            raise Exception(f"cannot connect. no address info")
        addr = self.addrInfos[0]
        if self.sock:
            self.close()
        self.sock = socket.socket(addr.family, addr.type)
        self.sock.connect(addr.sockaddr)
        self.sendThread = threading.Thread(None, sendLoop, args=(self.sock, self.sendQ, self.closeEvent))
        self.sendThread.start()


    def close(self):
        if not self.sock:
            return
        self.sendQ.put(b'')
        self.sendThread.join()
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        self.closeEvent.set()
        self.sock = None
        self.sendThread = None
        self.sendQueue = Queue()
        self.closeEvent.clear()


    def send(self, msg):
        # zero-length message not allowed
        if len(msg) == 0:
            raise Exception("cannot send zero-length message")
        self.sendQ.put(msg)


    def readN(self, n):
        return readN(self.sock, n)

class PooledConnection(Connection):
    def __init__(self, pool, *a, **k):
        super().__init__(*a, **k)
        self.pool = pool
        self.id = id(self)
        self.connect()

    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.pool.returnConnection(self)


class ConnectionPool:
    def __init__(self, *a, constructor=PooledConnection, **k):
        """
        constructor (Callable): Will be passed *a and **k. Returned object must have a
            unique 'id' attribute and a 'close' method accepting no arguments.
        """
        self.a = a
        self.k = k
        self.constructor = constructor
        self.freeConns = {}
        self.usedConns = {}
        self.connLock = threading.Lock()

    def close(self):
        with self.connLock:
            for connID, conn in list(self.freeConns.items()):
                conn.close()
                del self.freeConns[connID]
            for connID, conn in list(self.usedConns.items()):
                conn.close()
                del self.usedConns[connID]

    def conn(self):
        with self.connLock:
            if len(self.freeConns):
                connID, conn = self.freeConns.popitem()
                self.usedConns[connID] = conn
                return conn
            # No free conns. Let's create one.
            conn = self.constructor(self, *self.a, **self.k)
            self.usedConns[conn.id] = conn
            return conn

    def returnConnection(self, conn):
        with self.connLock:
            del self.usedConns[conn.id]
            self.freeConns[conn.id] = conn


def decodeStringIP(ip):
    """
    Parse an IP string to bytes.

    Args:
        ip (str): The string-encoded IP address.

    Returns:
        bytes-like: The byte-encoded IP address.
    """
    try:
        return socket.inet_pton(socket.AF_INET, ip)
    except OSError:
        return socket.inet_pton(socket.AF_INET6, ip)

def send(sock, msg):
    sent = 0
    msgLen = len(msg)
    b = msg.b
    while sent < msgLen:
        n = sock.send(b[sent:])
        if n == 0:
            raise Exception("socket connection broken")
        sent += n


def sendLoop(sock, q, closed):
    while True:
        msg = q.get()
        # zero length msg is indicator to exit.
        if len(msg) == 0:
            break
        if closed.is_set():
            return
        send(sock, msg)

class EOF(Exception):
    pass

def readN(sock, n):
    b = ByteArray(length=n)
    recvd = 0
    while recvd < n:
        chunk = sock.recv(min(n - recvd, 2048))
        if chunk == "":
            raise EOF("socket connection broken")
        b[recvd] = chunk
        recvd += len(chunk)
    return b
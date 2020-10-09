import atexit
import json
import math
import os
import socket
import sys
import threading
import time
from queue import Queue
from socketserver import BaseRequestHandler, ThreadingMixIn, UnixStreamServer
from typing import Any, Callable

import psycopg2
import redis
from base58 import b58encode
from decred.crypto import crypto, opcode
from decred.crypto.secp256k1.curve import generateKey
from decred.dcr import nets, txscript
from decred.dcr.addrlib import AddressScriptHash, decodeAddress
from decred.dcr.dcrdata import WS_DONE, DcrdataBlockchain
from decred.dcr.wire import msgtx
from decred.util import helpers
from decred.util.encode import ByteArray

import tcp

FEED_CHANNEL = "winatoms-feed"

log = helpers.getLogger("CHALLENGES")

DummyHash = ByteArray("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")

MinDisplayFunding = 1e7 # 0.1 DCR of funding before display.

# Standard network fee rate.
feeRate = 10 # DCR / byte

SockAddr = "/tmp/challenge.sock"

_addrIDs = {
    nets.mainnet.Name: ByteArray("0786"),  # Dw
    nets.testnet.Name: ByteArray("0fab"),  # Tw
    nets.simnet.Name:  ByteArray("0f17"),  # Sw
}

_netBytes = {
    nets.mainnet.Name: ByteArray(1),
    nets.testnet.Name: ByteArray(2),
    nets.simnet.Name:  ByteArray(3),
}

def scriptVersion(netParams):
    return _addrIDs[netParams.Name] + _netBytes[netParams.Name]

useLocalDcrdata = "--localdcrdata" in sys.argv

DcrdataDBPath = "./dcr.db"
WebRoot = "."

doneEvent = threading.Event()
def shutdownHandler():
    log.info('shutting down')
    doneEvent.set()

atexit.register(shutdownHandler)

class TwitterConfig:
    apiKey = "MB7i1q5jybKjztZfRgdLOSGuA"
    secretKey = "s21JlbpV9rSlh9PnDdn5TB55vgbl5syT3K9aHsQLxNvCvyu69D"
    bearerToken = "AAAAAAAAAAAAAAAAAAAAAJrQHgEAAAAAdLuQpp5NKCGZKp0NEPdU0nZugwA%3DvrhNNYEPGYF4pWw0Zw4cY0bacFcBMBIoei11npKcbAgHeT1UWm"
    accessToken = "1305620250529017863-wNnXfznP0qQ3W7rsEytO9ythm7NyRM"
    accessTokenSecret = "Bx9iInYiozTWr53YbWT4zasOdg2LRfxHi90XrFPdI3SVz"

# Decay factor is chosen so that score decays by 1/e every week.
decayFactor = 1 / (60 * 60 * 24 * 7)

# create user winatoms password '8158675309'
# database name winatoms

class PG:
    user = "winatoms"
    password = "8158675309"
    host = "127.0.0.1"
    port = 5432

    @staticmethod
    def dsn(netParams):
        return f"dbname={PG.dbName(netParams)} user={PG.user} password={PG.password} host={PG.host} port={PG.port}"

    @staticmethod
    def dbName(netParams):
        return f"winatoms_{netParams.Name}"

CreateChallenges = """
CREATE TABLE IF NOT EXISTS challenges(
    address VARCHAR(40) PRIMARY KEY,
    double_hash BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    proof BYTEA NOT NULL,
    signing_key BYTEA NOT NULL,
    prompt TEXT NOT NULL,
    register_time BIGINT NOT NULL,
    img_path VARCHAR(128),
    tweet VARCHAR(20),
    flagged BOOLEAN DEFAULT FALSE,
    approved BIGINT DEFAULT 0
);
"""

CreateFunds = """
CREATE TABLE IF NOT EXISTS funding(
    address VARCHAR(40) NOT NULL,
    tx_hash BYTEA NOT NULL,
    vout INTEGER NOT NULL,
    value BIGINT,
    tx_time BIGINT,
    redemption BYTEA,
    vin INTEGER,
    redeem_time BIGINT,
    FOREIGN KEY (address) REFERENCES challenges(address)
);
"""

CreateFlags = """
CREATE TABLE IF NOT EXISTS flags(
    address VARCHAR(40) NOT NULL,
    reason VARCHAR(250) NOT NULL,
    stamp  BIGINT NOT NULL,
    FOREIGN KEY (address) REFERENCES challenges(address)
);
"""

InsertFlag = """
INSERT INTO flags(address, reason, stamp) VALUES(%s, %s, %s);
"""

FlagChallenge = """
UPDATE challenges SET flagged = TRUE WHERE address = %s;
"""

InsertChallenge = """
INSERT INTO challenges(
    address, double_hash, nonce, proof, 
    signing_key, prompt, register_time, img_path
) VALUES(%s, %s, %s, %s, %s, %s, %s, %s);
"""

SelectFunded = """
SELECT address, tx_hash, vout, value, tx_time
FROM funding 
WHERE redemption IS NULL;
"""

SelectUnfunded = """
SELECT challenges.address, double_hash, nonce, prompt, register_time, 
    img_path, tweet, flagged, approved
FROM challenges LEFT JOIN funding
ON challenges.address = funding.address
WHERE funding.address IS NULL
    AND register_time > %s;
"""

SelectMempoolFunds = """
SELECT address, tx_hash, vout, value, tx_time, redemption, vin, redeem_time
FROM funding
WHERE tx_time = 0;
"""

SelectChallenge = """
SELECT address, double_hash, nonce, prompt, register_time, 
    img_path, tweet, flagged, approved
FROM challenges
WHERE address = %s;
"""

UpdateRedemption = """
UPDATE funding 
SET redemption = %s, vin = %s, redeem_time = %s
WHERE tx_hash = %s
    AND vout = %s;
"""

UpdateRedeemTime = """
UPDATE funding
SET redeem_time = %s
WHERE tx_hash = %s
    AND vout = %s;
"""

InsertFunds = """
INSERT INTO funding(address, tx_hash, vout, value, tx_time)
VALUES (%s, %s, %s, %s, %s);
"""

SelectKeyByProof = """
SELECT signing_key, double_hash
FROM challenges
WHERE address = %s 
    AND proof = %s;
"""


HOST = "localhost"
PORT = 54345

serverBound = threading.Event()

class Challenge:
    def __init__(self, addr, doubleHash, nonce, prompt, registerTime, imgPath=None,
            tweet=None, flagged=False, approved=0):
        self.addr = addr
        self.doubleHash = doubleHash
        self.nonce = nonce
        self.prompt = prompt
        self.registerTime = registerTime
        self.imgPath = imgPath
        self.tweet = tweet
        self.funds = {}
        self.score = 0
        self.flagged = flagged
        self.approved = approved

    @staticmethod
    def fromDBRow(row):
        addr, doubleHash, nonce, prompt, registerTime, imgPath, tweet, flagged, approved = row
        return Challenge(
            addr,
            ByteArray(bytes(doubleHash)),
            ByteArray(bytes(nonce)),
            prompt,
            registerTime,
            imgPath,
            tweet,
            flagged,
            approved,
        )

    def jsondict(self):
        return dict(
            addr=self.addr,
            doubleHash=self.doubleHash.hex(),
            nonce=self.nonce.hex(),
            prompt=self.prompt,
            registerTime=self.registerTime,
            imgPath=self.imgPath,
            tweet=self.tweet,
            funds=self.totalFunds(),
            fmtVal=self.fmtVal(),
            score=self.calcScore(),
            flagged=self.flagged,
            approved=self.approved,
        )

    def addFunds(self, utxo):
        self.funds[utxo.id] = utxo

    def totalFunds(self):
        return sum(f.value for f in self.funds.values() if f.redemption == None)

    def calcScore(self):
        # Must add scores from each funding point. This allows a challenge to 
        # be "refreshed" by adding new funds.
        score = 0
        for f in self.funds.values():
            if f.redemption:
                continue
            txTime = f.txTime if f.txTime else time.time()
            secondsSince = time.time() - txTime
            score += f.value * math.exp(-secondsSince*decayFactor)
        self.score = score
        return score

    def fmtVal(self):
        return f"{self.totalFunds() / 1e8:.8f}".rstrip("0").rstrip(".")

    def truncatedPrompt(self):
        if len(self.prompt) < 800:
            return self.prompt
        return self.prompt[:790].rstrip() + "…"

    def displayable(self):
        return self.totalFunds() > MinDisplayFunding and (not self.flagged or self.approved > 0)


class FundingOutput:
    def __init__(self, addr, txHash, vout, value, txTime, redemption=None, vin=-1, redeemTime=0):
        self.addr = addr
        self.txHash = txHash
        self.vout = vout
        self.value = value
        self.txTime = txTime
        self.redemption = redemption
        self.redeemTime = redeemTime
        self.id = txHash + vout # Simple concat. ByteArray is a valid dict key.


class ClientHandler(BaseRequestHandler):
    mgr = None
    socks = {}
    def handle(self):
        sockID = id(self.request)
        self.socks[sockID] = self.request
        try:
            while True:
                lenB = tcp.readN(self.request, 2)
                msgB = tcp.readN(self.request, lenB.int())
                req = json.loads(msgB.b)
                resp = ClientHandler.mgr.handleRequest(req)
                msgB = json.dumps(resp).encode("utf-8")
                packet = ByteArray(len(msgB), length=2) + msgB
                self.request.sendall(packet.b)
        except tcp.EOF:
            pass
        finally:
            del self.socks[sockID]

class ChallengeServer(ThreadingMixIn, UnixStreamServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()
        serverBound.set()
    
    def server_close(self, *a, **k):
        for sock in ClientHandler.socks.values():
            sock.close()
        super().server_close(*a, **k)

class DBConn(psycopg2.extensions.connection):
    def __init__(self, pool, *a, **k):
        super().__init__(*a, **k)
        self.id = id(self)
        self.pool = pool
    def __exit__(self, exc_type, exc_value, exc_traceback):
        super().__exit__(exc_type, exc_value, exc_traceback)
        self.pool.returnConnection(self)

class ChallengeManager:
    def __init__(self, netParams):
        log.info("spawning a new ChallengeManager")

        self.netParams = netParams
        self.challenges = {}
        self.threads = []
        self.blockchain = None
        self.requestHandlers = {
            "index": self.handleIndex,
            "liveChallengeList": self.handleLiveChallengeList,
            "contract": self.handleContract,
            "challenge": self.handleChallenge,
            "solve": self.handleSolve,
            "relay": self.handleRelay,
            "challenges": self.handleChallenges,
            "flag": self.handleFlag,
        }
        self.twitter_ = None

        self.cxnPool = tcp.ConnectionPool(PG.dsn(netParams), constructor=DBConn)
        self.db(self.createTables_)

        ClientHandler.mgr = self
        os.unlink(SockAddr)
        self.server = ChallengeServer(SockAddr, ClientHandler)
        self.serverThread = threading.Thread(None, self.server.serve_forever)
        self.serverThread.start()
        serverBound.wait()

        self.redis = redis.Redis(host='localhost', port=6379)
        self.publishQueue = Queue()
        self.publishThread = threading.Thread(None, self.publishLoop)
        self.publishThread.start()

        self.init()

    def addThread(self, thread):
        self.threads.append(thread)
        ts = [t for t in self.threads if t.is_alive()]
        self.threads = ts

    def init(self):
        self.challenges.clear()
        self.loadFundedChallenges()
        self.loadUnfundedChallenges()
        self.connectDcrdata()
        log.info(f"subscribing to {len(self.challenges)} challenge addresses")
        self.blockchain.subscribeAddresses(self.challenges.keys(), self.addrEvent)
        updateThread = threading.Thread(target=self.updateChallenges)
        updateThread.start()
        self.addThread(updateThread)

    def connectDcrdata(self):
        if self.blockchain:
            self.blockchain.close()

        dcrdataPath = "https://explorer.dcrdata.org" if self.netParams == nets.mainnet else "https://testnet.dcrdata.org"
        if useLocalDcrdata:
            dcrdataPath = "http://localhost:7777" if self.netParams == nets.mainnet else "http://localhost:17778"

        self.blockchain = DcrdataBlockchain(DcrdataDBPath, self.netParams, dcrdataPath)

        baseEmitter = self.blockchain.dcrdata.emitter
        def emit(sig):
            if sig == WS_DONE and not doneEvent.is_set():
                log.warning(f"lost pubsub connection detected: re-initializing in 5 seconds")
                time.sleep(5)
                try:
                    self.blockchain.dcrdata.ps = None
                    self.blockchain.subscribeAddresses(self.challenges.keys(), self.addrEvent)
                    updateThread = threading.Thread(target=self.updateChallenges)
                    updateThread.start()
                    self.addThread(updateThread)
                except Exception as e:
                    print("failed dcrdata reconnect:", e)
                    return
            baseEmitter(sig)
        self.blockchain.dcrdata.emitter = emit

        self.blockchain.subscribeBlocks(self.processBlock)

    def publishLoop(self):
        while True:
            msg = self.publishQueue.get()
            if msg == b'':
                log.debug("quitting publish loop")
                return
            self.redis.publish(FEED_CHANNEL, json.dumps(msg))

    def createTables_(self, cursor):
        cursor.execute(CreateChallenges)
        cursor.execute(CreateFunds)
        cursor.execute(CreateFlags)

    def close(self):
        doneEvent.set()
        self.publishQueue.put(b'')
        if self.cxnPool:
            self.cxnPool.close()
            self.cxnPool = None
        if self.server:
            self.server.server_close()
            self.server.shutdown()
            self.serverThread.join()
            self.server = None
        if self.publishThread:
            self.publishThread.join()
        if self.blockchain:
            self.blockchain.close()
        
    def db(self, f, *a):
        # When used as a context manager, a psycopg2.connection will
        # auto-commit.
        with self.cxnPool.conn() as conn:
            with conn.cursor() as cursor:
                return f(cursor, *a)

    def processBlock(self, sig):
        block = sig["message"]["block"]
        blockHeight = block["height"]
        log.info(f"block received at height {blockHeight}")
        self.publishQueue.put({
            "event": "block",
            "blockHeight": blockHeight,
        })
        self.updateRedeemTimes()
        self.refreshScoreIndex()

    def refreshScoreIndex(self):
        for ch in self.challenges.values():
            ch.calcScore()
        self.scoreIndex = sorted([ch for ch in self.challenges.values() if ch.displayable()], key=lambda ch: -ch.score)

    def updateRedeemTimes(self):
        # Get redemptions that don't have a redemption time.
        funding = self.db(self.selectMempoolFunds_)
        count, found = 0, 0
        # for addr, txHash, vout, redemption in funding:
        for funds in funding:
            count += 1
            txid = funds.redemption.rhex()
            header = self.blockchain.blockForTx(txid)
            if not header:
                continue
            found += 1
            redeemTime = header.timestamp

            self.db(self.updateRedeemTime_, funds.txHash.bytes(), funds.vout, redeemTime)
            
            ch = self.challenges.get(funds.addr)
            if not ch:
                continue
            fundID = funds.txHash + funds.vout
            funds = ch.funds.get(fundID)            
            if not funds:
                log.error(f"no funds found for addr = {funds.addr}, txid = {reversed(funds.txHash)}, vout = {funds.vout}")
                continue
            funds.redeemTime = redeemTime
        
        if count > 0:
            log.info(f"updated {found} of {count} redemption block times")

    def addrEvent(self, addr, txid):
        ch = self.challenges.get(addr)
        if not ch:
            log.error("received address event for unknown challenge %s", addr)
            return
        log.info(f"address event received for addr = {addr}, txid = {txid}")
        tx = self.blockchain.tx(txid)
        self.processTransactionIO(addr, ch, tx)
        self.refreshScoreIndex()
        self.publishQueue.put({
            "event": "addr",
            "addr": ch.addr,
            "funds": ch.totalFunds(),
            "fmtVal": ch.fmtVal(),
        })
        if len(ch.funds) == 0:
            del self.challenges[addr]

    def updateChallenges(self):
        # Get a dict of all current funds.
        log.info("updating challenges")
        fundsTracker = {}
        for ch in self.challenges.values():
            for funds in ch.funds.values():
                fundsTracker[funds.id] = funds
        utxos = self.blockchain.UTXOs(list(self.challenges.keys()))
        log.info(f"processing {len(utxos)} utxos")
        new = 0
        for utxo in utxos:
            if doneEvent.is_set():
                return
            challenge = self.challenges.get(utxo.address)
            if not challenge:
                log.error(f"received utxo for unknown address {utxo.address}")
                continue
            outputID = utxo.txHash + utxo.vout
            fundsTracker.pop(outputID, None)
            # If we already know about these funds, there's nothing left to do.
            if outputID in challenge.funds:
                continue
            new += 1
            # This is new funding. store it in the database.
            funds = FundingOutput(utxo.address, utxo.txHash, utxo.vout, utxo.satoshis, utxo.ts)
            challenge.addFunds(funds)
            self.db(self.insertFunds_, funds)

        log.info(f"found {new} new funding utxos")
        
        # If there are funds remaining in the fundsTracker, they've been spent
        # and we need to locate the spends.

        # 1. Reduce the fundsTracker to a set of addresses.
        updateAddrs = set()
        for funds in fundsTracker.values():
            if funds.redemption:
                continue
            updateAddrs.add(funds.addr)

        log.info(f"looking for redemptions for {len(updateAddrs)} challenges")

        # 2. Get the transaction inputs that spend the address's outputs.
        updates = set()
        for addr in updateAddrs:
            ch = self.challenges[addr]
            for txid in self.blockchain.txidsForAddr(addr):
                if doneEvent.is_set():
                    return
                tx = self.blockchain.tx(txid)
                # Presumably, we don't need to look for outputs, because if they
                # aren't spent, we've already added them with the utxos loop
                # above. So just look for spends of the funding outputs we know
                # about.
                self.processTransactionInputs(ch, tx)
                if len(ch.funds) == 0:
                    updates.add(funds)

        # 3. Check if any of the updated challenges can be deleted from the
        # challenges cache.
        for ch in updates:
            if len(ch.funds) == 0:
                del self.challenges[ch.addr]

        self.refreshScoreIndex()

        log.info("done updating challenges")

    def processTransactionInputs(self, ch, tx):
        for vin, txIn in enumerate(tx.txIn):
            pt = txIn.previousOutPoint
            fundsID = pt.hash + pt.index
            funds = ch.funds.get(fundsID)
            if not funds:
                continue

            # Attempt to get the block time for the redemption.
            log.info(f"redemption found for challenge {funds.addr} worth {funds.value/1e8:8f}DCR")     

            funds.redemption = tx.cachedHash()
            header = self.blockchain.blockForTx(tx.id())
            if header:
                funds.redeemTime = header.timestamp

            self.db(self.updateRedeem_, funds, tx.cachedHash(), vin, funds.redeemTime)

    def processTransactionIO(self, addr, ch, tx):
        self.processTransactionInputs(ch, tx)
        pkScript = txscript.payToAddrScript(decodeAddress(addr, self.netParams))
        found = 0
        for vout, txOut in enumerate(tx.txOut):
            if txOut.pkScript == pkScript:
                funds = FundingOutput(addr, tx.cachedHash(), vout, txOut.value, int(time.time()))
                if funds.id in ch.funds:
                    continue
                found += 1
                ch.addFunds(funds)
                self.db(self.insertFunds_, funds)
        log.info(f"found {found} outputs that pay to challenge {addr}")

    def updateRedeem_(self, cursor, funds, redeemTxHash, vin, redeemTime):
        cursor.execute(UpdateRedemption, (redeemTxHash.bytes(), vin, redeemTime, funds.txHash.bytes(), funds.vout))

    def insertChallenge_(self, cursor, addr, doubleHash, nonce, proof, signingKey, prompt, registerTime, imgPath):
        cursor.execute(InsertChallenge, (addr, doubleHash, nonce, proof, signingKey, prompt, registerTime, imgPath))

    def insertFunds_(self, cursor, funds):
        cursor.execute(InsertFunds, (funds.addr, funds.txHash.bytes(), funds.vout, funds.value, funds.txTime))

    def addNewChallenge(self, ch, proof, signingKey):
        self.db(self.insertChallenge_, 
            ch.addr, 
            ch.doubleHash.bytes(), 
            ch.nonce.bytes(), 
            proof.bytes(),
            signingKey.bytes(),
            ch.prompt,
            ch.registerTime,
            ch.imgPath,
        )

        log.debug(f"subscribing to address {ch.addr}")
        self.blockchain.subscribeAddresses([ch.addr], self.addrEvent)
        self.challenges[ch.addr] = ch

    def selectFunded_(self, cursor):
        cursor.execute(SelectFunded)
        funding = []
        for addr, txHash, vout, value, txTime in cursor.fetchall():
            funding.append(FundingOutput(addr, ByteArray(bytes(txHash)), vout, value, txTime))
        return funding

    def selectUnfunded_(self, cursor, oldest):
        cursor.execute(SelectUnfunded, (oldest,))
        chs = []
        for row in cursor.fetchall():
            chs.append(Challenge.fromDBRow(row))
        return chs

    def selectChallenge_(self, cursor, addr):
        cursor.execute(SelectChallenge, (addr,))
        return Challenge.fromDBRow(cursor.fetchone())

    def selectKeyByProof_(self, cursor, addr, proof):
        cursor.execute(SelectKeyByProof, (addr, proof))
        return cursor.fetchone()

    def insertFlag_(self, cursor, addr, reason, stamp):
        cursor.execute(InsertFlag, (addr, reason, stamp))
        cursor.execute(FlagChallenge, (addr,))


    def updateRedeemTime_(self, cursor, txHash, vout, redeemTime):
        cursor.execute(UpdateRedeemTime, (redeemTime, txHash, vout))

    def selectMempoolFunds_(self, cursor):
        cursor.execute(SelectMempoolFunds)
        funding = []
        for addr, txHash, vout, value, txTime, redemption, vin, redeemTime in cursor.fetchall():
            funding.append(FundingOutput(
                addr,
                ByteArray(bytes(txHash)),
                vout,
                value,
                txTime,
                ByteArray(bytes(redemption)) if redemption else None,
                vin,
                redeemTime,
            ))

        return funding

    def challenge(self, addr):
        ch = self.challenges.get(addr)
        if ch:
            return ch
        return self.db(self.selectChallenge_, addr)

    def submitProof(self, addr, proof, redemptionAddr):
        addrStr = addr.string()
        signingKeyB, doubleHashB = self.db(self.selectKeyByProof_, addrStr, proof.b)
        signingKey = crypto.privKeyFromBytes(ByteArray(bytes(signingKeyB)))

        # Prepare the redemption script
        redeemScript = ByteArray(opcode.OP_SHA256)
        redeemScript += txscript.addData(bytes(doubleHashB))
        redeemScript += opcode.OP_EQUALVERIFY
        redeemScript += txscript.addData(signingKey.pub.serializeCompressed())
        redeemScript += opcode.OP_CHECKSIG

        # Collect all outputs for the address. We could do this from the cache,
        # but we'll generate a new call to dcrdata instead to make sure we have
        # the freshest data.
        utxos = self.blockchain.UTXOs([addrStr])
        if len(utxos) == 0:
            return dict(
              error="challenge is either unfunded or has already been redeemed",
              code=1,
            )

        rewardTx = msgtx.MsgTx.new()
        reward = 0
        for utxo in utxos:
          reward += utxo.satoshis
          prevOut = msgtx.OutPoint(utxo.txHash, utxo.vout, msgtx.TxTreeRegular)
          rewardTx.addTxIn(msgtx.TxIn(prevOut, valueIn=utxo.satoshis))

        # sigScript = txscript.addData(answerHash) + txscript.addData(script)
        # rewardTx.addTxIn(msgtx.TxIn(prevOut, signatureScript=sigScript))

        # Add the reward output with zero value for now.
        txout = msgtx.TxOut(pkScript=txscript.payToAddrScript(redemptionAddr))
        rewardTx.addTxOut(txout)

        # Get the serialized size of the transaction. Since there are no signatures
        # involved, the size is known exactly. Use the size to calculate transaction
        # fees.
        # 1 + 73 = signature
        # 1 + 32 = answer hash
        # 1 + 70 = redeem script
        sigScriptSize = 1 + 73 + 1 + 32 + 1 + 70
        maxSize = rewardTx.serializeSize() + len(utxos)*sigScriptSize
        fees = feeRate * maxSize
        if reward <= fees:
            return makeErr(f"reward, {reward}, must cover fees {fees}, tx size = {maxSize} bytes, fee rate = {feeRate} atoms/byte")
        netReward = reward - fees
        # Set the value on the reward output.
        txout.value = netReward

        for idx, txIn in enumerate(rewardTx.txIn):
          sig = txscript.rawTxInSignature(rewardTx, idx, redeemScript, txscript.SigHashAll, signingKey.key)
          sigScript = txscript.addData(sig) + txscript.addData(DummyHash) + txscript.addData(redeemScript)
          txIn.signatureScript = sigScript

        return {
            "txHex": rewardTx.serialize().hex(),
        }

    def handleContract(self, payload):
        # Build the script. The first opcode says to hash the input in-place on the
        # stack.
        prompt = payload.get("prompt")
        doubleHash = ByteArray(payload.get("doubleHash"))
        nonce = ByteArray(payload.get("nonce"))
        proof = ByteArray(payload.get("proof"))
        imgPath = payload.get("imgPath")

        redeemScript = ByteArray(opcode.OP_SHA256)
        # Add the doubleHash to the stack.
        redeemScript += txscript.addData(doubleHash)

        # Start with OP_EQUALVERIFY because we don't want to leave a TRUE/FALSE on the
        # stack, we just want to fail if the answer is wrong.
        redeemScript += opcode.OP_EQUALVERIFY
        # We need to generate a key pair for the game key.
        priv = generateKey() # The "Game Key".
        # The rest of the script is like a p2pk.
        redeemScript += txscript.addData(priv.pub.serializeCompressed())
        redeemScript += opcode.OP_CHECKSIG

        gameKey = scriptVersion(self.netParams) + doubleHash + priv.key

        gameKeyEnc = b58encode(gameKey.bytes()).decode()

        # Create the address.
        p2shAddr = AddressScriptHash.fromScript(redeemScript, self.netParams)
        addr = p2shAddr.string()

        ch = Challenge(addr, doubleHash, nonce, prompt, int(time.time()), imgPath)
        self.addNewChallenge(ch, proof, priv.key)

        log.info(f"new challenge! address = {addr}, with_image = {bool(imgPath)}, prompt = {prompt}")
        
        return {
            "address": addr,
            "gameKey": gameKeyEnc,
        }

    def handleChallenge(self, payload):
        chid = payload.get("chid")
        ch = self.challenge(chid)
        if not ch:
            return makeErr(f"unknown challenge address: {chid}")
        return ch.jsondict()


    def handleSolve(self, payload):
        addrStr = payload["addr"]
        proof = ByteArray(payload["proof"])
        redemptionAddrStr = payload["redemptionAddr"]
        addr = decodeAddress(addrStr, self.netParams)
        if not isinstance(addr, AddressScriptHash):
            return makeErr("unsupported address type "+str(type(addr)))
        redemptionAddr = decodeAddress(redemptionAddrStr, self.netParams)
        return self.submitProof(addr, proof, redemptionAddr)

    def handleRelay(self, payload):
        # Looking for exception
        tx = msgtx.MsgTx.deserialize(ByteArray(payload["txHex"]))
        self.blockchain.broadcast(payload["txHex"])
        return tx.id()
    
    def handleChallenges(self, payload):
        chs = []
        for addr in payload["challenges"]:
            ch = self.challenge(addr)
            chs.append({
                "addr": ch.addr,
                "fmtVal": ch.fmtVal(),
                "truncatedPrompt": ch.truncatedPrompt(),
                "imgPath": ch.imgPath,
                "registerTime": ch.registerTime,
            })
        return chs

    def handleLiveChallengeList(self, payload):
        return [ch.addr for ch in self.scoreIndex]

    def handleFlag(self, payload):
        # raise an exception if this isn't a valid address
        addr = payload["addr"]
        reason = payload["reason"] if "reason" in payload else ""
        # decodeAddress(addr, self.netParams)
        ch = self.challenge(addr)
        if not ch:
            return makeErr(f"cannot flag. unknown address {addr}")
        ch.flagged = True
        self.db(self.insertFlag_, addr, reason, int(time.time()))
        self.refreshScoreIndex()
        return True

    def loadFundedChallenges(self):
        rows = 0
        for utxo in self.db(self.selectFunded_):
            rows += 1
            ch = self.challenges.get(utxo.addr)
            if not ch:
                ch = self.db(self.selectChallenge_, utxo.addr)
                self.challenges[ch.addr] = ch

            ch.addFunds(utxo)

        log.info(f"{rows} unspent challenge funding utxos loaded")

    def loadUnfundedChallenges(self):
        maxAge = 60 * 60 * 24 * 7 # Go back one week.
        oldest = int(time.time()) - maxAge
        chs = self.db(self.selectUnfunded_, oldest)
        for ch in chs:
            self.challenges[ch.addr] = ch

        log.info(f"{len(chs)} recent unfunded challenges loaded")

    def handleRequest(self, req):
        route = req["route"]
        handler = self.requestHandlers.get(route, None)
        if not handler:
            return {
                "error": f"unknown request route {route}",
            }
        try:
            return handler(req.get("payload", {}))
        except Exception as e:
            log.error(f"exception encountered with request {req}: {e}")
            print(helpers.formatTraceback(e))
            return {
                "error": "internal server error",
            }

    def handleIndex(self, payload):
        return {}

    

challengeTemplate = dict(
    addr=str,
    doubleHash=str,
    nonce=str,
    proof=str,
    signingKey=str,
    prompt=str,
    registerTime=int,
    imgPath=str,
)

def checkTemplate(thing, template):
    for k, T in template.items():
        if k not in thing:
            raise Exception(f"expected '{k}' in request")
        if not isinstance(thing[k], T):
            wrongType = type(thing[k])
            raise Exception(f"expected '{k}' to be of type {wrongType}")


def makeErr(msg):
    log.error(msg)
    return { "error": msg }
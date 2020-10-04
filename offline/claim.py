"""
Copyright (c) 2020, The Decred developers
"""
import hashlib
import sys

from base58 import b58decode

from decred.dcr import txscript, nets
# Import the rest
from decred.util.encode import ByteArray
from decred.crypto import crypto, opcode
from decred.dcr.dcrdata import DcrdataClient
from decred.dcr.wire import msgtx
from decred.dcr.addrlib import decodeAddress, AddressScriptHash

AddrIDs = {
    nets.mainnet.Name: ByteArray("0786"),  # Dw
    nets.testnet.Name: ByteArray("0fab"),  # Tw
    nets.simnet.Name:  ByteArray("0f17"),  # Sw
}

NetBytes = {
    nets.mainnet.Name: ByteArray(1),
    nets.testnet.Name: ByteArray(2),
    nets.simnet.Name:  ByteArray(3),
}

# Key length = 2 version bytes, 1 network byte, 1 answer double hash, 1 private key
# bytes.
KEY_LENGTH = 2 + 1 + 32 + 32

def hash256(b):
    return ByteArray(hashlib.sha256(bytes(b)).digest())

# Standard network fee rate.
feeRate = 10 # DCR / byte

# Collect the game key, if there is one.
gameKeyEnc = input("Enter the game key?\n")

decoded = ByteArray(b58decode(gameKeyEnc))

if len(decoded) != KEY_LENGTH:
    exit("invalid key length. wanted %d, got %d", KEY_LENGTH, len(decoded))

addrID = decoded.pop(2)
if addrID not in AddrIDs.values():
    exit("invalid address ID %s" + repr(addrID))

netByte = decoded.pop(1)[0]
if netByte not in NetBytes.values():
    exit("invalid net byte" + repr(netByte))

net = nets.mainnet if netByte == 1 else nets.testnet if netByte == 2 else nets.simnet

doubleHash = decoded.pop(32)
gameKey = crypto.privKeyFromBytes(decoded) # The remaining 32 bytes

# Make sure we can connect to dcrdata before proceeding.
url = "https://explorer.dcrdata.org" if net == nets.mainnet else "https://testnet.dcrdata.org" if net == nets.testnet else "http://localhost:17779"

dcrdata = DcrdataClient(url)
# Well be using the dcrdata Insight API
api = dcrdata.insight.api

# Rebuilt the script. See fund.py
redeemScript = ByteArray(opcode.OP_SHA256)
redeemScript += txscript.addData(doubleHash)
redeemScript += opcode.OP_EQUALVERIFY
redeemScript += txscript.addData(gameKey.pub.serializeCompressed())
redeemScript += opcode.OP_CHECKSIG

challengeAddr = AddressScriptHash.fromScript(redeemScript, net)

# Make sure that there is an unspent output going to this address. We'll use the
# insight API exposed by dcrdata to find unspent outputs.

utxos = api.addr.utxo(challengeAddr.string())
if not utxos:
    raise AssertionError("No open challenge for challenge address =" + challengeAddr)

reward = 0
for utxo in utxos:
    print("\nFunding found at {}:{}".format(utxo["txid"], utxo["vout"]))
    reward += utxo.get("satoshis")

print(f"Network = {net.Name}")
print(f"Total challenge funding is {reward/1e8:8f} DCR")

# Collect an address to send the funds to.

recipient = input(f"\nEnter a {net.Name} address to receive the reward.\n")
while True:
    try:
        rewardAddr = decodeAddress(recipient, net)
        break
    except:
        recipient = input(f"Invalid address. Enter an address for {net.Name}.\n")

# Reject identical challenge and reward addresses as user error.
if challengeAddr == recipient:
    raise AssertionError("challenge address cannot be the same as reward address")


# Just a quick check that it's a P2SH address.
if not isinstance(challengeAddr, AddressScriptHash):
    raise AssertionError("challenge address is not a valid pay-to-script-hash address")

while True:
    answer = input("\nWhat is your answer?\n").strip()
    # Get the double hash, build the redeem script, and check if it hashes
    # correctly.
    answerHash = hash256(answer.encode("utf-8"))
    hash2x = hash256(answerHash)
    # Prepare the script and compare its hash to the hash encoded in the
    # challenge address.
    if hash2x != doubleHash:
        print("'{}' is the wrong answer.".format(answer))
        continue

    print("\nCorrect answer!")

    # Build the transaction.
    rewardTx = msgtx.MsgTx.new()
    for utxo in utxos:
        prevOut = msgtx.OutPoint(reversed(ByteArray(utxo["txid"])), int(utxo["vout"]), msgtx.TxTreeRegular)
        rewardTx.addTxIn(msgtx.TxIn(prevOut, valueIn=utxo["satoshis"]))

    # sigScript = txscript.addData(answerHash) + txscript.addData(script)
    # rewardTx.addTxIn(msgtx.TxIn(prevOut, signatureScript=sigScript))

    # Add the reward output with zero value for now.
    txout = msgtx.TxOut(pkScript=txscript.payToAddrScript(rewardAddr))
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
        raise AssertionError(f"reward must be > fees")
    netReward = reward - fees
    # Set the value on the reward output.
    txout.value = netReward

    for idx, txIn in enumerate(rewardTx.txIn):
        sig = txscript.rawTxInSignature(rewardTx, idx, redeemScript, txscript.SigHashAll, gameKey.key)
        sigScript = txscript.addData(sig) + txscript.addData(answerHash) + txscript.addData(redeemScript)
        txIn.signatureScript = sigScript

    # print("--maxSize", maxSize, "actualSize", rewardTx.serializeSize())
    # exit()

    # Send the transaction, again using the dcrdata Insight API.
    api.tx.send.post({"rawtx": rewardTx.txHex()})
    print(round(netReward/1e8, 8), "\nDCR reward claimed. Transaction ID:", rewardTx.id())
    break

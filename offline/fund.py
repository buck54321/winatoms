"""
Copyright (c) 2020, The Decred developers
"""
import hashlib
import sys

from base58 import b58encode

from decred.util.encode import ByteArray
from decred.crypto import opcode
from decred.dcr import nets, txscript
from decred.dcr.addrlib import AddressScriptHash
from decred.crypto.secp256k1.curve import generateKey

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

# --mainnet flag must be specified to use mainnet.
isTestNet = "--testnet" in sys.argv
isSimNet = "--simnet" in sys.argv
net = nets.simnet if isSimNet else nets.testnet if isTestNet else nets.mainnet
print(f"Using {net.Name}")

def hash256(b):
    return ByteArray(hashlib.sha256(bytes(b)).digest())

def scriptVersion(netParams):
    return AddrIDs[netParams.Name] + NetBytes[netParams.Name]

# Get the answer from stdin. Strip whitespace from the ends, but nothing else,
# i.e. input is not converted to lower-case.
answer = input("What is the answer?\n").strip().encode("utf-8")

# The actual input needed to spend the transaction is the hash of the answer.
answerHash = hash256(answer)
# The input will be checked against its hash (the double-hash of the answer) to
# satisfy the script.
doubleHash = hash256(answerHash)

# Build the script. The first opcode says to hash the input in-place on the
# stack.
redeemScript = ByteArray(opcode.OP_SHA256)
# Add the doubleHash to the stack.
redeemScript += txscript.addData(doubleHash)

# Start with OP_EQUALVERIFY because we don't want to leave a TRUE/FALSE on the
# stack, we just want to if the answer is wrong.
redeemScript += opcode.OP_EQUALVERIFY
# We need to generate a key pair for the game key.
priv = generateKey() # The "Game Key".
# The rest of the script is like a p2pk.
redeemScript += txscript.addData(priv.pub.serializeCompressed())
redeemScript += opcode.OP_CHECKSIG

gameKey = scriptVersion(net) + doubleHash + priv.key
gameKeyEnc = b58encode(gameKey.bytes()).decode()

# Create the address.
p2shAddr = AddressScriptHash.fromScript(redeemScript, net)

# Print the address.
print("Fund this challenge by sending Decred to", p2shAddr.string())
print(f"The game key is {gameKeyEnc}")
print("The solver will need the game key to claim the prize.")

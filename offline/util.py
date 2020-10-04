import hashlib

from base58 import b58decode

from decred.dcr import txscript, nets
# Import the rest
from decred.util.encode import ByteArray
from decred.crypto import crypto, opcode
from decred.dcr.addrlib import AddressScriptHash

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


def scriptVersion(netParams):
    return AddrIDs[netParams.Name] + NetBytes[netParams.Name]

def hash256(b):
    return ByteArray(hashlib.sha256(bytes(b)).digest())

def decodeGameKey(gk):
    decoded = ByteArray(b58decode(gk))

    addrID = decoded.pop(2)
    if addrID not in AddrIDs.values():
        exit("invalid address ID %s" + repr(addrID))

    netByte = decoded.pop(1)[0]
    if netByte not in NetBytes.values():
        exit("invalid net byte" + repr(netByte))

    net = nets.mainnet if netByte == 1 else nets.testnet if netByte == 2 else nets.simnet

    doubleHash = decoded.pop(32)
    signingKey = crypto.privKeyFromBytes(decoded) # The remaining 32 bytes

    # Rebuilt the script. See fund.py
    redeemScript = ByteArray(opcode.OP_SHA256)
    redeemScript += txscript.addData(doubleHash)
    redeemScript += opcode.OP_EQUALVERIFY
    redeemScript += txscript.addData(signingKey.pub.serializeCompressed())
    redeemScript += opcode.OP_CHECKSIG

    challengeAddr = AddressScriptHash.fromScript(redeemScript, net)

    return net, signingKey, doubleHash, redeemScript, challengeAddr
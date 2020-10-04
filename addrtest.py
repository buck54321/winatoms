from base58 import b58encode
from decred.crypto.rando import generateSeed, newHash
from decred.dcr import addrlib, nets
from decred.util.encode import ByteArray

# if __name__ == "__main__":
#  for i in range(256):
#     b = ByteArray("0f17") + ByteArray(3) + newHash() + newHash()
#     enc = b58encode(b.bytes()).decode()
#     print(i, enc)

# addr = addrlib.AddressPubKeyHash(newHash()[:20], nets.mainnet)

# print("addr", addr.string(), addr.netID.hex())

DummyHash = ByteArray("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")

redeemScript = ByteArray(opcode.OP_SHA256)
redeemScript += txscript.addData(newHash())
redeemScript += opcode.OP_EQUALVERIFY
redeemScript += txscript.addData(signingKey.pub.serializeCompressed())
redeemScript += opcode.OP_CHECKSIG

txHex = (
    "0100000001aac1eeaecbba3ee756053d7177ef76dec3e2709be1d605711022a4e72d9"
    "2acda0000000000ffffffff01cad5f5050000000000001976a914523368819aa5628c"
    "cc178de8686e6153fb7ec67588ac00000000000000000100e1f505000000000000000"
    "000000000b1483045022100be3f496646f8f99a182e9ffa97a8da050b0bdf679c0a3c"
    "2abbbe9874e77e48af02200e2033a5301b351be66478bedf0e65cfb07a104e3dbe3cd"
    "d6316f2d6aafe93de0120ba7816bf8f01cfea414140de5dae2223b00361a396177a9c"
    "b410ff61f20015ad46c0204f8b42c22dd3729b519ba6f68d2da7cc5b2d606d05daed5"
    "ad5128cc03e6c635888210227726129c88a525ecb55d2ff5390a447894f6b810d977e"
    "25f91ea3b5e2d66d6eac"
)
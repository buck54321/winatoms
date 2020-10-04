from getpass import getpass
import sys

from util import decodeGameKey, hash256

if len(sys.argv) < 2:
    print("no game key supplied")

reader = input
if "--noecho" in sys.argv:
    reader = getpass

gameKeyEnc = sys.argv[len(sys.argv) - 1]

try:
    net, _, doubleHash, _, challengeAddr = decodeGameKey(gameKeyEnc)
except Exception as e:
    exit(f"Error decoding game key '{gameKeyEnc}': {str(e)}")

print(f"network = {net.Name}")
print(f"challenge address = {challengeAddr.string()}")

answer = reader("What is the solution?\n").strip().encode("utf-8")
if hash256(hash256(answer)) != doubleHash:
    exit(f"!!! Solution failed verification !!!")

exit("Sucess! Solution passed verification")
import atexit
import subprocess
import sys

from decred.dcr import nets
from decred.util import helpers

from challenges import ChallengeManager

helpers.prepareLogging()
log = helpers.getLogger("SERVER")

netParams = nets.mainnet
if "--testnet" in sys.argv:
    netParams = nets.testnet
if "--simnet" in sys.argv:
    netParams = nets.simnet

def runWSGI_http():
    return subprocess.Popen(["uwsgi", "--socket=localhost:5000", "--master", 
        "--wsgi=winatoms:app", "--python-autoreload=1", "--die-on-term"])

def runWSGI_ws():
    return subprocess.Popen(["uwsgi", "--http=localhost:5001", "--http-websockets", 
        "--asyncio=100", "--greenlet",  "--master", "--wsgi=ws:app", "--die-on-term"])

if __name__ == "__main__":
    mgr = ChallengeManager(netParams)
    http = runWSGI_http()
    ws = runWSGI_ws()

    try:
        http.wait()
    except KeyboardInterrupt:
        pass

    try:
        ws.wait()
    except KeyboardInterrupt:
        pass
    
    mgr.close()
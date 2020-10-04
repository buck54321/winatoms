const addrLen = 35

const tried = {}

dummyHash = /0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef/gi

function run () {
  const main = Doc.idel(document, 'main')
  const doubleHash = hexToBytes(main.dataset.doubleHash)
  const nonce = hexToBytes(main.dataset.nonce)
  const funds = parseInt(main.dataset.funds)
  const addr = main.dataset.addr
  var weSolved = false
  const page = Doc.parsePage(document, [
    'solution', 'addrBox', 'addr', 'addrErr', 'redemptionAddr', 'editAddress',
    'solutionSubmit', 'solutionProcessing', 'addrSubmit', 'winnerSpinner',
    'winnerConfirmation', 'txHex', 'blocker', 'txHex', 'instantRedeem',
    'backToPlay', 'unfundedMsg', 'solutionErr', 'redeemErr', 'redemptionLink',
    'doneMsg', 'challengeVal', 'keepTryingBttn', 'solvedMsg'
  ])
  var redemptionAddr = State.fetch('redemptionAddr')
  if (redemptionAddr) {
    page.redemptionAddr.textContent = redemptionAddr
    Doc.show(main)
  } else {
    Doc.show(page.addrBox)
  }

  const sumbitAddr = (e) => {

    // TODO: Do a server round-trip to validate the address, or implement
    // btc base-58 and check the checksum and network bytes ourselves.

    page.addrErr.textContent = ''
    redemptionAddr = page.addr.value
    invalid = redemptionAddr.length !== addrLen || new RegExp(/[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]+$/).test(redemptionAddr)
    if (invalid) {
      page.addrErr.textContent = 'invalid address'
      return
    }
    page.redemptionAddr.textContent = redemptionAddr
    State.store('redemptionAddr', redemptionAddr)
    Doc.show(main)
    Doc.hide(page.addrBox)
  }
    
  Doc.bind(page.addr, 'keyup', e => { 
    if (e.keyCode !== 13) return
    sumbitAddr(e)
  })
  Doc.bind(page.addrSubmit, 'click', e => { sumbitAddr(e) })
    

  Doc.bind(page.editAddress, 'click', e => {
    page.addr.value = redemptionAddr
    Doc.show(page.addrBox)
    Doc.hide(main)
  })

  setTriedBorder = t => {
    if (t) {
      page.solution.classList.add('tried')
    } else {
      page.solution.classList.remove('tried')
    }
  }

  setProcessing = t => {
    if (t) {
      page.solution.readOnly = true
      Doc.show(page.solutionProcessing)
      Doc.hide(page.solutionSubmit)
    } else {
      page.solution.readOnly = false
      Doc.hide(page.solutionProcessing)
      Doc.show(page.solutionSubmit)
    }
  }

  const trySolution = async () => {
    Doc.hide(page.solutionErr)
    const solutionStr = page.solution.value
    if (solutionStr === '') {
      setProcessing(false)
      return
    }
    const solution = encodeUTF8(solutionStr)
    const solutionHash = await sha256(solution)
    const h2 = await sha256(solutionHash)

    console.log("--solution -> doubleHash", solutionStr, bytesToHex(h2), bytesToHex(doubleHash))
     
    if (!bytesAreEqual(h2, doubleHash)) {
      tried[solutionStr] = true
      setTriedBorder(true)
      setProcessing(false)
      return
    }

    const noncedHash = new Uint8Array(solution.length + 16)
    noncedHash.set(nonce, 0)
    noncedHash.set(solution, 16)
    const proof = await sha256(noncedHash)

    const resp = await postJSON('/api/solve', {
      proof: bytesToHex(proof),
      addr: addr,
      redemptionAddr: redemptionAddr,
    })

    if (!checkResponse(resp)) {
      if (resp.payload && resp.payload.code === 1) {
        Doc.show(page.blocker, page.unfundedMsg)
        return
      }
      page.solutionErr.textContent = 'error submitting proof'
      console.error('error submitting proof:', resp)
      Doc.show(page.solutionErr)
      setProcessing(false)
      return
    }
    const payload = resp.payload

    console.log("--payload", payload)

    txHex = payload.txHex.replace(dummyHash, bytesToHex(solutionHash))
    page.txHex.textContent = txHex
    Doc.show(page.winnerConfirmation, page.blocker)
  }

  Doc.bind(page.instantRedeem, 'click', async () => {
    const txHex = page.txHex.textContent
    if (!txHex) return
    weSolved = true
    const resp = await postJSON('/api/relay', {
      "txHex": txHex
    })
      

    console.log("--resp", resp)

    if (!checkResponse(resp)) {
      weSolved = false
      page.redeemErr.textContent = 'error sending redemption'
      Doc.show(page.redeemErr)
      console.error('redeem error:', resp)
      return
    }
    page.redemptionLink.href = `https://testnet.dcrdata.org/tx/${resp.payload}`
    Doc.hide(page.winnerConfirmation)
    Doc.show(page.doneMsg)
  })

  Doc.bind(page.solution, 'keyup', e => {
    setTriedBorder(tried[page.solution.value])
    if (e.keyCode !== 13) return
    setProcessing(true)
    trySolution()
  })
    
  Doc.bind(page.solutionSubmit, 'click', () => {
    setProcessing(true)
    trySolution()
  })

  Doc.bind(page.keepTryingBttn, 'click', () => { 
    Doc.hide(page.blocker, page.solvedMsg)
    setProcessing(false)
  })

  ws = new MessageSocket('ws', msg => {

    console.log("--a.0")

    if (msg.event === 'addr' && msg.addr === addr) {
      page.challengeVal.textContent = msg.fmtVal

      console.log("--a.1", msg.funds === 0, !weSolved)

      if (msg.funds === 0 && !weSolved) {
        Doc.show(page.blocker, page.solvedMsg)
        Doc.hide(page.winnerConfirmation)
      }
    }
  })
}

run()
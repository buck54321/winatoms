const MebiByte = 1024 * 1024
const MaxFileSize = MebiByte // 1 MiB
const KeyVizText = 'Hide Game Key'
const KeyHiddenText = 'Show Game Key'

const MIME = {
  JPEG: 1,
  PNG: 2,
  GIF: 3
}

function imgMimeType (arrBuffer) {
  var header = bytesToHex(new Uint8Array(arrBuffer))
  switch (header) {
    case "89504e47":
      return MIME.PNG
    case "47494638":
      return MIME.GIF
    case "ffd8ffe0":
    case "ffd8ffe1":
    case "ffd8ffe2":
    case "ffd8ffe3":
    case "ffd8ffe8":
      return MIME.JPEG
  }
  return null
}

function run () {
  // const main = Doc.idel(document, 'main')
  const page = Doc.parsePage(document.body, [
    'prompt', 'imgBox', 'echoToggle', 'solution', 'submitSolution', 'fileSelector',
    'fileInput', 'imgPreview', 'imgPrompt', 'fileRemover', 'solutionErr',
    'promptErr', 'keySaver', 'keyWaiting', 'keyBlocker', 'keyEye', 'gameKey',
    'keyAddr', 'keyVizToggle', 'keySaveBttn', 'keyVizMsg', 'doneBttn',
    'fileSpinner', 'liveFunds'
  ])
  var gameData = {}

  // Doc.show(page.keyBlocker)
  // Doc.hide(page.keyWaiting)
  // gameData.gameKey = "4VsNqZTb2bDty2akSb2GNHhTPnVTjvmbWocxYfeTtHpEsAEoDXBmU96S7SbdpAJ6AW4ac6JTzCL1qk5bbdiRcS74RE7U"
  // gameData.address = "TsYWmUCLZsGMsTPtCn9a8DgFqfuABSbaJDE"

  Doc.bind(page.echoToggle, 'click', () => {
    if (page.echoToggle.classList.contains('ico-eye-open')) {
      page.echoToggle.classList.add('ico-eye-closed')
      page.echoToggle.classList.remove('ico-eye-open')
      page.solution.type = 'text'
      return
    }
    page.echoToggle.classList.add('ico-eye-open')
    page.echoToggle.classList.remove('ico-eye-closed')
    page.solution.type = 'password'
  })

  // Part of a hack to keep the browser from offering to save the solution's 
  // type="password" input.
  Doc.bind(page.solution, 'focus', () => { page.solution.removeAttribute('readonly') })

  setImgSrc = src => {
    if (src) {
      page.imgPreview.src = src
      Doc.hide(page.imgPrompt, page.fileSelector, page.fileSpinner)
      Doc.show(page.imgPreview, page.fileRemover)
      return
    }
    page.imgPreview.src = ''
    Doc.show(page.imgPrompt, page.fileSelector)
    Doc.hide(page.imgPreview, page.fileRemover, page.fileSpinner)
  }

  const reader = new FileReader()
  var imgFile, imgURL
  reader.onload = e => {
    setImgSrc(e.target.result)
    working(false)
  }

  const mimeChecker = new FileReader()
  mimeChecker.onload = e => {
    const imgType = imgMimeType(e.target.result)
    if (!imgType) {
      working(false)
      console.error("wrong file type", imgFile.type)
      return
    }
    reader.readAsDataURL(imgFile)
  }

  const working = (on) => {
    if (on) {
      Doc.hide(page.imgPrompt, page.fileSelector, page.fileRemover)
      Doc.show(page.fileSpinner)
    } else {
      Doc.hide(page.fileSpinner)
      if (page.imgPreview.src) {
        Doc.show(page.fileRemover)
      } else {
        Doc.show(page.fileSelector, page.imgPrompt)
      }
      Doc.show()
    }
    
  }

  const processImg = async blob => {
    if (blob.size > MaxFileSize) {
      if (imgMimeType(blob.slice(0, 4)) == MIME.GIF) {
        alert(`file size, ${blob.size} bytes, is larger than the max allowed for a gif, ${MaxFileSize}`)
        working(false)
        return
      }
      const targetSize = 0.8 * MaxFileSize
      console.log(`downsizing image from ${blob.size / MebiByte} MiB to ~${targetSize / MebiByte} MiB`)
      const img = new Image()
      Doc.bind(img, 'load', () => {        
        const adjustmentFactor = Math.sqrt(targetSize / blob.size)
        const canvas = document.createElement('canvas')
        const [w, h] = [img.width * adjustmentFactor, img.height * adjustmentFactor]
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d')
        ctx.drawImage(img, 0, 0, w, h)
        canvas.toBlob(smallerBlob => {
          console.log(`downsized image size = ${ smallerBlob.size / MebiByte} MiB`)
          processImg(smallerBlob) // recurse until below MaxFileSize
        })
      })
      img.src = URL.createObjectURL(blob)
      return
    }
    imgFile = blob
    // console.log("Filename: " + imgFile.name)
    // console.log("Type: " + imgFile.type)
    // console.log("Size: " + imgFile.size + " bytes")
    mimeChecker.readAsArrayBuffer(imgFile.slice(0, 4))
  }

  Doc.bind(page.fileSelector, 'click', () => page.fileInput.click())
  Doc.bind(page.fileRemover, 'click', () => {
    imgFile = null
    imgURL = null
    setImgSrc(false)
  })
  Doc.bind(page.fileInput, 'change', async () => {
    if (!page.fileInput.value) return
    working(true)
    processImg(page.fileInput.files[0])
  })
  

  ;['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    Doc.bind(document, eventName, e => {
      e.preventDefault()
      e.stopPropagation()
    })
  })

  Doc.bind(page.imgBox, 'dragenter', e => { page.imgBox.classList.add('focus') })
  Doc.bind(page.imgBox, 'dragover', e => { page.imgBox.classList.add('focus') })
  Doc.bind(page.imgBox, 'dragleave', e => { page.imgBox.classList.remove('focus') })

  Doc.bind(page.imgBox, 'drop', e => {
    working(true)
    page.imgBox.classList.remove('focus')
    if (e.dataTransfer.files[0]) {
      processImg(e.dataTransfer.files[0])
      return
    }
    if (e.dataTransfer.getData("url")) {
      imgURL = e.dataTransfer.getData("url")
      img = new Image()
      img.setAttribute('crossorigin', 'anonymous')
      Doc.bind(img, 'load', e => {
        const canvas = document.createElement('canvas')
        canvas.width = img.width
        canvas.height = img.height
        ctx = canvas.getContext('2d')
        ctx.drawImage(img, 0, 0)
        canvas.toBlob(processImg)
      })
      img.src = imgURL
    }
    working(false)
  })

  Doc.bind(page.imgPrompt, 'keypress', e => { e.preventDefault() })
  Doc.bind(page.imgPrompt, 'focus', () => {
    page.imgBox.classList.add('focus')
  })
  Doc.bind(page.imgPrompt, 'blur', () => {
    page.imgBox.classList.remove('focus')
  })
  Doc.bind(page.imgPrompt, 'paste', e => {
    working(true)
    e.preventDefault()
    const items = e.clipboardData.items
    for (const item of items) {
      if (item.kind === 'file') {
        imgFile = item.getAsFile()
        processImg(item.getAsFile())
        return
      }
    }
    working(false)
  })

  Doc.bind(page.keyVizToggle, 'click', () => {
    const t = page.keyVizMsg.textContent
    if (t === KeyHiddenText) {
      page.keyVizMsg.textContent = KeyVizText
      page.keyEye.classList.add('ico-eye-closed')
      page.keyEye.classList.remove('ico-eye-open')
      Doc.show(page.gameKey)
    } else {
      page.keyVizMsg.textContent = KeyHiddenText
      page.keyEye.classList.remove('ico-eye-closed')
      page.keyEye.classList.add('ico-eye-open')
      Doc.hide(page.gameKey)
    }
  })

  Doc.bind(page.keySaveBttn, 'click', () => {
    const a = document.createElement('a')
    a.href = `data:application/octet-stream,${encodeURIComponent(gameData.gameKey)}`
    a.download = `${gameData.address}.gamekey`
    document.body.appendChild(a)
    a.click()
    setTimeout(() => { 
      document.body.removeChild(a)
     }, 0)
  })
  
  Doc.bind(page.doneBttn, 'click', () => { window.location = `/challenge/${gameData.address}` })

  Doc.bind(page.submitSolution, 'click', async () => {
    page.solutionErr.textContent = ''
    const prompt = page.prompt.value.trim()
    if (!prompt) {
      page.promptErr.textContent = 'prompt cannot be empty'
      return
    }
    if (prompt.length > 1e4) {
      page.promptErr.textContent = 'prompt cannot be > 10,000 characters'
      return
    }
    const solutionStr = page.solution.value
    if (!solutionStr) {
      page.solutionErr.textContent = 'solution cannot be empty'
      return
    }

    const solution = encodeUTF8(solutionStr)
    const solutionHash = await sha256(solution)
    const doubleHash = await sha256(solutionHash)

    const nonce = new Uint8Array(16)
    window.crypto.getRandomValues(nonce)

    const noncedHash = new Uint8Array(solution.length + 16)
    noncedHash.set(nonce, 0)
    noncedHash.set(solution, 16)

    const proof = await sha256(noncedHash)

    const formData = new FormData()
    formData.append('doubleHash', bytesToHex(doubleHash))
    formData.append('prompt', prompt)
    formData.append('nonce', bytesToHex(nonce))
    formData.append('proof', bytesToHex(proof))

    if (imgFile) {
      formData.append('img', imgFile)
    }

    Doc.show(page.keyBlocker, page.keyWaiting)

    const resp = await postForm('/api/contract', formData)
    Doc.hide(page.keyWaiting)
    if (!checkResponse(resp)) {
      Doc.hide(page.keyBlocker, page.keyWaiting)
      alert("error submitting challenge")
      return
    }

    gameData = resp.payload
    page.gameKey.textContent = gameData.gameKey
    page.keyAddr.textContent = gameData.address
  })

  ws = new MessageSocket(`ws`, msg => {
    if (gameData && msg.event === 'addr' && msg.addr === gameData.address) {
      page.liveFunds.textContent = msg.fmtVal
    }
  })
}

run()
const numToFetch = 5

function offset (el) {
  const rect = el.getBoundingClientRect()
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop
  return { top: rect.top + scrollTop, left: rect.left + scrollLeft }
}

async function run () {
  const page = this.page = Doc.parsePage(document, [
    'challengeColumn', 'challengeTmpl', 'flagNo', 'flagYes', 'blocker',
    'report', 'flagReason', 'noMo', 'loadingMo'
  ])
  
  delete page.challengeTmpl.id
  page.challengeTmpl.remove()
  Doc.show(page.challengeTmpl)

  const resp = await getJSON('/api/live-challenge-index')
  if (!checkResponse(resp)) {
    console.error('error retrieving scored challenges', resp)
    return
  }
  const challengeList = resp.payload
  const challengeDivs = {}
  var nextIndex = 0
  var flagging

  unblock = () => {
    Doc.hide(page.blocker, page.report)
  }
  
  Doc.bind(page.flagNo, 'click', unblock)
  
  Doc.bind(page.flagYes, 'click', async () => { 
    unblock()
    // Don't wait and ignore errors here. Will see them server-side.
    postJSON("/api/flag", {
        "addr": flagging.addr,
        "reason": page.flagReason.value,
    })
    page.flagReason.value = ''
    await Doc.animate(2000, progress => {
        flagging.div.style.opacity = 1 - progress
    })
    flagging.div.remove()

  })

  var allOut = false

  fetchSome = async () => {
    if (nextIndex >= challengeList.length) return
    const batch = challengeList.slice(nextIndex, nextIndex + numToFetch)
    nextIndex += batch.length
    if (nextIndex === challengeList.length) {
        allOut = true
    }
    const resp = await postJSON('/api/challenges', {
      challenges: batch,
    })

    if (!checkResponse(resp)) {
      console.error('error retrieving challenges', resp)
      return
    }

    console.log("--resp", resp)

    const challenges = resp.payload
    for (const ch of challenges) {
      const div = page.challengeTmpl.cloneNode(true)
      challengeDivs[ch.addr] = div
      const set = (k, v) => Doc.tmplElement(div, k).textContent = v
      const challengeHref = `/challenge/${ch.addr}`
      Doc.tmplElement(div, 'headerLink').href = challengeHref
      set('val', ch.fmtVal)
      set('addr', ch.addr)
      // The truncated prompt is html-escaped already, so textContent will
      // re-escape some of our escape characters. Have to use innerHTML.
      Doc.tmplElement(div, 'prompt').innerHTML = ch.truncatedPrompt
      if (ch.imgPath) {
        const imgWrap = Doc.tmplElement(div, 'imgWrap')
        imgWrap.href = challengeHref
        Doc.show(imgWrap)
        Doc.tmplElement(div, 'img').src = `/static/img/uu/${ch.imgPath}`
      }
      set('datetime', new Date(ch.registerTime * 1000).toLocaleString())
      Doc.bind(Doc.tmplElement(div, 'flag'), 'click', () => {
        flagging = {
            addr: ch.addr,
            div: div,
        }
        Doc.show(page.blocker, page.report)
      })
      page.challengeColumn.appendChild(div)
    }
  }

  fetchSome()

  var loading = false
  Doc.bind(document, 'scroll', async () => {
    if (allOut) {
        Doc.show(page.noMo)
        return
    }
    if (loading) return
    Doc.show(page.loadingMo)
    const rect = page.challengeColumn.getBoundingClientRect()
    const scrollTop = window.pageYOffset + rect.top
    const challengesBottom = scrollTop + page.challengeColumn.offsetHeight
    const windowBottom = document.body.scrollTop + document.body.offsetHeight
    if (windowBottom >= challengesBottom) {
      loading = true
      await fetchSome()
      loading = false
    }
    Doc.hide(page.loadingMo)
  })

  url = new URL(window.location)
  ws = new MessageSocket(`ws://${url.host}/ws`, msg => {
    if (msg.event === 'addr') {
      const div = challengeDivs[msg.addr]
      if (!div) return
      if (msg.funds === 0) {
        Doc.show(div.querySelector('.solved'))
      } else {
          Doc.tmplElement(div, 'val').textContent = msg.fmtVal
      }
    }
  })

}

run()

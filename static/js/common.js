const parser = new window.DOMParser()

const FPS = 30

// Parameters for printing asset values.
const fullPrecisionSpecs = {
  minimumSignificantDigits: 4,
  maximumSignificantDigits: 8,
  minimumFractionDigits: 8,
  maximumFractionDigits: 8
}

// Helpers for working with the DOM.
class Doc {
  /*
   * idel is the element with the specified id that is the descendent of the
   * specified node.
   */
  static idel (el, id) {
    return el.querySelector(`#${id}`)
  }

  /* bind binds the function to the event for the element. */
  static bind (el, ev, f) {
    el.addEventListener(ev, f)
  }

  /* unbind removes the handler for the event from the element. */
  static unbind (el, ev, f) {
    el.removeEventListener(ev, f)
  }

  /* noderize creates a Document object from a string of HTML. */
  static noderize (html) {
    return parser.parseFromString(html, 'text/html')
  }

  /*
   * mouseInElement returns true if the position of mouse event, e, is within
   * the bounds of the specified element.
   */
  static mouseInElement (e, el) {
    const rect = el.getBoundingClientRect()
    return e.pageX >= rect.left && e.pageX <= rect.right &&
      e.pageY >= rect.top && e.pageY <= rect.bottom
  }

  /*
   * layoutMetrics gets information about the elements position on the page.
   */
  static layoutMetrics (el) {
    var box = el.getBoundingClientRect()
    var docEl = document.documentElement
    const top = box.top + docEl.scrollTop
    const left = box.left + docEl.scrollLeft
    const w = el.offsetWidth
    const h = el.offsetHeight
    return {
      bodyTop: top,
      bodyLeft: left,
      width: w,
      height: h,
      centerX: left + w / 2,
      centerY: top + h / 2
    }
  }

  /* empty removes all child nodes from the specified element. */
  static empty (el) {
    while (el.firstChild) el.removeChild(el.firstChild)
  }

  /*
   * hide hides the specified elements. This is accomplished by adding the
   * bootstrap d-hide class to the element. Use Doc.show to undo.
   */
  static hide (...els) {
    for (const el of els) el.classList.add('d-hide')
  }

  /*
   * show shows the specified elements. This is accomplished by removing the
   * bootstrap d-hide class as added with Doc.hide.
   */
  static show (...els) {
    for (const el of els) el.classList.remove('d-hide')
  }

  /* isHidden returns true if the specified element is hidden */
  static isHidden (el) {
    return el.classList.contains('d-hide')
  }

  /*
   * animate runs the supplied function, which should be a "progress" function
   * accepting one argument. The progress function will be called repeatedly
   * with the argument varying from 0.0 to 1.0. The exact path that animate
   * takes from 0.0 to 1.0 will vary depending on the choice of easing
   * algorithm. See the Easing object for the available easing algo choices. The
   * default easing algorithm is linear.
   */
  static async animate (duration, f, easingAlgo) {
    const easer = easingAlgo ? Easing[easingAlgo] : Easing.linear
    const start = new Date().getTime()
    const end = start + duration
    const range = end - start
    const frameDuration = 1000 / FPS
    var now = start
    while (now < end) {
      f(easer((now - start) / range))
      await sleep(frameDuration)
      now = new Date().getTime()
    }
    f(1)
  }

  /*
   * parsePage constructs a page object from the supplied list of id strings.
   * The properties of the returned object have names matching the supplied
   * id strings, with the corresponding value being the Element object. It is
   * not an error if an element does not exist for an id in the list.
   */
  static parsePage (main, ids) {
    const get = s => Doc.idel(main, s)
    const page = {}
    ids.forEach(id => { page[id] = get(id) })
    return page
  }

  // formatCoinValue formats the asset value to a string.
  static formatCoinValue (x) {
    var [whole, frac] = x.toLocaleString('en-us', fullPrecisionSpecs).split('.')
    // toLocalString gives precedence to minimumSignificantDigits, so the result
    // can have no fractional part, despite the minimumFractionDigits setting.
    if (!frac) return whole
    // ... or it can have more than 8 fractional digits, despite of the
    // maximumFractionDigits setting.
    frac = frac.substring(0, 8)
    if (frac === '00000000') return whole
    // Trim trailing zeros.
    return `${whole}.${frac.replace(/,+$/, '')}`
  }

  /*
  * tmplElement is a helper function for grabbing sub-elements of the market list
  * template.
  */
  static tmplElement (ancestor, s) {
    return ancestor.querySelector(`[data-tmpl="${s}"]`)
  }

  /*
   * timeSince returns a string representation of the duration since the specified
   * unix timestamp.
   */
  static timeSince (t) {
    var seconds = Math.floor(((new Date().getTime()) - t))
    var result = ''
    var count = 0
    const add = (n, s) => {
      if (n > 0 || count > 0) count++
      if (n > 0) result += `${n} ${s} `
      return count >= 2
    }
    var y, mo, d, h, m, s
    [y, seconds] = timeMod(seconds, aYear)
    if (add(y, 'y')) { return result }
    [mo, seconds] = timeMod(seconds, aMonth)
    if (add(mo, 'mo')) { return result }
    [d, seconds] = timeMod(seconds, aDay)
    if (add(d, 'd')) { return result }
    [h, seconds] = timeMod(seconds, anHour)
    if (add(h, 'h')) { return result }
    [m, seconds] = timeMod(seconds, aMinute)
    if (add(m, 'm')) { return result }
    [s, seconds] = timeMod(seconds, 1000)
    add(s, 's')
    return result || '0 s'
  }

  /*
   * disableMouseWheel can be used to disable the mouse wheel for any
   * input. It is very easy to unknowingly scroll up on a number input
   * and then submit an unexpected value. This function prevents the
   * scroll increment/decrement behavior for a wheel action on a
   * number input.
   */
  static disableMouseWheel (...inputFields) {
    for (const inputField of inputFields) {
      inputField.addEventListener('wheel', (ev) => {
        ev.preventDefault()
      })
    }
  }
}

/* Easing algorithms for animations. */
var Easing = {
  linear: t => t,
  easeIn: t => t * t,
  easeOut: t => t * (2 - t),
  easeInHard: t => t * t * t,
  easeOutHard: t => (--t) * t * t + 1
}

/* sleep can be used by async functions to pause for a specified period. */
function sleep (ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

const aYear = 31536000000
const aMonth = 2592000000
const aDay = 86400000
const anHour = 3600000
const aMinute = 60000

/* timeMod returns the quotient and remainder of t / dur. */
function timeMod (t, dur) {
  const n = Math.floor(t / dur)
  return [n, t - n * dur]
}

// State is a set of static methods for working with the user state. It has
// utilities for setting and retrieving cookies and storing user configuration
// to localStorage.
class State {
  static setCookie (cname, cvalue) {
    var d = new Date()
    // Set cookie to expire in ten years.
    d.setTime(d.getTime() + (86400 * 365 * 10 * 1000))
    var expires = 'expires=' + d.toUTCString()
    document.cookie = cname + '=' + cvalue + ';' + expires + ';path=/'
  }

  /*
   * getCookie returns the value at the specified cookie name, otherwise null.
   */
  static getCookie (cname) {
    for (const cstr of document.cookie.split(';')) {
      const [k, v] = cstr.split('=')
      if (k.trim() === cname) return v
    }
    return null
  }

  /* store puts the key-value pair into Window.localStorage. */
  static store (k, v) {
    window.localStorage.setItem(k, JSON.stringify(v))
  }

  /* clearAllStore remove all the key-value pair in Window.localStorage. */
  static clearAllStore () {
    window.localStorage.clear()
  }
    
  /* fetch fetches the value associated with the key in Window.localStorage, or
   * null if the no value exists for the key.
   */
  static fetch (k) {
    const v = window.localStorage.getItem(k)
    if (v !== null) {
      return JSON.parse(v)
    }
    return null
  }
}


const jsonHeaders = new window.Headers({ 'content-type': 'application/json' })

/*
 * requestJSON encodes the object and sends the JSON to the specified address.
 */
async function requestJSON (method, addr, reqBody, headers) {
  try {
    const req = { 
      method: method,
      credentials: 'same-origin'
    }
    if (reqBody) req.body = reqBody
    req.headers = headers || new window.Headers({})
    const response = await window.fetch(addr, req)
    if (response.status !== 200) { throw response }
    const body = await response.text()
    var resp
    try {
      resp = JSON.parse(body)
    } catch {
      console.error(`json parse error, body = ${body}`)
      throw {ok: false}
    }
    resp.requestSuccessful = true
    return resp
  } catch (response) {
    response.requestSuccessful = false
    if (typeof response.text === 'function') {
      response.msg = await response.text()
    } else {
      console.error("json decode error:", response)
      console.msg = "invalid json"
    }    
    return response
  }
}
  
/*
* postJSON sends a POST request with JSON-formatted data and returns the
* response.
*/
async function postJSON (addr, data) {
  return requestJSON('POST', addr, JSON.stringify(data), jsonHeaders)
}
  
/*
* getJSON sends a GET request and returns the response.
*/
async function getJSON (addr) {
  return requestJSON('GET', addr, null, jsonHeaders)
}

/*
* postForm sends a PUT request with formatted data and returns the response.
*/
async function postForm (addr, formData) {
    return requestJSON('POST', addr, formData)
  }

/*
* checkResponse checks the response object as returned from the functions in
* the http module. If the response indicates that the request failed, a
* message will be displayed in the drop-down notifications and false will be
* returned.
*/
function checkResponse (resp, skipNote) {
  if (!resp.requestSuccessful || !resp.ok) {
    console.error("bad response: ", resp)
    return false
  }
  return true
}

class MessageSocket {
  constructor (path, recv, reconnect) {
    const url = new URL(window.location)
    const proto = url.protocol === 'https:' ? 'wss:' : 'ws:'
    this.uri = `${proto}//${url.host}/${path}`
    this.recv = recv
    this.reconnect = reconnect
    this.ws = undefined
    this.queue = []
    this.connect()
  }

  // send a message
  send (msg) {
    if (!this.ws || this.ws.readyState !== window.WebSocket.OPEN) {
      while (this.queue.length > this.maxQlength - 1) this.queue.shift()
      this.queue.push(msg)
      return
    }

    this.ws.send(message)
  }

  close (reason) {
    this.ws.close()
  }

  connect () {
    var retrys = 0
    const go = () => {
      var conn = this.ws = new window.WebSocket(this.uri)
      var timeout = setTimeout(() => {
        // readyState is still WebSocket.CONNECTING. Cancel and trigger onclose.
        conn.close()
      }, 500)

      // unmarshal message, and forward the message to registered handlers
      conn.onmessage = (evt) => {
        console.log(evt.data)
        this.recv(JSON.parse(evt.data))
        
      }

      // Stub out standard functions
      conn.onclose = (evt) => {
        clearTimeout(timeout)
        conn = this.ws = null
        retrys++
        // 1.2, 1.6, 2.0, 2.4, 3.1, 3.8, 4.8, 6.0, 7.5, 9.3, ...
        const delay = Math.min(Math.pow(1.25, retrys), 10)
        console.error(`websocket disconnected (${evt.code}), trying again in ${delay.toFixed(1)} seconds`)
        setTimeout(() => {
          go()
        }, delay * 1000)
      }

      conn.onopen = () => {
        clearTimeout(timeout)
        if (retrys > 0) {
          retrys = 0
          if (this.reconnect) this.reconnect()
        }
        while (this.queue.length) {
          const msg = this.queue.shift()
          this.send(msg)
        }
      }

      conn.onerror = (evt) => {
        console.error('websocket error:', evt)
      }
    }
    go()
  }
}

function encodeUTF8(s) {
  return new TextEncoder('utf-8').encode(s)
}

async function hashString (s) {
  return await sha256(new TextEncoder('utf-8').encode(s))
}

function hexToBytes (hex) {
  return new Uint8Array(hex.match(/.{1,2}/g).map(byte => parseInt(byte, 16)))
}

function bytesToHex (b) {
  return Array.from(b, byte => {
    return ('0' + (byte & 0xFF).toString(16)).slice(-2)
  }).join('')
}

async function sha256 (b) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', b))
}

function bytesAreEqual (b1, b2) {
  return b1.length === b2.length && b1.every((v, i) => v === b2[i])
}
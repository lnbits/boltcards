const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const {webcrypto} = require('node:crypto')

let options
const requests = []
const copied = []
const errors = []
const exportedFiles = []
const confirmations = []
const card = {
  id: 'card',
  enable: true,
  wallet: 'wallet',
  otp: 'otp',
  uid: 'uid',
  k0: 'old-k0',
  k1: 'old-k1',
  k2: 'old-k2'
}
let storedCard = {...card}
let failWipe = false
let failRefresh = false
let loseWipeResponse = false
let failRefreshAfterWipe = false
let holdWipe = false
let finishWipe
vm.runInNewContext(fs.readFileSync('static/js/index.js', 'utf8'), {
  window: {location: {origin: 'https://cards.example', host: 'cards.example'}},
  windowMixin: {},
  Vue: {
    createApp: value => {
      options = value
      return value
    }
  },
  Quasar: {
    date: {formatDate: () => 'date'},
    exportFile: (...args) => exportedFiles.push(args)
  },
  _: {
    findWhere: (items, fields) =>
      items.find(item =>
        Object.entries(fields).every(([key, value]) => item[key] === value)
      )
  },
  crypto: webcrypto,
  LNbits: {
    api: {
      request: async (...args) => {
        requests.push(args)
        if (args[0] === 'POST' && failWipe)
          throw new Error('network unavailable')
        if (args[0] === 'POST' && holdWipe)
          await new Promise(resolve => {
            finishWipe = resolve
          })
        if (args[0] === 'POST') {
          storedCard = {...storedCard, enable: false, k0: '', k1: '', k2: ''}
          if (loseWipeResponse) throw new Error('response lost')
          if (failRefreshAfterWipe) failRefresh = true
        }
        if (args[0] === 'GET' && args[1].includes('/cards') && failRefresh)
          throw new Error('refresh unavailable')
        return {data: args[1].includes('/cards') ? [{...storedCard}] : []}
      }
    },
    utils: {
      notifyApiError: error => errors.push(error),
      confirmDialog: message => {
        confirmations.push(message)
        return {onOk: () => {}}
      }
    }
  }
})
const app = Object.assign(options.data(), options.methods, {
  g: {user: {wallets: [{id: 'wallet', adminkey: 'admin', inkey: 'invoice'}]}},
  getHits: () => {},
  copyText: value => copied.push(value)
})

async function main() {
  await app.openQrCodeDialog('card', true)
  assert.equal(requests[0][2], 'admin')
  assert.equal(
    requests.some(([method]) => method === 'POST'),
    false
  )
  assert.equal(app.qrCodeDialog.data_wipe, null)
  assert.equal(app.qrCodeDialog.data.k0, card.k0)
  assert.match(
    options.computed.deeplinkUrl.call(app),
    /^boltcard:\/\/reset\?url=/
  )
  await options.methods.getHits.call(app)
  assert.equal(requests.find(([, url]) => url.includes('/hits'))[2], 'admin')
  await options.methods.getRefunds.call(app)
  assert.equal(requests.find(([, url]) => url.includes('/refunds'))[2], 'admin')
  app.deleteCard('card')
  assert.equal(exportedFiles.length, 0)
  assert.equal(confirmations.length, 0)

  failWipe = true
  await app.prepareWipe()
  assert.equal(errors.length, 1)
  assert.equal(JSON.parse(app.qrCodeDialog.data_wipe).k0, card.k0)
  assert.equal(app.qrCodeDialog.data.k0, card.k0)
  assert.equal(copied.length, 1)
  assert.equal(app.qrCodeDialog.wiping, false)
  assert.equal(app.qrCodeDialog.wipePrepared, false)
  app.deleteCard('card')
  assert.equal(exportedFiles.length, 0)
  const failedPosts = requests.filter(([method]) => method === 'POST').length
  await app.prepareWipe()
  assert.equal(
    requests.filter(([method]) => method === 'POST').length,
    failedPosts + 1
  )
  assert.equal(copied[1], copied[0])

  failWipe = false
  await app.prepareWipe()
  assert.equal(app.qrCodeDialog.wipePrepared, true)
  assert.equal(JSON.parse(app.qrCodeDialog.data_wipe).k0, card.k0)
  storedCard = {...card}
  await app.openQrCodeDialog('card', true)
  holdWipe = true
  const pending = app.prepareWipe()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(app.qrCodeDialog.wiping, true)
  const pendingCopies = copied.length
  const pendingPosts = requests.filter(([method]) => method === 'POST').length
  await app.prepareWipe()
  assert.equal(
    requests.filter(([method]) => method === 'POST').length,
    pendingPosts
  )
  assert.equal(copied.length, pendingCopies)
  app.deleteCard('card')
  assert.equal(exportedFiles.length, 0)
  finishWipe()
  await pending
  assert.equal(app.qrCodeDialog.wiping, false)
  assert.equal(errors.length, 2)
  const wipe = JSON.parse(copied[0])
  assert.equal(wipe.action, 'wipe')
  assert.equal(wipe.k0, card.k0)
  assert.equal(wipe.k1, card.k1)
  assert.equal(
    requests.find(([method]) => method === 'POST')[1],
    'https://cards.example/boltcards/api/v1/auth?a=otp&wipe=true'
  )
  const posts = requests.filter(([method]) => method === 'POST').length
  await app.prepareWipe()
  assert.equal(requests.filter(([method]) => method === 'POST').length, posts)
  app.deleteCard('card')
  assert.equal(exportedFiles.length, 1)
  assert.equal(exportedFiles[0][1], app.qrCodeDialog.data_wipe)
  assert.equal(confirmations.length, 1)

  holdWipe = false
  storedCard = {...card}
  await app.openQrCodeDialog('card', true)
  loseWipeResponse = true
  await app.prepareWipe()
  assert.equal(app.qrCodeDialog.wipePrepared, false)
  const lostResponsePosts = requests.filter(
    ([method]) => method === 'POST'
  ).length
  loseWipeResponse = false
  await app.prepareWipe()
  assert.equal(app.qrCodeDialog.wipePrepared, true)
  assert.equal(
    requests.filter(([method]) => method === 'POST').length,
    lostResponsePosts
  )
  assert.equal(JSON.parse(app.qrCodeDialog.data_wipe).k0, card.k0)

  storedCard = {...card}
  await app.openQrCodeDialog('card', true)
  failRefreshAfterWipe = true
  await app.prepareWipe()
  assert.equal(errors.at(-1).message, 'refresh unavailable')
  assert.equal(app.qrCodeDialog.wipePrepared, true)
  assert.equal(app.qrCodeDialog.wiping, false)
  assert.equal(JSON.parse(app.qrCodeDialog.data_wipe).k0, card.k0)

  app.cardDialog.data.card_name = 'debug card'
  app.generateKeys()
  assert.match(app.cardDialog.data.k1, /^[0-9a-f]{32}$/)
  assert.notEqual(app.cardDialog.data.k1, '2'.repeat(32))
  console.log('Card UI checks passed')
}
main().catch(error => {
  console.error(error)
  process.exitCode = 1
})

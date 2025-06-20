const mapCards = obj => {
  obj.date = Quasar.date.formatDate(new Date(obj.time), 'YYYY-MM-DD HH:mm')
  return obj
}

window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  data() {
    return {
      toggleAdvanced: false,
      disableNfcButton: true,
      lnurlLink: `${window.location.host}/boltcards/api/v1/scan/`,
      cards: [],
      hits: [],
      refunds: [],
      cardDialog: {
        show: false,
        data: {
          counter: 1,
          k0: '',
          k1: '',
          k2: '',
          uid: '',
          card_name: ''
        },
        temp: {}
      },
      cardsTable: {
        columns: [
          {
            name: 'card_name',
            align: 'left',
            label: 'Card name',
            field: 'card_name'
          },
          {
            name: 'counter',
            align: 'left',
            label: 'Counter',
            field: 'counter'
          },
          {
            name: 'wallet',
            align: 'left',
            label: 'Wallet',
            field: 'wallet'
          },
          {
            name: 'tx_limit',
            align: 'left',
            label: 'Max tx',
            field: 'tx_limit'
          },
          {
            name: 'daily_limit',
            align: 'left',
            label: 'Daily tx limit',
            field: 'daily_limit'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      refundsTable: {
        columns: [
          {
            name: 'hit_id',
            align: 'left',
            label: 'Hit ID',
            field: 'hit_id'
          },
          {
            name: 'refund_amount',
            align: 'left',
            label: 'Refund Amount',
            field: 'refund_amount'
          },
          {
            name: 'date',
            align: 'left',
            label: 'Time',
            field: 'date'
          }
        ],
        pagination: {
          rowsPerPage: 10,
          sortBy: 'date',
          descending: true
        }
      },
      hitsTable: {
        columns: [
          {
            name: 'card_name',
            align: 'left',
            label: 'Card name',
            field: 'card_name'
          },
          {
            name: 'amount',
            align: 'left',
            label: 'Amount',
            field: 'amount'
          },
          {
            name: 'old_ctr',
            align: 'left',
            label: 'Old counter',
            field: 'old_ctr'
          },
          {
            name: 'new_ctr',
            align: 'left',
            label: 'New counter',
            field: 'new_ctr'
          },
          {
            name: 'date',
            align: 'left',
            label: 'Time',
            field: 'date'
          },
          {
            name: 'ip',
            align: 'left',
            label: 'IP',
            field: 'ip'
          },
          {
            name: 'useragent',
            align: 'left',
            label: 'User agent',
            field: 'useragent'
          }
        ],
        pagination: {
          rowsPerPage: 10,
          sortBy: 'date',
          descending: true
        }
      },
      qrCodeDialog: {
        show: false,
        wipe: false,
        data: null
      }
    }
  },
  computed: {
    deeplinkUrl() {
      const baseUrl = `boltcard://${this.qrCodeDialog.wipe ? 'reset' : 'program'}`
      const url =
        this.qrCodeDialog.data.link +
        (this.qrCodeDialog.wipe ? '&wipe=true' : '')
      return `${baseUrl}?url=${encodeURIComponent(url)}`
    }
  },
  methods: {
    readNfcTag() {
      const ndef = new NDEFReader()
      const readerAbortController = new AbortController()
      readerAbortController.signal.onabort = event => {
        console.log('All NFC Read operations have been aborted.')
      }

      Quasar.Notify.create({
        message: 'Tap your NFC tag to copy its UID here.'
      })

      return ndef.scan({signal: readerAbortController.signal}).then(() => {
        ndef.onreadingerror = () => {
          this.disableNfcButton = false
          Quasar.Notify.create({
            type: 'negative',
            message: 'There was an error reading this NFC tag.'
          })
          readerAbortController.abort()
        }

        ndef.onreading = ({message, serialNumber}) => {
          const uid = serialNumber.toUpperCase().replaceAll(':', '')
          //Decode NDEF data from tag
          this.cardDialog.data.uid = uid
          Quasar.Notify.create({
            type: 'positive',
            message: 'NFC tag read successfully.'
          })
        }
      })
    },
    getCards() {
      LNbits.api
        .request(
          'GET',
          '/boltcards/api/v1/cards?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.cards = response.data.map(function (obj) {
            return mapCards(obj)
          })
        })
        .then(() => {
          this.getHits()
        })
    },
    getHits() {
      LNbits.api
        .request(
          'GET',
          '/boltcards/api/v1/hits?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.hits = response.data.map(obj => {
            obj.card_name = this.cards.find(d => d.id == obj.card_id).card_name
            return mapCards(obj)
          })
        })
    },
    getRefunds() {
      LNbits.api
        .request(
          'GET',
          '/boltcards/api/v1/refunds?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.refunds = response.data.map(obj => {
            return mapCards(obj)
          })
        })
    },
    openQrCodeDialog(cardId, wipe) {
      var card = _.findWhere(this.cards, {id: cardId})
      this.qrCodeDialog.data = {
        id: card.id,
        link: window.location.origin + '/boltcards/api/v1/auth?a=' + card.otp,
        encodedURI: encodeURIComponent(
          window.location.origin + '/boltcards/api/v1/auth?a=' + card.otp
        ),
        name: card.card_name,
        uid: card.uid,
        external_id: card.external_id,
        k0: card.k0,
        k1: card.k1,
        k2: card.k2,
        k3: card.k1,
        k4: card.k2
      }
      this.qrCodeDialog.data_wipe = JSON.stringify({
        action: 'wipe',
        k0: card.k0,
        k1: card.k1,
        k2: card.k2,
        k3: card.k1,
        k4: card.k2,
        uid: card.uid,
        version: 1
      })
      this.qrCodeDialog.wipe = wipe
      this.qrCodeDialog.show = true
    },
    addCardOpen() {
      this.cardDialog.show = true
      this.generateKeys()
    },
    generateKeys() {
      const genRandomHexBytes = size =>
        crypto
          .getRandomValues(new Uint8Array(size))
          .reduce((acc, i) => acc + i.toString(16).padStart(2, '0'), '')

      debugcard =
        typeof this.cardDialog.data.card_name === 'string' &&
        this.cardDialog.data.card_name.search('debug') > -1

      this.cardDialog.data.k0 = debugcard
        ? '11111111111111111111111111111111'
        : genRandomHexBytes(16)

      this.cardDialog.data.k1 = debugcard
        ? '22222222222222222222222222222222'
        : genRandomHexBytes(16)

      this.cardDialog.data.k2 = debugcard
        ? '33333333333333333333333333333333'
        : genRandomHexBytes(16)
    },
    closeFormDialog() {
      this.cardDialog.data = {}
    },
    sendFormData() {
      let wallet = _.findWhere(this.g.user.wallets, {
        id: this.cardDialog.data.wallet
      })
      let data = this.cardDialog.data
      if (data.id) {
        this.updateCard(wallet, data)
      } else {
        this.createCard(wallet, data)
      }
    },
    createCard(wallet, data) {
      LNbits.api
        .request('POST', '/boltcards/api/v1/cards', wallet.adminkey, data)
        .then(response => {
          this.cards.push(mapCards(response.data))
          this.cardDialog.show = false
          this.cardDialog.data = {}
        })
        .catch(LNbits.utils.notifyApiError)
    },
    updateCardDialog(formId) {
      var card = _.findWhere(this.cards, {id: formId})
      this.cardDialog.data = _.clone(card)

      this.cardDialog.temp.k0 = this.cardDialog.data.k0
      this.cardDialog.temp.k1 = this.cardDialog.data.k1
      this.cardDialog.temp.k2 = this.cardDialog.data.k2

      this.cardDialog.show = true
    },
    updateCard(wallet, data) {
      if (
        this.cardDialog.temp.k0 != data.k0 ||
        this.cardDialog.temp.k1 != data.k1 ||
        this.cardDialog.temp.k2 != data.k2
      ) {
        data.prev_k0 = this.cardDialog.temp.k0
        data.prev_k1 = this.cardDialog.temp.k1
        data.prev_k2 = this.cardDialog.temp.k2
      }

      LNbits.api
        .request(
          'PUT',
          '/boltcards/api/v1/cards/' + data.id,
          wallet.adminkey,
          data
        )
        .then(response => {
          this.cards = _.reject(this.cards, function (obj) {
            return obj.id == data.id
          })
          this.cards.push(mapCards(response.data))
          this.cardDialog.show = false
          this.cardDialog.data = {}
        })
        .catch(function (error) {
          LNbits.utils.notifyApiError(error)
        })
    },
    enableCard(wallet, card_id, enable) {
      let fullWallet = _.findWhere(this.g.user.wallets, {
        id: wallet
      })
      LNbits.api
        .request(
          'GET',
          '/boltcards/api/v1/cards/enable/' + card_id + '/' + enable,
          fullWallet.adminkey
        )
        .then(response => {
          console.log(response.data)
          this.cards = _.reject(this.cards, function (obj) {
            return obj.id == response.data.id
          })
          this.cards.push(mapCards(response.data))
        })
        .catch(function (error) {
          LNbits.utils.notifyApiError(error)
        })
    },
    deleteCard(cardId) {
      let cards = _.findWhere(this.cards, {id: cardId})

      Quasar.exportFile(
        cards.card_name + '.json',
        this.qrCodeDialog.data_wipe,
        'application/json'
      )

      LNbits.utils
        .confirmDialog(
          "Are you sure you want to delete this card? Without access to the card keys you won't be able to reset them in the future!"
        )
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              '/boltcards/api/v1/cards/' + cardId,
              _.findWhere(this.g.user.wallets, {id: cards.wallet}).adminkey
            )
            .then(response => {
              this.cards = _.reject(this.cards, function (obj) {
                return obj.id == cardId
              })
            })
            .catch(function (error) {
              LNbits.utils.notifyApiError(error)
            })
        })
    },
    exportCardsCSV() {
      LNbits.utils.exportCSV(this.cardsTable.columns, this.cards)
    },
    exportHitsCSV() {
      LNbits.utils.exportCSV(this.hitsTable.columns, this.hits)
    },
    exportRefundsCSV() {
      LNbits.utils.exportCSV(this.refundsTable.columns, this.refunds)
    }
  },
  created() {
    if (this.g.user.wallets.length) {
      this.getCards()
      this.getRefunds()
    }
    try {
      if (typeof NDEFReader == 'undefined') {
        throw {
          toString() {
            return 'NFC not supported on this device or browser.'
          }
        }
      }
      this.disableNfcButton = false
      Quasar.Notify.create({
        type: 'positive',
        message: 'NFC is supported on this device. You can now read NFC tags.'
      })
    } catch (error) {
      Quasar.Notify.create({
        type: 'negative',
        message: error ? error.toString() : 'An unexpected error has occurred.'
      })
    }
  }
})

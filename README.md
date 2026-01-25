<a href="https://lnbits.com" target="_blank" rel="noopener noreferrer">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://i.imgur.com/QE6SIrs.png">
    <img src="https://i.imgur.com/fyKPgVT.png" alt="LNbits" style="width:280px">
  </picture>
</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-success?logo=open-source-initiative&logoColor=white)](./LICENSE)
[![Built for LNbits](https://img.shields.io/badge/Built%20for-LNbits-4D4DFF?logo=lightning&logoColor=white)](https://github.com/lnbits/lnbits)

# Bolt Cards - <small>[LNbits](https://github.com/lnbits/lnbits) extension</small>

<small>For more about LNBits extensions check [this tutorial](https://youtu.be/_sW7miqaXJc)</small>

This extension allows you to link your [Bolt Card](https://github.com/boltcard) on a NXP NTAG424 DNA tag with a LNbits hub that generated new links on each tab which allows a better privacy and security than a static LNURLw that you can also write to a NFC tag (fromon NTAG 213) in the withdraw-extension e.g. for one-time usage as a gift-card.

<a class="text-secondary" href="https://youtu.be/_sW7miqaXJc">Video Tutorial</a>

**Disclaimer:** **_Use this only if you either know what you are doing or are a reckless lightning pioneer.
Only you are responsible for all your sats, cards and other devices. Always backup all your card keys!_**

For the easy way you need:

- an LNbits instance in clearnet
- opened on Android in Chrome browser
- Boltcard extension installed for your LNbits wallet
- [Boltcard NFC Card Creator App](https://github.com/boltcard/bolt-nfc-android-app) from the [Apple-](https://apps.apple.com/us/app/boltcard-nfc-programmer/id6450968873) or [Play-Store](https://play.google.com/store/search?q=bolt+card+nfc+card+creator&c=apps) to write your keys to the tags once they were generated on LNbits

If you want to gift a Boltcard, make sure to [include the following data](https://www.figma.com/proto/OH6aGCxH45vNpKsZ2nD96S/Untitled?node-id=6%3A37&scaling=min-zoom&page-id=0%3A1) in your present, so that the user is able to make full use of it.

**_Always backup all keys that you're trying to write on the card. Without them you may not be able to change them in the future!_**

## Setting the card - Boltcard NFC Card Creator (easy way)

- Add new card in the extension.
  - Set a max sats per transaction. Any transaction greater than this amount will be rejected. This is usually set higher than the funds in the wallet are to prevent accidential withdraws.
  - Set a max sats per day. After the card spends this amount of sats in a day, additional transactions will be rejected.
  - Set a card name. This is just for your reference inside LNbits.
  - Set the card UID. This is the unique identifier of your NFC card and is 7 bytes.
    - If on an Android device with a newish version of Chrome, you can click the icon next to the input and tap your card to autofill this field.
    - Otherwise read it with the Bolt-Card app (Read NFC) and paste it to the field.
  - Advanced Options
    - Card Keys (k0, k1, k2) will be automatically generated if not explicitly set.
      - Set to 16 bytes of 0s (00000000000000000000000000000000) to leave the keys in default (empty) state (this is unsecure).
      - GENERATE KEY button fill the keys randomly.
  - Click CREATE CARD button
- Click the QR code button next to a card to view its details. Backup the keys now! They'll be comfortable in your password manager.
  - Now you can scan the QR code with the Boltcard app (Create Bolt Card -> SCAN QR CODE).
  - Or the "KEYS / AUTH LINK" button to copy the auth URL to the clipboard. Then paste it into the Android app (Create Bolt Card -> PASTE AUTH URL).
- Click WRITE CARD NOW and approach the NFC card to set it up. DO NOT REMOVE THE CARD PREMATURELY!

## Erasing the card - Boltcard NFC Card Creator

Updated for v0.1.9

Since v0.1.2 of Boltcard NFC Card Creator it is possible not only to reset the keys but also to disable the SUN function and do the complete erase so the card can be used again as a static tag (or set as a new Bolt Card, ofc).

- In the Boltcard extension click the QR code button next to a card to view its details and select WIPE
- OR click the red cross icon on the right side to reach the same
- In the Boltcard app (Reset Keys)
  - Click SCAN QR CODE to scan the QR
  - Or click WIPE DATA in LNbits to copy and paste in to the app (PASTE KEY JSON)
- Click RESET CARD NOW and approach the NFC card to erase it. DO NOT REMOVE THE CARD PREMATURELY!
- Now if all is successful the card can be safely deleted from LNbits (but keep the keys backuped anyway; batter safe than brick).

If you somehow find yourself in some non-standard state (for instance only k3 and k4 remains filled after previous unsuccessful reset), then you need to edit the key fields manually (for instance leave k0-k2 to zeroes and provide the right k3 and k4).

## Setting the card (advanced)

A technology called [Secure Unique NFC](https://web.archive.org/web/20220706134959/https://mishka-scan.com/blog/secure-unique-nfc) is utilized in this workflow.

### About the keys

Up to five 16-byte keys can be stored on the card, numbered from 00 to 04. In the empty state they all should be set to zeros (00000000000000000000000000000000). For this extension only two keys need to be set, but for the security reasons all five keys should be changed from default (empty) state. The keys directly needed by this extension are:

- One for encrypting the card UID and the counter (p parameter), let's called it meta key, key #01 or K1.

- One for calculating CMAC (c parameter), let's called it file key, key #02 or K2.

The key #00, K0 (also know as auth key) is used as authentification key. It is not directly needed by this extension, but should be filled in order to write the keys in cooperation with Boltcard NFC Card Creator. In this case also K3 is set to same value as K1 and K4 as K2, so all keys are changed from default values. Keep that in your mind in case you ever need to reset the keys manually.

### The writing process

There's also a more [advanced guide](https://www.whitewolftech.com/articles/payment-card/) to set cards up manually with a card reader connected to your computer.
Writing can also be done (without setting the keys) via the [TagWriter app by NXP](https://play.google.com/store/apps/details?id=com.nxp.nfc.tagwriter) on Android.

The URI should be `lnurlw://YOUR_LNBITS_DOMAIN/boltcards/api/v1/scan/{YOUR_card_external_id}?p=00000000000000000000000000000000&c=0000000000000000`

Then fill up the card parameters in the extension. Card Auth key (K0) can be filled in the extension just for the record. Initical counter can be 0.

- If you don't know the card ID, use NXP TagInfo app to read it first.
- Tap Write tags > New Data Set > Link
- Set URI type to Custom URL
- URL should look like `lnurlw://YOUR_LNBITS_DOMAIN/boltcards/api/v1/scan/{YOUR_card_external_id}?p=00000000000000000000000000000000&c=0000000000000000`
- click Configure mirroring options
- Select Card Type NTAG 424 DNA
- Check Enable SDM Mirroring
- Select SDM Meta Read Access Right to 01
- Check Enable UID Mirroring
- Check Enable Counter Mirroring
- Set SDM Counter Retrieval Key to 0E
- Set PICC Data Offset to immediately after e=
- Set Derivation Key for CMAC Calculation to 00
- Set SDM MAC Input Offset to immediately after c=
- Set SDM MAC Offset to immediately after c=
- Save & Write
- Scan with compatible Wallet

This app afaik cannot change the keys. If you cannot change them any other way, leave them empty in the extension dialog and remember you're not secured. Card Auth key (K0) can be omitted anyway. Initical counter can be 0.

## Powered by LNbits

[LNbits](https://lnbits.com) is a free and open-source lightning accounts system.

[![Visit LNbits Shop](https://img.shields.io/badge/Visit-LNbits%20Shop-7C3AED?logo=shopping-cart&logoColor=white&labelColor=5B21B6)](https://shop.lnbits.com/)
[![Try myLNbits SaaS](https://img.shields.io/badge/Try-myLNbits%20SaaS-2563EB?logo=lightning&logoColor=white&labelColor=1E40AF)](https://my.lnbits.com/login)

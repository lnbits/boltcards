async def m001_initial(db):
    await db.execute(
        """
        CREATE TABLE boltcards.cards (
            id TEXT PRIMARY KEY UNIQUE,
            wallet TEXT NOT NULL,
            card_name TEXT NOT NULL,
            uid TEXT NOT NULL UNIQUE,
            external_id TEXT NOT NULL UNIQUE,
            counter INT NOT NULL DEFAULT 0,
            tx_limit TEXT NOT NULL,
            daily_limit TEXT NOT NULL,
            enable BOOL NOT NULL,
            k0 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            k1 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            k2 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k0 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k1 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k2 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            otp TEXT NOT NULL DEFAULT '',
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    await db.execute(
        f"""
        CREATE TABLE boltcards.hits (
            id TEXT PRIMARY KEY UNIQUE,
            card_id TEXT NOT NULL,
            ip TEXT NOT NULL,
            spent BOOL NOT NULL DEFAULT True,
            useragent TEXT,
            old_ctr INT NOT NULL DEFAULT 0,
            new_ctr INT NOT NULL DEFAULT 0,
            amount {db.big_int} NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    await db.execute(
        f"""
        CREATE TABLE boltcards.refunds (
            id TEXT PRIMARY KEY UNIQUE,
            hit_id TEXT NOT NULL,
            refund_amount {db.big_int} NOT NULL,
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )


async def m002_correct_typing(db):
    await db.execute("ALTER TABLE boltcards.cards RENAME TO cards_m001;")
    await db.execute(
        """
        CREATE TABLE boltcards.cards (
            id TEXT PRIMARY KEY UNIQUE,
            wallet TEXT NOT NULL,
            card_name TEXT NOT NULL,
            uid TEXT NOT NULL UNIQUE,
            external_id TEXT NOT NULL UNIQUE,
            counter INT NOT NULL DEFAULT 0,
            tx_limit INT NOT NULL,
            daily_limit INT NOT NULL,
            enable BOOL NOT NULL,
            k0 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            k1 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            k2 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k0 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k1 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k2 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            otp TEXT NOT NULL DEFAULT '',
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    await db.execute(
        """
        INSERT INTO boltcards.cards (
            id,
            wallet,
            card_name,
            uid,
            external_id,
            counter,
            tx_limit,
            daily_limit,
            enable,
            k0,
            k1,
            k2,
            prev_k0,
            prev_k1,
            prev_k2,
            otp,
            time
        )
        SELECT
            id,
            wallet,
            card_name,
            uid,
            external_id,
            counter,
            CAST(tx_limit AS INT),
            CAST(daily_limit AS INT),
            enable,
            k0,
            k1,
            k2,
            prev_k0,
            prev_k1,
            prev_k2,
            otp,
            time
        FROM boltcards.cards_m001;
    """
    )
    await db.execute("DROP TABLE boltcards.cards_m001;")


async def m003_add_pin(db):
    await db.execute("ALTER TABLE boltcards.cards RENAME TO cards_m002;")
    await db.execute(
        f"""
        CREATE TABLE boltcards.cards (
            id TEXT PRIMARY KEY UNIQUE,
            wallet TEXT NOT NULL,
            card_name TEXT NOT NULL,
            uid TEXT NOT NULL UNIQUE,
            external_id TEXT NOT NULL UNIQUE,
            counter INT NOT NULL DEFAULT 0,
            tx_limit INT NOT NULL,
            daily_limit INT NOT NULL,
            pin_limit INT NOT NULL DEFAULT 0,
            pin_try INT NOT NULL DEFAULT 0,
            pin TEXT NOT NULL DEFAULT '',
            pin_enable BOOL NOT NULL DEFAULT FALSE,
            enable BOOL NOT NULL,
            k0 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            k1 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            k2 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k0 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k1 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            prev_k2 TEXT NOT NULL DEFAULT '00000000000000000000000000000000',
            otp TEXT NOT NULL DEFAULT '',
            time TIMESTAMP NOT NULL DEFAULT """
        + db.timestamp_now
        + """
        );
    """
    )

    await db.execute(
        """
        INSERT INTO boltcards.cards (
            id,
            wallet,
            card_name,
            uid,
            external_id,
            counter,
            tx_limit,
            daily_limit,
            pin_limit,
            pin_try,
            pin,
            pin_enable,
            enable,
            k0,
            k1,
            k2,
            prev_k0,
            prev_k1,
            prev_k2,
            otp,
            time
        )
        SELECT
            id,
            wallet,
            card_name,
            uid,
            external_id,
            counter,
            tx_limit,
            daily_limit,
            0,
            0,
            '',
            FALSE,
            enable,
            k0,
            k1,
            k2,
            prev_k0,
            prev_k1,
            prev_k2,
            otp,
            time
        FROM boltcards.cards_m002;
    """
    )
    await db.execute("DROP TABLE boltcards.cards_m002;")

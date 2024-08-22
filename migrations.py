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

async def m002_add_features(db):
    await db.execute(
        """
        ALTER TABLE boltcards.cards ADD expiration_date TEXT NULL;
    """
    )

async def m003_add_features(db):
    await db.execute(
        """
        ALTER TABLE boltcards.hits ADD payment_hash TEXT NULL;
    """
    )

async def m004_add_features(db):
    await db.execute(
        """
        ALTER TABLE boltcards.cards ADD monthly_limit TEXT NOT NULL DEFAULT 0;
    """
    )

async def m005_add_features(db):
    await db.execute(
        """
        ALTER TABLE boltcards.cards ADD limit_type TEXT NOT NULL DEFAULT 'sats';
    """
    )

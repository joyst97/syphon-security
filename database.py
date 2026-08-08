import sqlite3
import datetime
import logging
from config import DB_PATH

logger = logging.getLogger("AEGIS.Database")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA cache_size = -64000;")
    except Exception:
        pass
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Guild Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id TEXT PRIMARY KEY,
        anti_nuke INTEGER DEFAULT 0,
        anti_raid INTEGER DEFAULT 0,
        anti_invite INTEGER DEFAULT 0,
        anti_spam INTEGER DEFAULT 0,
        anti_mass_mention INTEGER DEFAULT 0,
        verification_enabled INTEGER DEFAULT 0,
        unverified_role_id TEXT DEFAULT NULL,
        verified_role_id TEXT DEFAULT NULL,
        log_channel_id TEXT DEFAULT NULL,
        verification_channel_id TEXT DEFAULT NULL,
        member_counter_channel_id TEXT DEFAULT NULL,
        action_on_nuke TEXT DEFAULT 'quarantine'  -- quarantine, kick, ban
    )
    """)

    try:
        cursor.execute("ALTER TABLE guild_settings ADD COLUMN member_counter_channel_id TEXT DEFAULT NULL")
    except Exception:
        pass

    # Whitelist Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS whitelists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_type TEXT NOT NULL, -- 'user', 'role', 'bot'
        feature TEXT NOT NULL,     -- 'all', 'anti_nuke', 'anti_link', 'anti_spam'
        added_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(guild_id, target_id, feature)
    )
    """)

    # Active Temp-Bans Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tempbans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        user_name TEXT,
        reason TEXT,
        banned_by TEXT,
        unban_timestamp INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1
    )
    """)

    # Warnings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        moderator_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Security Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        action_type TEXT NOT NULL, -- ANTI_NUKE, ANTI_RAID, AUTOMOD, TEMPBAN, LOCKDOWN
        severity TEXT DEFAULT 'MEDIUM', -- LOW, MEDIUM, HIGH, CRITICAL
        culprit_id TEXT,
        culprit_name TEXT,
        details TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Giveaways Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        message_id TEXT NOT NULL UNIQUE,
        prize TEXT NOT NULL,
        winners_count INTEGER DEFAULT 1,
        end_timestamp INTEGER NOT NULL,
        host_id TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        entries TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Support Tickets Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        channel_id TEXT NOT NULL UNIQUE,
        user_id TEXT NOT NULL,
        status TEXT DEFAULT 'open', -- open, closed
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Bad Words Blacklist Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bad_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        word TEXT NOT NULL,
        added_by TEXT DEFAULT 'Admin',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(guild_id, word)
    )
    """)

    # Voice 247 Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS voice_247 (
        guild_id TEXT PRIMARY KEY,
        channel_id TEXT NOT NULL,
        enabled INTEGER DEFAULT 1
    );
    """)

    # Auto TTS Channels Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auto_tts_channels (
        guild_id TEXT PRIMARY KEY,
        text_channel_id TEXT NOT NULL,
        enabled INTEGER DEFAULT 1
    );
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def set_auto_tts_channel_db(guild_id: str, text_channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO auto_tts_channels (guild_id, text_channel_id, enabled) VALUES (?, ?, 1)
    ON CONFLICT(guild_id) DO UPDATE SET text_channel_id = excluded.text_channel_id, enabled = 1
    """, (str(guild_id), str(text_channel_id)))
    conn.commit()
    conn.close()

def remove_auto_tts_channel_db(guild_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM auto_tts_channels WHERE guild_id = ?", (str(guild_id),))
    conn.commit()
    conn.close()

def get_auto_tts_channel_db(guild_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT text_channel_id FROM auto_tts_channels WHERE guild_id = ? AND enabled = 1", (str(guild_id),))
    row = cursor.fetchone()
    conn.close()
    return row["text_channel_id"] if row else None

def set_247_vc_db(guild_id: str, channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO voice_247 (guild_id, channel_id, enabled) VALUES (?, ?, 1)
    ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, enabled = 1
    """, (str(guild_id), str(channel_id)))
    conn.commit()
    conn.close()

def remove_247_vc_db(guild_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM voice_247 WHERE guild_id = ?", (str(guild_id),))
    conn.commit()
    conn.close()

def get_247_vcs_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT guild_id, channel_id FROM voice_247 WHERE enabled = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- RAM Caches for Ultra-High Speed ---
_SETTINGS_CACHE = {}
_WHITELIST_CACHE = {}

def get_guild_settings(guild_id: str):
    gid = str(guild_id)
    if gid in _SETTINGS_CACHE:
        return _SETTINGS_CACHE[gid]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (gid,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO guild_settings (guild_id) VALUES (?)", (gid,))
        conn.commit()
        cursor.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (gid,))
        row = cursor.fetchone()
    conn.close()
    result = dict(row)
    _SETTINGS_CACHE[gid] = result
    return result

def update_guild_setting(guild_id: str, key: str, value):
    gid = str(guild_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM guild_settings WHERE guild_id = ?", (gid,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO guild_settings (guild_id, anti_nuke, anti_raid, anti_invite, anti_spam) VALUES (?, 0, 0, 0, 0)", (gid,))
        conn.commit()

    query = f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?"
    cursor.execute(query, (value, gid))
    conn.commit()
    conn.close()

    # Invalidate RAM cache AFTER database commit!
    _SETTINGS_CACHE.pop(gid, None)

# --- Whitelist Helpers ---

def add_whitelist(guild_id: str, target_id: str, target_type: str, feature: str = 'all', added_by: str = 'System'):
    _WHITELIST_CACHE.pop(str(guild_id), None)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO whitelists (guild_id, target_id, target_type, feature, added_by) VALUES (?, ?, ?, ?, ?)",
            (str(guild_id), str(target_id), target_type, feature, str(added_by))
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding whitelist: {e}")
        return False
    finally:
        conn.close()

def remove_whitelist(guild_id: str, target_id: str, feature: str = 'all'):
    _WHITELIST_CACHE.pop(str(guild_id), None)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM whitelists WHERE guild_id = ? AND target_id = ? AND feature = ?", 
                   (str(guild_id), str(target_id), feature))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def is_whitelisted(guild_id: str, target_id: str, feature: str = 'all', role_ids: list = None, channel_id: str = None):
    gid = str(guild_id)
    cache_key = (gid, str(target_id), feature, tuple(role_ids or []), str(channel_id or ""))
    if gid in _WHITELIST_CACHE and cache_key in _WHITELIST_CACHE[gid]:
        return _WHITELIST_CACHE[gid][cache_key]

    conn = get_connection()
    cursor = conn.cursor()
    result = False

    cursor.execute(
        "SELECT 1 FROM whitelists WHERE guild_id = ? AND target_id = ? AND (feature = 'all' OR feature = ?)",
        (gid, str(target_id), feature)
    )
    if cursor.fetchone():
        result = True

    if not result and channel_id:
        cursor.execute(
            "SELECT 1 FROM whitelists WHERE guild_id = ? AND target_id = ? AND (feature = 'all' OR feature = ?)",
            (gid, str(channel_id), feature)
        )
        if cursor.fetchone():
            result = True

    if not result and role_ids:
        for r_id in role_ids:
            cursor.execute(
                "SELECT 1 FROM whitelists WHERE guild_id = ? AND target_id = ? AND (feature = 'all' OR feature = ?)",
                (gid, str(r_id), feature)
            )
            if cursor.fetchone():
                result = True
                break

    conn.close()
    if gid not in _WHITELIST_CACHE:
        _WHITELIST_CACHE[gid] = {}
    _WHITELIST_CACHE[gid][cache_key] = result
    return result

def get_whitelists(guild_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM whitelists WHERE guild_id = ? ORDER BY created_at DESC", (str(guild_id),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Temp-Ban Helpers ---

def add_tempban(guild_id: str, user_id: str, user_name: str, reason: str, banned_by: str, duration_seconds: int):
    conn = get_connection()
    cursor = conn.cursor()
    unban_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + duration_seconds
    
    cursor.execute(
        "INSERT INTO tempbans (guild_id, user_id, user_name, reason, banned_by, unban_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (str(guild_id), str(user_id), user_name, reason, str(banned_by), unban_time)
    )
    conn.commit()
    conn.close()
    return unban_time

def remove_tempban(guild_id: str, user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tempbans SET active = 0 WHERE guild_id = ? AND user_id = ? AND active = 1",
                   (str(guild_id), str(user_id)))
    conn.commit()
    conn.close()

def get_active_tempbans(guild_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if guild_id:
        cursor.execute("SELECT * FROM tempbans WHERE guild_id = ? AND active = 1 ORDER BY unban_timestamp ASC", (str(guild_id),))
    else:
        cursor.execute("SELECT * FROM tempbans WHERE active = 1 ORDER BY unban_timestamp ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_expired_tempbans(current_timestamp: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tempbans WHERE active = 1 AND unban_timestamp <= ?", (current_timestamp,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Warnings Helpers ---

def add_warning(guild_id: str, user_id: str, reason: str, moderator_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO warnings (guild_id, user_id, reason, moderator_id) VALUES (?, ?, ?, ?)",
        (str(guild_id), str(user_id), reason, str(moderator_id))
    )
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) as count FROM warnings WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
    count = cursor.fetchone()['count']
    conn.close()
    return count

def get_user_warnings(guild_id: str, user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC", 
                   (str(guild_id), str(user_id)))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def clear_warnings(guild_id: str, user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

# --- Audit Logging Helpers ---

def add_audit_log(guild_id: str, action_type: str, details: str, culprit_id: str = None, culprit_name: str = None, severity: str = 'MEDIUM'):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_logs (guild_id, action_type, details, culprit_id, culprit_name, severity) VALUES (?, ?, ?, ?, ?, ?)",
        (str(guild_id), action_type, details, str(culprit_id) if culprit_id else None, culprit_name, severity)
    )
    conn.commit()
    conn.close()

def get_audit_logs(guild_id: str = None, limit: int = 50):
    conn = get_connection()
    cursor = conn.cursor()
    if guild_id:
        cursor.execute("SELECT * FROM audit_logs WHERE guild_id = ? ORDER BY timestamp DESC LIMIT ?", (str(guild_id), limit))
    else:
        cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Giveaway Helpers ---

import json

def add_giveaway_db(guild_id: str, channel_id: str, message_id: str, prize: str, winners_count: int, end_timestamp: int, host_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners_count, end_timestamp, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(guild_id), str(channel_id), str(message_id), prize, int(winners_count), int(end_timestamp), str(host_id))
    )
    conn.commit()
    conn.close()

def get_giveaway_db(message_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM giveaways WHERE message_id = ?", (str(message_id),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_active_giveaways_db(guild_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if guild_id:
        cursor.execute("SELECT * FROM giveaways WHERE guild_id = ? AND active = 1", (str(guild_id),))
    else:
        cursor.execute("SELECT * FROM giveaways WHERE active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def toggle_giveaway_entry_db(message_id: str, user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT entries FROM giveaways WHERE message_id = ?", (str(message_id),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, 0

    entries = json.loads(row["entries"])
    uid = str(user_id)
    entered = False
    if uid in entries:
        entries.remove(uid)
        entered = False
    else:
        entries.append(uid)
        entered = True

    new_entries_str = json.dumps(entries)
    cursor.execute("UPDATE giveaways SET entries = ? WHERE message_id = ?", (new_entries_str, str(message_id)))
    conn.commit()
    conn.close()
    return entered, len(entries)

def end_giveaway_db(message_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE giveaways SET active = 0 WHERE message_id = ?", (str(message_id),))
    conn.commit()
    conn.close()

# --- Bad Words Helpers ---

def add_bad_word(guild_id: str, word: str, added_by: str = 'Admin'):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO bad_words (guild_id, word, added_by) VALUES (?, ?, ?)",
            (str(guild_id), word.strip().lower(), str(added_by))
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding bad word: {e}")
        return False
    finally:
        conn.close()

def remove_bad_word(guild_id: str, word: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bad_words WHERE guild_id = ? AND word = ?", (str(guild_id), word.strip().lower()))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_bad_words(guild_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bad_words WHERE guild_id = ? ORDER BY created_at DESC", (str(guild_id),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Ticket Helpers ---

def add_ticket_db(guild_id: str, user_id: str, channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO tickets (guild_id, user_id, channel_id, status) VALUES (?, ?, ?, 'open')",
            (str(guild_id), str(user_id), str(channel_id))
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding ticket: {e}")
        return False
    finally:
        conn.close()

def get_open_tickets(guild_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if guild_id:
        cursor.execute("SELECT * FROM tickets WHERE guild_id = ? AND status = 'open' ORDER BY created_at DESC", (str(guild_id),))
    else:
        cursor.execute("SELECT * FROM tickets WHERE status = 'open' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def close_ticket_db(channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (str(channel_id),))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()

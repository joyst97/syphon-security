import discord

# Fallback Unicode Emojis
DEFAULT_EMOJIS = {
    "shield": "🛡️",
    "success": "✅",
    "cancel": "✖️",
    "delete": "🧹",
    "warning": "⚠️",
    "danger": "🚨",
    "ban": "🔨",
    "timeout": "🔇",
    "untimeout": "🔊",
    "kick": "👢",
    "purge": "🧹",
    "verify": "🔒",
    "loading": "⏳",
    "bot": "🤖",
    "question": "❓",
    "info": "ℹ️",
    "music": "🎵",
    "bell": "🔔"
}

# Alias keywords mapped directly to your custom server emojis!
KEYWORD_MAP = {
    "shield": ["94046dev", "shield", "joyst_shield", "security", "guard", "protection"],
    "success": ["cb_greentick", "success", "check", "yes", "tick", "confirm", "approved"],
    "cancel": ["purge", "cancel", "cross", "no", "deny", "rejected"],
    "delete": ["purge", "delete", "clear", "trash"],
    "purge": ["purge", "clean", "clear"],
    "warning": ["22593alert", "warning", "warn", "alert", "caution"],
    "danger": ["22593alert", "danger", "alert", "red_alert", "nuke", "emergency"],
    "ban": ["zzz_banned", "ban", "hammer", "tempban", "banned"],
    "timeout": ["sw_timer", "22593alert", "timeout", "mute", "silenced", "muted"],
    "untimeout": ["cb_greentick", "untimeout", "unmute", "speak"],
    "kick": ["zzz_banned", "kick", "boot"],
    "verify": ["94046dev", "verify", "verified", "lock", "shield_check"],
    "loading": ["green_loading", "loading", "spin", "spinner", "wait"],
    "bot": ["bots", "bot", "ai", "robot"],
    "question": ["question1", "question", "help", "think"],
    "info": ["rainymm_info", "info"],
    "music": ["playing_audio", "music", "play", "audio", "song"],
    "play": ["playing_audio", "play"],
    "bell": ["campana", "bell", "notification", "alert"]
}

import re

def parse_custom_emoji_input(input_str: str, guild: discord.Guild = None, client: discord.Client = None) -> str:
    """
    Universal Discord Custom & Animated Emoji Resolver:
    Converts inputs like ':93153verify:', '93153verify', ':verify:', '<a:verify:93153...>'
    automatically into active rendering Discord animated (<a:name:id>) or static (<:name:id>) emojis.
    """
    if not input_str:
        return ""

    text = str(input_str).strip()

    # 1. Already valid Discord emoji syntax
    if re.match(r"^<a?:[a-zA-Z0-9_]+:\d+>$", text):
        return text

    clean_term = text.strip(":").lower()

    # Build search pool of emojis from current guild & client
    search_pool = []
    if guild and hasattr(guild, "emojis"):
        search_pool.extend(list(guild.emojis))
    if client and hasattr(client, "emojis"):
        search_pool.extend(list(client.emojis))

    if search_pool:
        # Match A: Exact Emoji ID if present
        id_match = re.search(r"\d{17,20}", text)
        if id_match:
            target_id = int(id_match.group())
            for emoji in search_pool:
                if emoji.id == target_id:
                    return str(emoji)

        # Match B: Exact Name Match
        for emoji in search_pool:
            if emoji.name.lower() == clean_term:
                return str(emoji)

        # Match C: Partial Name Match (prefers animated emojis)
        for emoji in search_pool:
            if emoji.animated and clean_term in emoji.name.lower():
                return str(emoji)
        for emoji in search_pool:
            if clean_term in emoji.name.lower() or emoji.name.lower() in clean_term:
                return str(emoji)

        # Match D: Strip leading digits (e.g., '93153verify' -> 'verify')
        stripped_term = re.sub(r"^\d+", "", clean_term)
        if stripped_term:
            for emoji in search_pool:
                if emoji.animated and stripped_term in emoji.name.lower():
                    return str(emoji)
            for emoji in search_pool:
                if stripped_term in emoji.name.lower():
                    return str(emoji)

    # 2. Fallback to keyword get_emoji lookup
    fallback = get_emoji(clean_term, guild)
    return fallback if fallback else text

def replace_emoji_tags(text_content: str, guild: discord.Guild = None, client: discord.Client = None) -> str:
    """
    Scans entire paragraphs for ':emoji_name:' or ':93153verify:' tags and replaces them
    with live animated/static custom Discord emojis.
    """
    if not text_content:
        return ""

    def emoji_replacer(match):
        raw_tag = match.group(0)
        resolved = parse_custom_emoji_input(raw_tag, guild, client)
        return resolved if resolved else raw_tag

    # Match anything enclosed in colons like :verify: or :93153verify:
    return re.sub(r":[a-zA-Z0-9_]+:", emoji_replacer, text_content)

def get_emoji(name: str, guild: discord.Guild = None) -> str:
    """Dynamically resolves custom ANIMATED & STATIC server emojis first, falling back to default unicode."""
    key = name.lower()

    if guild and hasattr(guild, "emojis"):
        target_keywords = KEYWORD_MAP.get(key, [key])
        
        # 1. Search for EXACT match or ANIMATED emojis first in the server!
        for kw in target_keywords:
            for emoji in guild.emojis:
                if emoji.name.lower() == kw or (emoji.animated and kw in emoji.name.lower()):
                    return str(emoji)

        # 2. Search for STATIC custom emojis in the server
        for kw in target_keywords:
            for emoji in guild.emojis:
                if kw in emoji.name.lower():
                    return str(emoji)

    # 3. Fallback to standard unicode emoji
    return DEFAULT_EMOJIS.get(key, "🛡️")

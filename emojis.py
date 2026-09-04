import discord
import re

# Clean Direct Animated Discord Emojis Matrix
DEFAULT_EMOJIS = {
    "black_dot": "<a:black_dot:1535579629253951489>",
    "tick": "<a:CB_greentick:1441097547350282260>",
    "success": "<a:CB_greentick:1441097547350282260>",
    "cross_": "<a:redtick:1441097679407943782>",
    "cross": "<a:redtick:1441097679407943782>",
    "cancel": "<a:redtick:1441097679407943782>",
    "redtick": "<a:redtick:1441097679407943782>",
    "shield": "<a:13969niebieskipiorun:1441085314272722959>",
    "antinuke": "<a:13969niebieskipiorun:1441085314272722959>",
    "verify": "<a:CB_greentick:1441097547350282260>",
    "ban": "<a:redtick:1441097679407943782>",
    "kick": "<a:redtick:1441097679407943782>",
    "danger": "<a:22593alert:1441088162976895120>",
    "warning": "<a:22593alert:1441088162976895120>",
    "alert": "<a:22593alert:1441088162976895120>",
    "timeout": "<a:Green_Loading:1534236460163661976>",
    "untimeout": "<a:Green_Loading:1534236460163661976>",
    "delete": "<a:9093settings:1441087243996496079>",
    "purge": "<a:redtick:1441097679407943782>",
    "loading": "<a:Green_Loading:1534236460163661976>",
    "bot": "<a:dev:1528079861283946538>",
    "question": "<a:question1:1534236585456046274>",
    "info": "<a:13969niebieskipiorun:1441085314272722959>",
    "music": "<a:Playing_Audio:1534236884639944705>",
    "play": "<a:Playing_Audio:1534236884639944705>",
    "ticket": "<a:13969niebieskipiorun:1441085314272722959>",
    "giveaway": "<a:Giveaway86:1441323391209570446>",
    "stats": "<a:Green_Loading:1534236460163661976>",
    "wave": "<a:pikachu_wave:1320787117881823252>",
    "pikachu_wave": "<a:pikachu_wave:1320787117881823252>",
    "nut_yes": "<a:CB_greentick:1441097547350282260>",
    "bell": "<a:9093settings:1441087243996496079>",
    "bolt": "<a:13969niebieskipiorun:1441085314272722959>",
    "crown": "<a:86751whitedripheart:1320786130869817526>",
    "owner": "<a:86751whitedripheart:1320786130869817526>",
    "staff": "<a:dev:1528079861283946538>",
    "link": "<a:32877animatedarrowbluelite:1396718513787371530>"
}

def get_emoji(name: str, guild: discord.Guild = None) -> str:
    """Returns exact custom emoji dynamically from guild or bot cache."""
    key = str(name).lower().strip(":")

    # 1. Search current guild emojis first
    if guild and hasattr(guild, "emojis"):
        for e in guild.emojis:
            if e.name.lower() == key:
                return str(e)

    # 2. Search connected bot guilds
    if guild and hasattr(guild, "_state") and hasattr(guild._state, "_get_client"):
        try:
            client = guild._state._get_client()
            if client:
                for g in client.guilds:
                    for e in g.emojis:
                        if e.name.lower() == key:
                            return str(e)
        except Exception:
            pass

    # 3. Fallback to DEFAULT_EMOJIS dictionary
    if key in DEFAULT_EMOJIS:
        return DEFAULT_EMOJIS[key]

    return "•"

def parse_custom_emoji_input(input_str: str, guild: discord.Guild = None, client: discord.Client = None) -> str:
    """Converts inputs like ':verify:' directly into direct animated emoji tags."""
    if not input_str:
        return ""
    text = str(input_str).strip()
    if re.match(r"^<a?:[a-zA-Z0-9_\-]+:\d+>$", text):
        return text
    clean_term = text.strip(":").lower()
    return get_emoji(clean_term, guild)

def replace_emoji_tags(text_content: str, guild: discord.Guild = None, client: discord.Client = None) -> str:
    """Scans text for ':name:' and unicode emojis, converting them to custom server emojis while preserving Discord timestamps and custom animated emojis!"""
    if not text_content:
        return text_content

    # Preserve Discord timestamp tags like <t:1725470000:R> or <t:1725470000:f>
    timestamps = []
    def save_ts(m):
        timestamps.append(m.group(0))
        return f"__DISCORD_TS_{len(timestamps)-1}__"

    res = str(text_content)
    res = re.sub(r"<t:\d+(?::[a-zA-Z])?>", save_ts, res)

    # 1. Convert standard unicode emojis to server custom emojis
    unicode_map = {
        "🛡️": get_emoji("shield", guild),
        "✅": get_emoji("tick", guild),
        "❌": get_emoji("cross_", guild),
        "⚡": get_emoji("bolt", guild),
        "🔒": get_emoji("shield", guild),
        "👑": get_emoji("crown", guild),
        "🤖": get_emoji("bot", guild),
        "💬": get_emoji("question", guild),
        "📢": get_emoji("bell", guild),
    }

    for u_char, c_emoji in unicode_map.items():
        res = res.replace(u_char, c_emoji)

    # 2. Convert :emoji_name: tags
    if ":" in res:
        pattern = r"(?<!<a)(?<!<):([a-zA-Z0-9_\-]+):(?![\d]+>)"
        def _sub_emoji(m):
            tag_name = m.group(1)
            if tag_name.isdigit() or len(tag_name) <= 1:
                return m.group(0)
            emoji_str = get_emoji(tag_name, guild)
            return emoji_str if emoji_str != "•" else m.group(0)
        res = re.sub(pattern, _sub_emoji, res)

    # Restore preserved timestamps
    for i, ts_val in enumerate(timestamps):
        res = res.replace(f"__DISCORD_TS_{i}__", ts_val)

    return res

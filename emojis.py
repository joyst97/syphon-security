import discord
import re

# Clean Direct Animated Discord Emojis Matrix
DEFAULT_EMOJIS = {
    "black_dot": "<a:black_dot:1535579629253951489>",
    "tick": "<a:CB_greentick:1441097547350282260>",
    "success": "<a:CB_greentick:1441097547350282260>",
    "cross_": "<a:Cross_:1535587084952272937>",
    "cross": "<a:Cross_:1535587084952272937>",
    "cancel": "<a:Cross_:1535587084952272937>",
    "redtick": "<a:Cross_:1535587084952272937>",
    "shield": "<:antinuke:1441085562244038708>",
    "antinuke": "<:antinuke:1441085562244038708>",
    "verify": "<:antinuke:1441085562244038708>",
    "ban": "<:zzz_banned:1534236096781619252>",
    "kick": "<:zzz_banned:1534236096781619252>",
    "danger": "<a:22593alert:1441088162976895120>",
    "warning": "<a:22593alert:1441088162976895120>",
    "alert": "<a:22593alert:1441088162976895120>",
    "timeout": "<a:Green_Loading:1534236460163661976>",
    "untimeout": "<a:Green_Loading:1534236460163661976>",
    "delete": "<a:9093settings:1441087243996496079>",
    "purge": "<:Purge:1441105980040548383>",
    "loading": "<a:Green_Loading:1534236460163661976>",
    "bot": "<a:bots:1534236795187888178>",
    "question": "<a:question1:1534236585456046274>",
    "info": "<:RainyMM_info:1534236695854055546>",
    "music": "<a:Playing_Audio:1534236884639944705>",
    "play": "<a:Playing_Audio:1534236884639944705>",
    "ticket": "<:GlacierTicketSupportEmojiForBot:1396426191673626624>",
    "giveaway": "<a:Giveaway86:1441323391209570446>",
    "stats": "<a:Green_Loading:1534236460163661976>",
    "wave": "<a:pikachu_wave:1320787117881823252>",
    "pikachu_wave": "<a:pikachu_wave:1320787117881823252>",
    "nut_yes": "<:nut_yes:1441085461715222670>",
    "bell": "<a:9093settings:1441087243996496079>",
    "bolt": "<a:13969niebieskipiorun:1441085314272722959>",
    "crown": "<:38596ownercrown:1385894350101155923>",
    "owner": "<:owner_gradient:1441090538408382585>",
    "staff": "<:Staff:1385894566271389696>",
    "link": "<:32877animatedarrowbluelite:1396568347537309698>"
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
    """Scans text for ':name:' and unicode emojis, converting them to custom server emojis while keeping existing '<a:name:id>' untouched!"""
    if not text_content:
        return text_content

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

    res = str(text_content)
    for u_char, c_emoji in unicode_map.items():
        res = res.replace(u_char, c_emoji)

    # 2. Convert :emoji_name: tags
    if ":" in res:
        pattern = r"(?<!<a)(?<!<):([a-zA-Z0-9_\-]+):(?![\d]+>)"
        res = re.sub(pattern, lambda m: get_emoji(m.group(1), guild), res)

    return res

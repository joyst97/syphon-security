import discord
import re

# Clean Direct Animated Discord Emojis Matrix
DEFAULT_EMOJIS = {
    "tick": "<a:Green_Loading:1534236460163661976>",
    "success": "<a:Green_Loading:1534236460163661976>",
    "cross": "<a:question1:1534236585456046274>",
    "cancel": "<a:question1:1534236585456046274>",
    "shield": "<a:dev:1528079861283946538>",
    "verify": "<a:dev:1528079861283946538>",
    "ban": "<:zzz_banned:1534236096781619252>",
    "kick": "<:zzz_banned:1534236096781619252>",
    "danger": "<a:dev:1528079861283946538>",
    "warning": "<a:question1:1534236585456046274>",
    "timeout": "<a:Green_Loading:1534236460163661976>",
    "untimeout": "<a:Green_Loading:1534236460163661976>",
    "delete": "<a:settings:1528080056620941362>",
    "purge": "<a:settings:1528080056620941362>",
    "loading": "<a:Green_Loading:1534236460163661976>",
    "bot": "<a:bots:1534236795187888178>",
    "question": "<a:question1:1534236585456046274>",
    "info": "<:RainyMM_info:1534236695854055546>",
    "music": "<a:Playing_Audio:1534236884639944705>",
    "play": "<a:Playing_Audio:1534236884639944705>",
    "ticket": "<a:question1:1534236585456046274>",
    "giveaway": "<a:settings:1528080056620941362>",
    "stats": "<a:Green_Loading:1534236460163661976>",
    "wave": "<a:pikachu_wave:1320787117881823252>",
    "pikachu_wave": "<a:pikachu_wave:1320787117881823252>",
    "nut_yes": "<:nut_yes:1441085461715222670>",
    "bell": "<a:settings:1528080056620941362>",
    "bolt": "<a:Green_Loading:1534236460163661976>"
}

def get_emoji(name: str, guild: discord.Guild = None) -> str:
    """Returns exact animated custom emoji directly without any keyword guesswork."""
    key = str(name).lower().strip(":")
    return DEFAULT_EMOJIS.get(key, "<a:dev:1528079861283946538>")

def parse_custom_emoji_input(input_str: str, guild: discord.Guild = None, client: discord.Client = None) -> str:
    """Converts inputs like ':verify:' directly into direct animated emoji tags."""
    if not input_str:
        return ""
    text = str(input_str).strip()
    if re.match(r"^<a?:[a-zA-Z0-9_\-]+:\d+>$", text):
        return text
    clean_term = text.strip(":").lower()
    return DEFAULT_EMOJIS.get(clean_term, text)

def replace_emoji_tags(text_content: str, guild: discord.Guild = None, client: discord.Client = None) -> str:
    """Scans text for ':name:' or '<a:name:id>' and returns exact animated emojis."""
    if not text_content:
        return ""
    def emoji_replacer(match):
        raw_tag = match.group(0)
        return parse_custom_emoji_input(raw_tag, guild, client)

    text = re.sub(r"<a?:[a-zA-Z0-9_\-]+:\d+>", emoji_replacer, text_content)
    text = re.sub(r":[a-zA-Z0-9_]+:", emoji_replacer, text_content)
    return text

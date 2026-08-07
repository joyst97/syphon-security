import discord
import logging
import database as db
import config
from emojis import get_emoji

logger = logging.getLogger("AEGIS.EmbedBuilder")

# Modern Discord Native Dark Palette (Blends into Discord UI, zero thick border clutter)
COLOR_DARK = discord.Color.from_str("#2b2d31")      # Discord Theme Native Dark
COLOR_BLURPLE = discord.Color.from_str("#5865f2")   # Discord Accent Blurple
COLOR_GREEN = discord.Color.from_str("#57f287")     # Modern Soft Green
COLOR_YELLOW = discord.Color.from_str("#fee75c")    # Modern Soft Gold
COLOR_RED = discord.Color.from_str("#ed4245")       # Modern Soft Crimson

# Aliases
COLOR_BLUE = COLOR_BLURPLE
COLOR_SUCCESS = COLOR_GREEN
COLOR_WARNING = COLOR_YELLOW
COLOR_DANGER = COLOR_RED
COLOR_PURPLE = discord.Color.from_str("#eb459e")
COLOR_INFO = COLOR_BLURPLE

from emojis import get_emoji, replace_emoji_tags

def joyst_embed(
    title: str = None,
    description: str = None,
    color: discord.Color = COLOR_DARK,
    fields: list = None,
    footer: str = None,
    thumbnail: str = None,
    author_name: str = None,
    author_icon: str = None,
    guild: discord.Guild = None
) -> discord.Embed:
    """Constructs an ultra-compact, modern, sleek Discord embed with dynamic custom emoji parsing."""
    parsed_title = replace_emoji_tags(title, guild) if title else None
    parsed_desc = replace_emoji_tags(description, guild) if description else None

    embed = discord.Embed(
        title=parsed_title,
        description=parsed_desc,
        color=color
    )

    if fields:
        for field in fields:
            name = field.get("name", "Field")
            value = field.get("value", "N/A")
            inline = field.get("inline", False)
            embed.add_field(name=name, value=value, inline=inline)

    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon)
    elif guild:
        g_icon = str(guild.icon.url) if guild and guild.icon else (str(guild.me.display_avatar.url) if guild and guild.me else None)
        embed.set_author(name=guild.name, icon_url=g_icon)

    thumb_url = thumbnail or (str(guild.icon.url) if guild and guild.icon else (str(guild.me.display_avatar.url) if guild and guild.me else None))
    if thumb_url:
        embed.set_thumbnail(url=thumb_url)

    footer_text = footer if footer else (f"{guild.name} • Cyber Security OS" if guild else f"{config.SERVER_NAME}")
    footer_icon = (str(guild.icon.url) if guild and guild.icon else None)
    embed.set_footer(text=footer_text, icon_url=footer_icon)

    return embed

async def send_user_dm(user: discord.User | discord.Member, title: str, description: str, color: discord.Color, fields: list = None) -> bool:
    """Sends a clean Direct Message embed to the user (Wick Bot Method)."""
    if getattr(user, "bot", False):
        return False

    guild = getattr(user, "guild", None)
    embed = joyst_embed(
        title=title,
        description=description,
        color=color,
        fields=fields,
        footer=f"{config.SERVER_NAME} Notice",
        guild=guild
    )

    # 1. Direct send attempt
    try:
        await user.send(embed=embed)
        logger.info(f"DM delivered to user {user} ({user.id})")
        return True
    except discord.Forbidden:
        pass
    except Exception as e:
        logger.debug(f"Primary DM failed for {user.id}: {e}")

    # 2. Fallback create_dm() attempt
    try:
        dm_ch = user.dm_channel or await user.create_dm()
        await dm_ch.send(embed=embed)
        logger.info(f"DM delivered via create_dm to {user} ({user.id})")
        return True
    except Exception as e:
        logger.warning(f"Could not deliver DM to {user} ({user.id}): {e}")
        return False

async def get_or_create_log_channel(guild: discord.Guild) -> discord.TextChannel:
    """Finds or automatically creates a dedicated JOYST Security Log Channel in the guild."""
    if not guild or not guild.me:
        return None

    settings = db.get_guild_settings(str(guild.id))
    log_ch_id = settings.get("log_channel_id")

    if log_ch_id:
        ch = guild.get_channel(int(log_ch_id))
        if ch:
            return ch

    target_name = "🛡️-joyst-security-logs"
    fallback_name = "joyst-security-logs"

    for ch in guild.text_channels:
        if ch.name in [target_name, fallback_name]:
            db.update_guild_setting(str(guild.id), "log_channel_id", str(ch.id))
            return ch

    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True)
        }

        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)

        new_ch = await guild.create_text_channel(
            name=target_name,
            overwrites=overwrites,
            reason=f"[{config.SERVER_NAME}] Auto-created security log vault."
        )

        db.update_guild_setting(str(guild.id), "log_channel_id", str(new_ch.id))

        welcome_embed = joyst_embed(
            title=f"{get_emoji('shield', guild)} Security Logs",
            description=f"Security event audit trail for **{guild.name}**.",
            color=COLOR_GREEN,
            guild=guild
        )
        await new_ch.send(embed=welcome_embed)
        return new_ch

    except Exception as e:
        logger.error(f"Failed to auto-create log channel in {guild.name}: {e}")
        return None

async def log_security_event(guild: discord.Guild, title: str, description: str = None, color: discord.Color = COLOR_DARK, fields: list = None):
    """Sends a compact log embed directly into the dedicated log channel."""
    log_ch = await get_or_create_log_channel(guild)
    if log_ch:
        embed = joyst_embed(title=title, description=description, color=color, fields=fields, guild=guild)
        try:
            await log_ch.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to post log in {guild.name}: {e}")

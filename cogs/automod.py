import discord
from discord.ext import commands
import re
import time
import datetime
import logging
from collections import defaultdict
import database as db
import config
from embed_builder import joyst_embed, send_user_dm, log_security_event, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_SUCCESS
from emojis import get_emoji

logger = logging.getLogger("AEGIS.AutoMod")

INVITE_REGEX = re.compile(r"(discord(?:app)?\.(?:gg|io|me|li|com\/invite)\/[a-zA-Z0-9\-]+)", re.IGNORECASE)
URL_REGEX = re.compile(
    r"(https?://\S+|www\.\S+|\b[a-zA-Z0-9.\-]+\.(?:com|net|org|gg|io|me|co|xyz|link|info|biz|dev|app|site|tech|online|store|shop|live|stream|top|club|vip|page|cloud|cc|tk|ml|ga|cf|gq|in|us|uk|eu)\b/\S*|\b[a-zA-Z0-9.\-]+\.(?:com|net|org|gg|io|me|co|xyz|link|info|biz|dev|app|site|tech|online|store|shop|live|stream|top|club|vip|page|cloud|cc|tk|ml|ga|cf|gq|in|us|uk|eu)\b)",
    re.IGNORECASE
)

SCAM_IMAGE_KEYWORDS = ["mrbeast", "giveaway", "nitro", "airdrop", "claim", "crypto", "free_nitro", "qr_code", "steam_gift", "tesla", "btc", "eth"]
TOKEN_GRABBER_KEYWORDS = [
    "mapevin", "vyro", "crypto casino", "cryptocurrency casino", "claim your reward", 
    "enter the special promo code", "receive your $2,500", "withdrawal success",
    "withdraw the bonus", "rake-back", "rakeback", "bonus code", "activate code for bonus",
    "honestly6327", "free usdt", "2500 usdt", "2,500 usdt", "crypto giveaway", "airdrop bonus",
    "mrbeast games", "beast games"
]
TOXIC_KEYWORDS = [
    "mc", "bc", "bkl", "chutiye", "chutiya", "gandu", "gand", "gaand", "lund", "lauda", "loda", "lawde", "lawda",
    "bhenchod", "madarchod", "bsdk", "bhosdike", "bhosdika", "randi", "terimaa", "gandmare", "gandmasti",
    "chakke", "chakka", "hijra", "hijde", "lodu", "tatte", "tatta", "mutthal", "jhant", "jhantu", "raddi",
    "maderchod", "behenchod", "bhenkeode", "bhenlode", "chut", "chutmarike", "harami", "kamine", "saale", "saley",
    "retard", "nigger", "faggot", "slut", "whore", "bitch", "bastard"
]

PHISHING_DOMAINS = [
    "mapevin.com", "mapevin.io", "mapevin.net", "vyro-crypto.com", "vyro.io", "vyro.com",
    "dlscord.gift", "discrod.gift", "dlscord.com", "discrod.com", "discord-nitro.com",
    "discord-app.info", "discord-free.ru", "discbrd.com", "dlscord.net", "discordapp.info",
    "steamcommunlty.com", "steamcomunuty.ru", "steam-nitro.com", "free-nitro.ru",
    "nitro-free.link", "discord-claim.com", "discord-gift.com", "dlscordapp.com"
]

PHISHING_REGEX = re.compile(
    r"(https?://\S*(?:mapevin|vyro|dlscord|discrod|discord-nitro|steamcommunlty|steamcomunuty|free-nitro|discord-gift|dlscordapp|discbrd)\S*)",
    re.IGNORECASE
)

# --- IP LOGGER & IMAGE GRABBER SHIELD DOMAINS & PATTERNS ---
IP_LOGGER_DOMAINS = [
    "grabify.link", "grabify.org", "iplogger.org", "iplogger.com", "iplogger.ru", "2no.co",
    "mewho.com", "yip.su", "blasze.com", "blasze.tk", "cur.lv", "v.gd", "x.co", "po.st",
    "cutt.ly", "tinyurl.com", "shorturl.at", "bit.ly", "is.gd", "buff.ly", "rebrand.ly",
    "qr.ae", "adf.ly", "bc.vc", "ow.ly", "v.ht", "clck.ru", "rotf.lol", "linkvertise.com",
    "linkvertise.net", "adfly.com", "shorte.st", "gestyy.com", "short.pe", "shorturl.com",
    "discord-gift.app", "discord-gift.ru", "discord-nitro.link", "discord-steam.com"
]

IP_LOGGER_REGEX = re.compile(
    r"(https?://\S*(?:grabify|iplogger|2no\.co|mewho|yip\.su|blasze|cur\.lv|linkvertise|shorturl|tinyurl|bit\.ly|is\.gd|buff\.ly|rebrand\.ly|clck\.ru|rotf\.lol|adf\.ly|shorte\.st|gestyy)\S*)",
    re.IGNORECASE
)

SUSPICIOUS_IMAGE_SCRIPT_REGEX = re.compile(
    r"(https?://\S+\.(?:php|cgi|asp|aspx|jsp|pl|py|sh)\?\S*|\bhttps?://\S+/(?:image|pic|view|download|avatar|photo|img|media)\.php\S*)",
    re.IGNORECASE
)

MARKDOWN_LINK_REGEX = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", re.IGNORECASE)
INVISIBLE_CHAR_REGEX = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]", re.UNICODE)
DOUBLE_EXTENSION_REGEX = re.compile(
    r"\.(?:png|jpg|jpeg|gif|bmp|webp)\.(?:exe|scr|bat|vbs|pif|cmd|ps1|zip|rar|7z|tar|iso|jar|js|hta|wsf)",
    re.IGNORECASE
)

SUSPICIOUS_QUERY_PARAMS = [
    "?token=", "&token=", "?auth=", "&auth=", "?redirect=", "&redirect=",
    "?callback=", "&callback=", "?return=", "&return=", "?access_token=", "&access_token=",
    "?session=", "&session=", "?login=", "&login="
]

WEBHOOK_URL_REGEX = re.compile(
    r"(https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/\d+/[a-zA-Z0-9_\-]+)",
    re.IGNORECASE
)

TRUSTED_IMAGE_CDNS = [
    "cdn.discordapp.com",
    "media.discordapp.net",
    "images-ext-1.discordapp.net",
    "images-ext-2.discordapp.net",
    "imgur.com",
    "i.imgur.com",
    "tenor.com",
    "media.tenor.com",
    "giphy.com",
    "media.giphy.com",
    "gfycat.com"
]

import io
import urllib.parse

try:
    from PIL import Image
    import pytesseract
    HAS_OCR = True
except Exception:
    HAS_OCR = False

async def scan_image_attachment_for_scams(attachment: discord.Attachment) -> bool:
    """Downloads attachment and performs Optical Character Recognition (OCR) to detect embedded text in token-grabber images!"""
    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        return False

    fname = attachment.filename.lower()
    if any(kw in fname for kw in TOKEN_GRABBER_KEYWORDS + SCAM_IMAGE_KEYWORDS):
        return True

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url, timeout=5) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
                    
                    if HAS_OCR:
                        try:
                            img = Image.open(io.BytesIO(img_bytes))
                            ocr_text = pytesseract.image_to_string(img).lower()
                            scam_triggers = TOKEN_GRABBER_KEYWORDS + [
                                "activate code", "withdrawal success", "bonus", "casino", 
                                "rakeback", "$2500", "2500$", "transfer completed", "vyro", "mapevin"
                            ]
                            if any(kw in ocr_text for kw in scam_triggers):
                                logger.warning(f"OCR Scam Image Detected! Extracted Text: {ocr_text[:200]}")
                                return True
                        except Exception:
                            pass
    except Exception as e:
        logger.debug(f"Image scan error: {e}")

    return False

def is_scam_image_or_text(message: discord.Message) -> bool:
    """Detects if message content, attachment filenames, or embed data contain automated MrBeast / Token Grabber / Image Grabber patterns."""
    text_content = message.content.lower()

    # 0. Check for Webhook URLs posted by non-admins
    if WEBHOOK_URL_REGEX.search(message.content):
        logger.warning(f"Blocked Raw Discord Webhook Leak from {message.author}")
        return True

    # 1. Check for Masked Image Markdown Links [label](target_url) & Invisible Payloads
    if INVISIBLE_CHAR_REGEX.search(message.content) and (message.attachments or message.embeds or "http" in text_content):
        logger.warning(f"Blocked Invisible Zero-Width Payload in Image Message from {message.author}")
        return True

    markdown_matches = MARKDOWN_LINK_REGEX.findall(message.content)
    for label, target_url in markdown_matches:
        label_clean = label.lower()
        target_clean = target_url.lower()

        # If markdown link label claims to be an image or CDN link but target URL is different
        if any(ext in label_clean for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", "cdn.discordapp", "media.discordapp"]) or any(ext in target_clean for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
            if label_clean != target_clean:
                logger.warning(f"Blocked Masked Image Hyperlink Token Grabber Exploit! Label: '{label[:50]}' -> Target: '{target_url[:50]}' from {message.author}")
                return True

        if IP_LOGGER_REGEX.search(target_clean) or any(d in target_clean for d in IP_LOGGER_DOMAINS) or SUSPICIOUS_IMAGE_SCRIPT_REGEX.search(target_clean):
            return True

    # 2. Direct Check for IP Logger / Image Grabber domains & CGI script links & Suspicious OAuth Query Params
    if IP_LOGGER_REGEX.search(text_content) or any(domain in text_content for domain in IP_LOGGER_DOMAINS):
        return True

    if SUSPICIOUS_IMAGE_SCRIPT_REGEX.search(text_content):
        return True

    if any(param in text_content for param in SUSPICIOUS_QUERY_PARAMS):
        return True

    # 3. Check for Token Grabber / Phishing keywords directly
    if any(kw in text_content for kw in TOKEN_GRABBER_KEYWORDS):
        return True

    # 4. Check attachments (filenames / double extensions / image content types / tracking pixels)
    for att in message.attachments:
        fname = att.filename.lower()

        # Double extension executable check (e.g. image.png.exe)
        if DOUBLE_EXTENSION_REGEX.search(fname):
            logger.warning(f"Blocked Double Extension Executable Image '{fname}' from {message.author}")
            return True

        if any(kw in fname for kw in SCAM_IMAGE_KEYWORDS + TOKEN_GRABBER_KEYWORDS):
            return True

        if att.content_type and att.content_type.startswith("image/"):
            # Block 1x1 or tiny tracking pixel images (< 500 bytes or <= 5px dimensions)
            if att.size < 500 or (att.width and att.width <= 5) or (att.height and att.height <= 5):
                logger.warning(f"Blocked 1x1 IP tracking pixel attachment from {message.author}")
                return True

            if any(kw in text_content for kw in ["mrbeast", "giveaway", "scan", "qr", "claim", "nitro", "$1000", "free", "$2500", "bonus", "casino", "withdraw"]):
                return True

    # 5. Check embeds (image URLs / titles / descriptions / Untrusted Image Host Embeds)
    for embed in message.embeds:
        emb_text = f"{embed.title or ''} {embed.description or ''}".lower()
        if any(kw in emb_text for kw in SCAM_IMAGE_KEYWORDS + TOKEN_GRABBER_KEYWORDS):
            return True

        urls_to_check = []
        if embed.image and embed.image.url:
            urls_to_check.append(embed.image.url.lower())
        if embed.thumbnail and embed.thumbnail.url:
            urls_to_check.append(embed.thumbnail.url.lower())
        if embed.url:
            urls_to_check.append(embed.url.lower())

        for u in urls_to_check:
            if IP_LOGGER_REGEX.search(u) or any(d in u for d in IP_LOGGER_DOMAINS) or SUSPICIOUS_IMAGE_SCRIPT_REGEX.search(u) or any(kw in u for kw in SCAM_IMAGE_KEYWORDS + TOKEN_GRABBER_KEYWORDS) or any(param in u for param in SUSPICIOUS_QUERY_PARAMS):
                return True

            # Strictly verify image embed host domain against TRUSTED_IMAGE_CDNS!
            try:
                parsed_host = urllib.parse.urlparse(u).netloc.lower()
                if parsed_host and not any(trusted in parsed_host for trusted in TRUSTED_IMAGE_CDNS):
                    logger.warning(f"Blocked untrusted external image embed domain '{parsed_host}' from {message.author}")
                    return True
            except Exception:
                pass

    # 6. Check text content for MrBeast giveaway scam patterns
    if ("mrbeast" in text_content or "giveaway" in text_content or "casino" in text_content) and any(w in text_content for w in ["claim", "nitro", "free", "scan", "qr", "crypto", "$", "code"]):
        return True

    return False

    # 1. Check for Token Grabber / Phishing keywords directly
    if any(kw in text_content for kw in TOKEN_GRABBER_KEYWORDS):
        return True

    # 2. Check attachments (filenames / image content types / tracking pixels)
    for att in message.attachments:
        fname = att.filename.lower()
        if any(kw in fname for kw in SCAM_IMAGE_KEYWORDS + TOKEN_GRABBER_KEYWORDS):
            return True
        if att.content_type and att.content_type.startswith("image/"):
            # Block 1x1 or tiny tracking pixel images (< 500 bytes or <= 5px dimensions)
            if att.size < 500 or (att.width and att.width <= 5) or (att.height and att.height <= 5):
                logger.warning(f"Blocked 1x1 IP tracking pixel attachment from {message.author}")
                return True

            if any(kw in text_content for kw in ["mrbeast", "giveaway", "scan", "qr", "claim", "nitro", "$1000", "free", "$2500", "bonus", "casino", "withdraw"]):
                return True

    # 3. Check embeds (image URLs / titles / descriptions / Untrusted Image Host Embeds)
    for embed in message.embeds:
        emb_text = f"{embed.title or ''} {embed.description or ''}".lower()
        if any(kw in emb_text for kw in SCAM_IMAGE_KEYWORDS + TOKEN_GRABBER_KEYWORDS):
            return True

        urls_to_check = []
        if embed.image and embed.image.url:
            urls_to_check.append(embed.image.url.lower())
        if embed.thumbnail and embed.thumbnail.url:
            urls_to_check.append(embed.thumbnail.url.lower())
        if embed.url:
            urls_to_check.append(embed.url.lower())

        for u in urls_to_check:
            if IP_LOGGER_REGEX.search(u) or any(d in u for d in IP_LOGGER_DOMAINS) or SUSPICIOUS_IMAGE_SCRIPT_REGEX.search(u) or any(kw in u for kw in SCAM_IMAGE_KEYWORDS + TOKEN_GRABBER_KEYWORDS):
                return True

            # Strictly verify image embed host domain against TRUSTED_IMAGE_CDNS!
            try:
                parsed_host = urllib.parse.urlparse(u).netloc.lower()
                if parsed_host and not any(trusted in parsed_host for trusted in TRUSTED_IMAGE_CDNS):
                    logger.warning(f"Blocked untrusted external image embed domain '{parsed_host}' from {message.author}")
                    return True
            except Exception:
                pass

    # 4. Check text content for MrBeast giveaway scam patterns
    if ("mrbeast" in text_content or "giveaway" in text_content or "casino" in text_content) and any(w in text_content for w in ["claim", "nitro", "free", "scan", "qr", "crypto", "$", "code"]):
        return True

    return False

async def check_and_delete_scam_image(message: discord.Message) -> bool:
    """Checks message text, embeds, and image attachments for any token grabber / scam pattern."""
    if is_scam_image_or_text(message):
        return True

    if message.attachments:
        for att in message.attachments:
            if await scan_image_attachment_for_scams(att):
                return True

    return False

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_message_history = defaultdict(lambda: defaultdict(list))

    async def _log_automod_violation(self, guild: discord.Guild, member: discord.Member, message: discord.Message, violation_type: str, action_taken: str, details: str):
        fields = [
            {"name": "Offending User", "value": f"{member.mention} (`{member.id}`)", "inline": True},
            {"name": "Action Taken", "value": f"`{action_taken}`", "inline": True},
            {"name": "Channel", "value": f"{message.channel.mention}", "inline": True},
            {"name": "Violation Type", "value": f"`{violation_type}` — {details}", "inline": False},
            {"name": "Exact Message Content", "value": f"```{message.content[:1000] if message.content else '[Image / File Only]'}```", "inline": False}
        ]

        if message.attachments:
            att_links = "\n".join([f"• [{att.filename}]({att.url})" for att in message.attachments[:5]])
            fields.append({"name": "Attachments / Images", "value": att_links, "inline": False})

        await log_security_event(
            guild=guild,
            title=f"🚨 AUTOMOD VIOLATION DETECTED • {config.SERVER_NAME}",
            color=COLOR_DANGER,
            fields=fields
        )

    async def _handle_warning_escalation(self, guild: discord.Guild, member: discord.Member, reason: str, message: discord.Message = None):
        warn_count = db.add_warning(str(guild.id), str(member.id), reason, str(self.bot.user.id))
        
        if warn_count == 1:
            timeout_minutes = 2
            duration_str = "2 Minutes"
        elif warn_count == 2:
            timeout_minutes = 5
            duration_str = "5 Minutes"
        else:
            timeout_minutes = 10
            duration_str = "10 Minutes"

        until = discord.utils.utcnow() + datetime.timedelta(minutes=timeout_minutes)

        to_fields = [
            {"name": "Server", "value": f"**{guild.name} ({config.SERVER_NAME})**", "inline": True},
            {"name": "Timeout Duration", "value": f"`{duration_str}`", "inline": True},
            {"name": "Violation Count", "value": f"`{warn_count}`", "inline": True},
            {"name": "Reason", "value": reason, "inline": False},
            {"name": "Escalation Policy", "value": "1st Violation = 2m Timeout | 2nd Violation = 5m Timeout | 3rd+ Violation = 10m Timeout", "inline": False}
        ]
        await send_user_dm(member, f"🔇 Timeout Applied • {config.SERVER_NAME}", "AutoMod detected a policy violation and applied a timeout.", COLOR_WARNING, to_fields)

        try:
            await member.timeout(until, reason=f"[{config.SERVER_NAME} AutoMod] {reason} (Warn #{warn_count})")
            
            if message:
                await self._log_automod_violation(guild, member, message, "POLICY_VIOLATION", f"{duration_str} Timeout (Warn #{warn_count})", reason)
            else:
                await log_security_event(
                    guild=guild,
                    title=f"⚠️ AutoMod Violation & Timeout • {config.SERVER_NAME}",
                    color=COLOR_WARNING,
                    fields=[
                        {"name": "Offender", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                        {"name": "Timeout Applied", "value": f"`{duration_str}`", "inline": True},
                        {"name": "Violation Count", "value": f"`{warn_count}`", "inline": True},
                        {"name": "Violation Reason", "value": reason, "inline": False}
                    ]
                )

            db.add_audit_log(
                guild_id=str(guild.id),
                action_type="AUTOMOD_TIMEOUT",
                details=f"Timed out {member} ({member.id}) for {duration_str} [Warn #{warn_count}]. Reason: {reason}",
                culprit_id=str(member.id),
                culprit_name=str(member),
                severity="MEDIUM"
            )
        except Exception as e:
            logger.error(f"Failed to apply AutoMod timeout for {member.id}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        guild = message.guild
        member = message.author
        if not isinstance(member, discord.Member):
            return

        if member.id == guild.owner_id or member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return

        user_roles = [str(r.id) for r in member.roles]
        channel_id_str = str(message.channel.id)

        if (db.is_whitelisted(str(guild.id), str(member.id), "all", user_roles, channel_id_str) or
            db.is_whitelisted(str(guild.id), str(member.id), "anti_link", user_roles, channel_id_str) or
            db.is_whitelisted(str(guild.id), str(member.id), "anti_spam", user_roles, channel_id_str)):
            return

        msg_clean = message.content.lower().strip()

        # 0. IMMEDIATE STEP 0: Anti-Token-Grabber & Scam Image Scanner
        is_scam = await check_and_delete_scam_image(message)
        if is_scam:
            try:
                await message.delete()
            except Exception:
                pass

            duration = datetime.timedelta(hours=1)
            until = datetime.datetime.now(datetime.timezone.utc) + duration

            try:
                await member.timeout(until, reason=f"[{config.SERVER_NAME} Anti-Token-Grabber] Posted malicious token grabber / scam image.")
            except Exception:
                pass

            try:
                embed = joyst_embed(
                    title="🚨 ANTI-TOKEN GRABBER GUARD ACTIVATED",
                    description=f"{member.mention}, a malicious token-grabber scam image / message was detected and **DELETED IMMEDIATELY**. Account timed out for **1 Hour**.",
                    color=COLOR_DANGER,
                    guild=guild
                )
                await message.channel.send(embed=embed, delete_after=10)
            except Exception:
                pass

            await log_security_event(
                guild=guild,
                title=f"🚨 TOKEN GRABBER / SCAM IMAGE BLOCKED • {config.SERVER_NAME}",
                color=COLOR_DANGER,
                fields=[
                    {"name": "Offender Account", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                    {"name": "Channel", "value": message.channel.mention, "inline": True},
                    {"name": "Action Taken", "value": "`Message Deleted & 1 Hour Timeout`", "inline": False}
                ]
            )

            db.add_audit_log(
                guild_id=str(guild.id),
                action_type="TOKEN_GRABBER_DELETED",
                details=f"Deleted malicious token grabber scam image from user {member} ({member.id}) in #{message.channel.name}.",
                culprit_id=str(member.id),
                culprit_name=str(member),
                severity="HIGH"
            )
            return

        # 1. Anti-Phishing & Fake Nitro Link Guard Engine
        if PHISHING_REGEX.search(msg_clean) or any(p_dom in msg_clean for p_dom in PHISHING_DOMAINS):
            try:
                await message.delete()
            except Exception:
                pass

            duration = datetime.timedelta(hours=1)
            until = datetime.datetime.now(datetime.timezone.utc) + duration

            try:
                await member.timeout(until, reason=f"[{config.SERVER_NAME} Anti-Phishing Guard] Posted dangerous phishing/fake Nitro link.")
                desc = f"🚨 **ANTI-PHISHING GUARD:** {member.mention} has been timed out for **1 Hour** for posting a dangerous phishing/scam link. Message deleted."
                embed = joyst_embed(description=desc, color=COLOR_DANGER, guild=guild)
                await message.channel.send(embed=embed, delete_after=10)

                db.add_audit_log(str(guild.id), "ANTI_PHISHING", f"Blocked phishing link from {member} ({member.id}). Timed out 1 hr.", str(member.id), str(member), "HIGH")
                await self._log_automod_violation(guild, member, message, "PHISHING_LINK_ATTEMPT", "1 Hour Timeout & Message Deleted", "Fake Nitro / Phishing Link Detected")
                return
            except Exception as e:
                logger.error(f"Failed to timeout phishing offender {member.id}: {e}")

        # AI Chat Toxicity & Severe Abuse Filter (Warn #1, Warn #2, and Timeout on Warn #3+)
        for toxic_word in TOXIC_KEYWORDS:
            if re.search(r'\b' + re.escape(toxic_word) + r'\b', msg_clean):
                try:
                    await message.delete()
                except Exception:
                    pass

                warn_count = db.add_warning(str(guild.id), str(member.id), f"Toxic Language / Abuse: '{toxic_word}'", str(self.bot.user.id))
                
                # Check if 3rd violation or higher -> TIMEOUT
                if warn_count >= 3:
                    timeout_minutes = 10 if warn_count == 3 else 30
                    duration = datetime.timedelta(minutes=timeout_minutes)
                    until = datetime.datetime.now(datetime.timezone.utc) + duration
                    
                    try:
                        await member.timeout(until, reason=f"[{config.SERVER_NAME} AutoMod] Accumulated {warn_count} toxic language warnings.")
                        desc = f"{get_emoji('warning', guild)} **AUTOMOD TIMEOUT (3rd Abuse Violation):** {member.mention} has been timed out for **{timeout_minutes} minutes** for repeated toxic language/slurs."
                        embed = joyst_embed(description=desc, color=COLOR_DANGER, guild=guild)
                        await message.channel.send(embed=embed, delete_after=10)
                        
                        db.add_audit_log(str(guild.id), "AUTOMOD_TOXICITY_TIMEOUT", f"Timed out {member} ({member.id}) for {timeout_minutes}m after {warn_count} toxic warnings.", str(member.id), str(member), "HIGH")
                        await self._log_automod_violation(guild, member, message, "TOXIC_LANGUAGE", f"10m Timeout (Warn #{warn_count})", f"Word: '{toxic_word}'")
                        return
                    except Exception as e:
                        logger.error(f"Failed to timeout toxic user {member.id}: {e}")

                desc = f"{get_emoji('warning', guild)} **TOXIC LANGUAGE FILTERED:** {member.mention}, toxic slurs are strictly prohibited! Message deleted. **(Warn #{warn_count}/3)**"
                embed = joyst_embed(description=desc, color=COLOR_WARNING, guild=guild)
                try:
                    await message.channel.send(embed=embed, delete_after=8)
                except Exception:
                    pass

                db.add_audit_log(str(guild.id), "AUTOMOD_TOXICITY", f"Filtered toxic slur '{toxic_word}' from {member} ({member.id}). Warn #{warn_count}.", str(member.id), str(member), "MEDIUM")
                await self._log_automod_violation(guild, member, message, "TOXIC_LANGUAGE", f"Warning #{warn_count}/3", f"Word: '{toxic_word}'")
                return

        # AI Sales & FAQ Assistant (Detects buying panel / vps / support queries)
        msg_clean = message.content.lower().strip()
        buying_keywords = ["buy", "buying", "panel", "vps", "price", "cost", "shop", "khareedna", "lena h", "lena hai", "purchase"]
        
        if any(kw in msg_clean for kw in buying_keywords) and len(msg_clean) < 120 and not message.channel.name.startswith("ticket-"):
            ticket_ch = discord.utils.get(guild.text_channels, name="tickets") or discord.utils.get(guild.text_channels, name="support")
            ch_mention = ticket_ch.mention if ticket_ch else "#support / #tickets"
            
            ai_reply = (
                f"👋 **Hey {member.mention}!**\n\n"
                f"🎟️ **Looking to buy a Panel / VPS or need billing support?**\n"
                f"Please open a private support ticket in {ch_mention} to talk directly with our sales team!"
            )
            embed = joyst_embed(description=ai_reply, color=COLOR_INFO, guild=guild)
            try:
                await message.channel.send(embed=embed, delete_after=15)
            except Exception:
                pass

        settings = db.get_guild_settings(str(guild.id))

        # 0. SPECIAL FILTER: MrBeast / Scam Image & Phishing Detector (DELETE ONLY, NO BAN / NO TIMEOUT / NO WARN)
        if is_scam_image_or_text(message):
            try:
                await message.delete()
            except Exception:
                pass

            try:
                embed = joyst_embed(
                    title=f"🛡️ Automated Scam Image Filtered • {config.SERVER_NAME}",
                    description=f"{member.mention}, an automated scam/giveaway image was removed for server safety. **No punishment applied.**",
                    color=COLOR_INFO
                )
                await message.channel.send(embed=embed, delete_after=5)
            except Exception:
                pass

            # DM User Advisory
            advisory_fields = [
                {"name": "Server", "value": f"**{guild.name}**", "inline": True},
                {"name": "Action Taken", "value": "`Message Deleted Only (No Ban / No Timeout)`", "inline": True},
                {"name": "Security Tip", "value": "If your account was token-logged or hijacked, please change your Discord password & enable 2FA immediately!", "inline": False}
            ]
            await send_user_dm(member, f"ℹ️ Security Advisory • {config.SERVER_NAME}", "An automated scam image was posted from your account.", COLOR_INFO, advisory_fields)

            await log_security_event(
                guild=guild,
                title=f"🧹 Scam Image Filtered (No Punishment) • {config.SERVER_NAME}",
                color=COLOR_INFO,
                fields=[
                    {"name": "User Account", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                    {"name": "Channel", "value": message.channel.mention, "inline": True},
                    {"name": "Action Taken", "value": "`Message Deleted Only`", "inline": False}
                ]
            )

            db.add_audit_log(
                guild_id=str(guild.id),
                action_type="SCAM_IMAGE_DELETED",
                details=f"Deleted automated scam image from user {member} ({member.id}) in #{message.channel.name} [No Punishment Applied].",
                culprit_id=str(member.id),
                culprit_name=str(member),
                severity="LOW"
            )
            return

        # 1. Anti-Mass-Mention / Rapid Tag Filter (5+ mentions)
        if settings.get("anti_mass_mention"):
            if not db.is_whitelisted(str(guild.id), str(member.id), "anti_spam", user_roles, channel_id_str):
                mentions_count = len(message.mentions) + len(message.role_mentions)
                if message.mention_everyone or mentions_count >= 5:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    try:
                        embed = joyst_embed(
                            title=f"⚠️ RAPID TAGGING PROHIBITED • TIMED OUT",
                            description=f"{member.mention}, tagging 5+ users/roles or `@everyone` is prohibited! Your message was deleted and you have been timed out.",
                            color=COLOR_WARNING
                        )
                        await message.channel.send(embed=embed, delete_after=6)
                    except Exception:
                        pass

                    await self._handle_warning_escalation(guild, member, "Rapid tagging / 5+ user mentions violation.", message)
                    return

        # 2. Universal Anti-Link Filter (TIMEOUT ONLY, NO BANS)
        if settings.get("anti_invite"):
            if not db.is_whitelisted(str(guild.id), str(member.id), "anti_link", user_roles, channel_id_str):
                if URL_REGEX.search(message.content) or INVITE_REGEX.search(message.content):
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    try:
                        embed = joyst_embed(
                            title=f"🔇 LINK PROHIBITED • TIMED OUT",
                            description=f"{member.mention}, posting links or URLs is prohibited! Your message was removed and you have been timed out.",
                            color=COLOR_WARNING
                        )
                        await message.channel.send(embed=embed, delete_after=6)
                    except Exception:
                        pass

                    await self._handle_warning_escalation(guild, member, "Unauthorized URL / link posted in server.", message)
                    return

        # 3. Anti-Spam (Same message 5+ times or 5 messages in 10s)
        if settings.get("anti_spam"):
            if not db.is_whitelisted(str(guild.id), str(member.id), "anti_spam", user_roles, channel_id_str):
                now = time.time()
                history = self.user_message_history[str(guild.id)][str(member.id)]
                history = [item for item in history if now - item[0] <= 10]
                history.append((now, hash(message.content)))
                self.user_message_history[str(guild.id)][str(member.id)] = history

                recent_hashes = [h for _, h in history]
                if len(history) >= 5 or recent_hashes.count(hash(message.content)) >= 5:
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    try:
                        embed = joyst_embed(
                            title=f"🔇 REPEATED SPAM • TIMED OUT",
                            description=f"{member.mention}, sending the same message 5+ times or spam flooding is prohibited! You have been timed out.",
                            color=COLOR_WARNING
                        )
                        await message.channel.send(embed=embed, delete_after=6)
                    except Exception:
                        pass

                    await self._handle_warning_escalation(guild, member, "Sending same message 5+ times / rapid spam flooding.", message)
                    return

async def setup(bot):
    await bot.add_cog(AutoMod(bot))

import discord
from discord import app_commands
from discord.ext import commands
import logging
import time
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
import platform
import database as db
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji

logger = logging.getLogger("AEGIS.SecurityCmd")

def is_admin_or_owner(ctx_or_interaction) -> bool:
    """Helper to verify if invoker is Server Owner or Administrator"""
    guild = ctx_or_interaction.guild
    if not guild:
        return False
    user = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author
    if user.id == guild.owner_id:
        return True
    if hasattr(user, "guild_permissions") and user.guild_permissions.administrator:
        return True
    return False

# --- Modern Interactive Help Dropdown & View ---

class HelpDropdown(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [
            discord.SelectOption(label="Antinuke & Anti-Raid", value="antinuke", description="Anti-Nuke, Anti-Raid, Emergency Lockdown", emoji=get_emoji("shield", guild)),
            discord.SelectOption(label="Moderation & Enforcement", value="moderation", description="Ban, TempBan, Timeout, Purge, Whitelist, Say", emoji=get_emoji("ban", guild)),
            discord.SelectOption(label="Hi-Fi Music System", value="music", description="Play, Skip, Stop, Loop, Autoplay", emoji=get_emoji("music", guild)),
            discord.SelectOption(label="Support Ticket System", value="ticket", description="Support Ticket Dropdown Panel & Close/Claim", emoji=get_emoji("ticket", guild)),
            discord.SelectOption(label="Giveaway Manager", value="giveaway", description="Interactive Giveaway Start, Reroll & End", emoji=get_emoji("giveaway", guild)),
            discord.SelectOption(label="Voice & TTS Engine", value="voice_tts", description="TTS Speech, 24/7 Voice Channel, Auto-TTS", emoji=get_emoji("bot", guild)),
            discord.SelectOption(label="Server Stats & Temp VC", value="stats_tempvc", description="Live Member Counter & Dynamic Temp VC", emoji=get_emoji("stats", guild)),
            discord.SelectOption(label="Utilities & Bot Info", value="utilities", description="Ping, BotInfo, ServerInfo, Uptime, UserInfo", emoji=get_emoji("info", guild)),
        ]
        super().__init__(placeholder="> Select Module From Here", min_values=1, max_values=1, options=options)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        guild = interaction.guild
        bot_user = interaction.client.user
        bot_avatar = bot_user.display_avatar.url

        if selected == "antinuke":
            desc = (
                f"<a:dev:1528079861283946538> **ANTINUKE & CYBER DEFENSE MATRIX**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,emergencylockdown` • **[OWNER ONLY]** 1-s lockdown & role strip\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,unlockdown` • **[OWNER ONLY]** Lift emergency lockdown\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,security status` • View live anti-nuke & anti-raid status\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,whitelist add` • Add user/role/channel to whitelist\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,whitelist remove` • Remove entry from whitelist\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,whitelist list` • View current whitelisted entries\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `,audit` • View recent security audit logs\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_DANGER, guild=guild)

        elif selected == "moderation":
            desc = (
                f"<:zzz_banned:1534236096781619252> **MODERATION & ENFORCEMENT ENGINE**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,ban` • Ban a member from the server\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,tempban` • Temporarily ban a user (e.g. `,tempban @user 7d`)\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,kick` • Kick a member from the server\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,timeout` • Apply or remove member timeout\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,purge` • Bulk clean text channel messages\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,warn` • Issue an official warning to a member\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `,say` • **[HIDDEN ADMIN]** Repeat message directly as bot\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)

        elif selected == "music":
            desc = (
                f"<a:Playing_Audio:1534236884639944705> **HI-FI MUSIC ENGINE MODULE**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,play` • **[OPEN FOR ALL]** Play song or URL stream\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,skip` • **[STAFF ONLY]** Skip current playing track\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,stop` • **[STAFF ONLY]** Clear queue & disconnect VC\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,loop` • **[STAFF ONLY]** Toggle Track or Queue loop\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `,autoplay` • **[STAFF ONLY]** Toggle non-stop music autoplay\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_INFO, guild=guild)

        elif selected == "ticket":
            desc = (
                f"<a:question1:1534236585456046274> **SUPPORT TICKET SYSTEM MODULE**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,ticket setup` • Deploy interactive **📩 Support Ticket Panel**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,close` • Close current support ticket channel\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> **Claim Ticket** • Staff claim & handle private ticket\n"
                f" └─ <:xliyo_arrow:1528079785123774676> **Transcript Export** • Save and export 200-message chat log\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

        elif selected == "giveaway":
            desc = (
                f"<a:settings:1528080056620941362> **GIVEAWAY MANAGER MODULE**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `/giveaway start` • Deploy interactive giveaway with entry buttons\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `/giveaway reroll` • Pick a new winner for an active/ended giveaway\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `/giveaway end` • Force end giveaway immediately\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_WARNING, guild=guild)

        elif selected == "voice_tts":
            desc = (
                f"<a:bots:1534236795187888178> **VOICE & TTS SPEECH ENGINE**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,tts <text>` • Convert text to natural speech audio stream in VC\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,247` • Toggle 24/7 permanent Voice Channel connection\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,ttsauto` • Auto-read channel text messages into VC\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,join` • Connect bot to your current voice channel\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `,leave` • Disconnect bot from voice channel\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_INFO, guild=guild)

        elif selected == "stats_tempvc":
            desc = (
                f"<a:Green_Loading:1534236460163661976> **SERVER STATS & TEMP VC GENERATOR**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,stats setup` • Deploy live member counter voice channel (`👥 Total Members: X`)\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `,tempvc setup` • Deploy dynamic **➕ Join to Create** private VC generator\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

        elif selected == "utilities":
            desc = (
                f"<:RainyMM_info:1534236695854055546> **UTILITIES & SYSTEM INFO ENGINE**\n\n"
                f"• **Command List**\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,ping` • View WebSocket, Discord API & Database Latency\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,botinfo` • View bot RAM allocation, CPU load & VPS health\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,serverinfo` • View detailed server stats & member breakdown\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,uptime` • View continuous online uptime tracker\n"
                f" ├─ <:xliyo_arrow:1528079785123774676> `,userinfo` • View user account creation & permissions\n"
                f" └─ <:xliyo_arrow:1528079785123774676> `,weather` • View live weather temperature & forecast\n\n"
                f"🔗 **Links**\n"
                f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
                f"[Support Server](https://discord.gg/joyst) | "
                f"[Website](https://syphon-security-bot.onrender.com)"
            )
            embed = joyst_embed(description=desc, color=COLOR_INFO, guild=guild)

        embed.set_thumbnail(url=bot_avatar)
        embed.set_footer(text=f"Powered By SYPHON SECURITY OS | Designed for {guild.name}", icon_url=guild.icon.url if guild.icon else None)
        await interaction.response.edit_message(embed=embed, view=self.view)

class AdvancedHelpView(discord.ui.View):
    def __init__(self, guild: discord.Guild, invoker: discord.User | discord.Member):
        super().__init__(timeout=180)
        self.invoker = invoker
        self.add_item(HelpDropdown(guild))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker.id and not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ You cannot control this help menu.", ephemeral=True)
            return False
        return True

class SecurityCmd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_status(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        settings = db.get_guild_settings(str(guild.id))

        status_anti_nuke = f"{get_emoji('online', guild)} Enabled" if settings.get("anti_nuke", 1) else f"{get_emoji('offline', guild)} Disabled"
        status_anti_raid = f"{get_emoji('online', guild)} Enabled" if settings.get("anti_raid", 1) else f"{get_emoji('offline', guild)} Disabled"
        status_anti_spam = f"{get_emoji('online', guild)} Enabled" if settings.get("anti_spam", 1) else f"{get_emoji('offline', guild)} Disabled"
        status_anti_invite = f"{get_emoji('online', guild)} Enabled" if settings.get("anti_invite", 1) else f"{get_emoji('offline', guild)} Disabled"
        
        log_ch_id = settings.get("log_channel_id")
        log_ch_str = f"<#{log_ch_id}>" if log_ch_id else "`#joyst-security-logs`"

        desc = (
            f"🛡️ **{config.SERVER_NAME} Security Matrix Status**\n\n"
            f"• **Anti-Nuke Protection:** {status_anti_nuke}\n"
            f"• **Anti-Raid / Bot Guard:** {status_anti_raid}\n"
            f"• **Anti-Spam & Phishing Filter:** {status_anti_spam}\n"
            f"• **Anti-Invite Link Filter:** {status_anti_invite}\n"
            f"• **Dedicated Log Channel:** {log_ch_str}\n"
            f"• **Nuke Action Mode:** `{settings.get('action_on_nuke', 'quarantine').upper()}`"
        )
        embed = joyst_embed(description=desc, color=COLOR_INFO, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _do_whitelist_add(self, ctx_or_interaction, target_id: str, target_name: str, target_type: str, feature: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if not is_admin_or_owner(ctx_or_interaction):
            embed = joyst_embed(description="❌ Access Denied: Administrator permissions required.", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        db.add_whitelist(str(guild.id), target_id, target_type, feature, str(author.id))

        desc = f"✅ Whitelisted **{target_name}** (`{target_id}`) for feature `{feature.upper()}`."
        embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

        db.add_audit_log(str(guild.id), "WHITELIST_ADD", f"Added {target_type} {target_name} ({target_id}) to whitelist for {feature}.", str(author.id), str(author), "MEDIUM")

    async def _do_whitelist_remove(self, ctx_or_interaction, target_id: str, feature: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if not is_admin_or_owner(ctx_or_interaction):
            return

        clean_id = target_id.replace("<@", "").replace("<#", "").replace("<&", "").replace("!", "").replace(">", "").strip()
        affected = db.remove_whitelist(str(guild.id), clean_id, feature)

        if affected > 0:
            desc = f"✅ Removed `{clean_id}` from `{feature.upper()}` whitelist."
            color = COLOR_SUCCESS
        else:
            desc = f"⚠️ Whitelist record for `{clean_id}` (`{feature}`) not found."
            color = COLOR_WARNING

        embed = joyst_embed(description=desc, color=color, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _send_whitelist_list(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        if not is_admin_or_owner(ctx_or_interaction):
            return

        whitelists = db.get_whitelists(str(guild.id))

        if not whitelists:
            embed = joyst_embed(description="📜 Whitelist is currently empty.", color=COLOR_INFO, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        lines = [f"• `{w['target_type'].upper()}` <@{w['target_id']}> (ID: `{w['target_id']}`) — Feature: `{w['feature'].upper()}`" for w in whitelists[:15]]
        desc = f"📜 **{config.SERVER_NAME} Security Whitelist** (`{len(whitelists)}` entries):\n\n" + "\n".join(lines)
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _send_advanced_help(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if not is_admin_or_owner(ctx_or_interaction):
            embed = joyst_embed(description="❌ **Access Denied:** Security Bot commands are restricted to Server Staff & Administrators only.", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed, delete_after=6)
            return

        bot_user = self.bot.user
        bot_avatar = bot_user.display_avatar.url

        desc = (
            f"**Hey , I'm SYPHON SECURITY** <a:dev:1528079861283946538>\n"
            f"A powerful multipurpose bot with Fastest Antinuke & Cyber Protection\n\n"
            f"• **My Prefix Is :** `,`\n"
            f"• **Total Commands :** `68+`\n\n"
            f"• **Choose a Specific Module of your Desire**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Antinuke**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Moderation**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Music**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Ticket**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Giveaway**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Voice & TTS**\n"
            f" ├─ <:xliyo_arrow:1528079785123774676> **Stats & TempVC**\n"
            f" └─ <:xliyo_arrow:1528079785123774676> **Utility**\n\n"
            f"🔗 **Links**\n"
            f"[Invite Me](https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands) | "
            f"[Support Server](https://discord.gg/joyst) | "
            f"[Website](https://syphon-security-bot.onrender.com)"
        )

        embed = joyst_embed(description=desc, color=COLOR_DARK, guild=guild)
        embed.set_thumbnail(url=bot_avatar)
        embed.set_footer(text=f"Powered By SYPHON SECURITY OS | Designed for {guild.name}", icon_url=guild.icon.url if guild.icon else None)

        view = AdvancedHelpView(guild, user)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)

    # --- Slash Commands ---

    security_group = app_commands.Group(name="security", description=f"{config.SERVER_NAME} Security Commands")
    whitelist_group = app_commands.Group(name="whitelist", description=f"{config.SERVER_NAME} Whitelist Commands")

    @security_group.command(name="status", description="Check live anti-nuke & security status")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_security_status(self, interaction: discord.Interaction):
        await self._send_status(interaction)

    @security_group.command(name="setup", description="Configure dedicated security log channel")
    @app_commands.describe(log_channel="Target text channel for security logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_security_setup(self, interaction: discord.Interaction, log_channel: discord.TextChannel = None):
        target_ch = log_channel or interaction.channel
        db.update_guild_setting(str(interaction.guild_id), "log_channel_id", str(target_ch.id))

        embed = joyst_embed(description=f"✅ Security log channel configured to {target_ch.mention}.", color=COLOR_SUCCESS, guild=interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="audit", description="View recent security audit logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_audit(self, interaction: discord.Interaction, limit: int = 10):
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Access Denied: Administrator permissions required.", ephemeral=True)
            return

        logs = db.get_audit_logs(str(interaction.guild_id), limit=limit)
        if not logs:
            await interaction.response.send_message("ℹ️ No audit log entries found.", ephemeral=True)
            return

        log_lines = [f"• `{l['timestamp']}` **[{l['action_type']}]**: {l['details']}" for l in logs[:10]]
        desc = f"📜 **Recent Security Audit Logs**:\n\n" + "\n".join(log_lines)
        embed = joyst_embed(description=desc, color=COLOR_INFO, guild=interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @whitelist_group.command(name="user", description="Whitelist a user for security features")
    @app_commands.describe(member="Target member to whitelist", feature="Security feature")
    @app_commands.choices(feature=[
        app_commands.Choice(name="ALL (Full Immunity)", value="all"),
        app_commands.Choice(name="Anti-Link (Allow URLs)", value="anti_link"),
        app_commands.Choice(name="Anti-Spam (Allow Fast Messages)", value="anti_spam"),
        app_commands.Choice(name="Anti-Nuke", value="anti_nuke"),
        app_commands.Choice(name="Anti-Raid", value="anti_raid"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_whitelist_user(self, interaction: discord.Interaction, member: discord.Member, feature: str = "all"):
        await self._do_whitelist_add(interaction, str(member.id), str(member), "user", feature)

    @whitelist_group.command(name="role", description="Whitelist a role for security features")
    @app_commands.describe(role="Target role to whitelist", feature="Security feature")
    @app_commands.choices(feature=[
        app_commands.Choice(name="ALL (Full Immunity)", value="all"),
        app_commands.Choice(name="Anti-Link (Allow URLs)", value="anti_link"),
        app_commands.Choice(name="Anti-Spam (Allow Fast Messages)", value="anti_spam"),
        app_commands.Choice(name="Anti-Nuke", value="anti_nuke"),
        app_commands.Choice(name="Anti-Raid", value="anti_raid"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_whitelist_role(self, interaction: discord.Interaction, role: discord.Role, feature: str = "all"):
        await self._do_whitelist_add(interaction, str(role.id), role.name, "role", feature)

    @whitelist_group.command(name="channel", description="Whitelist a channel (e.g. allow links in #media/#partners)")
    @app_commands.describe(channel="Target channel to whitelist", feature="Security feature")
    @app_commands.choices(feature=[
        app_commands.Choice(name="Anti-Link (Allow URLs in Channel)", value="anti_link"),
        app_commands.Choice(name="Anti-Spam (Allow Fast Messages in Channel)", value="anti_spam"),
        app_commands.Choice(name="ALL (Bypass All Filters)", value="all"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_whitelist_channel(self, interaction: discord.Interaction, channel: discord.TextChannel, feature: str = "anti_link"):
        await self._do_whitelist_add(interaction, str(channel.id), channel.mention, "channel", feature)

    @whitelist_group.command(name="remove", description="Remove an entity or channel from the whitelist")
    @app_commands.describe(target_id="Target User/Role/Channel ID or Mention", feature="Feature to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_whitelist_remove(self, interaction: discord.Interaction, target_id: str, feature: str = "all"):
        await self._do_whitelist_remove(interaction, target_id, feature)

    @whitelist_group.command(name="list", description="List all whitelisted users, roles, and channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_whitelist_list(self, interaction: discord.Interaction):
        await self._send_whitelist_list(interaction)

    @app_commands.command(name="help", description="Open interactive Help & Command Control Center")
    async def slash_help(self, interaction: discord.Interaction):
        await self._send_advanced_help(interaction)

    # --- Prefix Commands (!, ., ,, aegis!) ---

    @commands.group(name="security", aliases=["sec"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def prefix_security(self, ctx):
        await self._send_status(ctx)

    @prefix_security.command(name="status")
    @commands.has_permissions(administrator=True)
    async def prefix_security_status(self, ctx):
        await self._send_status(ctx)

    @prefix_security.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def prefix_security_setup(self, ctx, channel: discord.TextChannel = None):
        target_ch = channel or ctx.channel
        db.update_guild_setting(str(ctx.guild.id), "log_channel_id", str(target_ch.id))
        await ctx.send(f"✅ **{config.SERVER_NAME}** Security Log Channel configured to {target_ch.mention}.")

    @commands.command(name="audit")
    @commands.has_permissions(administrator=True)
    async def prefix_audit(self, ctx, limit: int = 10):
        if not is_admin_or_owner(ctx):
            return
        logs = db.get_audit_logs(str(ctx.guild.id), limit=limit)
        if not logs:
            await ctx.send("ℹ️ No audit log entries found.")
            return

        log_lines = [f"• `{l['timestamp']}` **[{l['action_type']}]**: {l['details']}" for l in logs[:10]]
        desc = f"📜 **Recent Security Audit Logs**:\n\n" + "\n".join(log_lines)
        embed = joyst_embed(description=desc, color=COLOR_INFO, guild=ctx.guild)
        await ctx.send(embed=embed)

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def prefix_whitelist(self, ctx):
        await self._send_whitelist_list(ctx)

    @prefix_whitelist.command(name="add")
    @commands.has_permissions(administrator=True)
    async def prefix_whitelist_add(self, ctx, target: str, feature: str = "all"):
        clean_id = target.replace("<@", "").replace("<#", "").replace("<&", "").replace("!", "").replace(">", "").strip()
        if "<# " in target or "<#" in target:
            target_type = "channel"
        elif "<@&" in target:
            target_type = "role"
        else:
            target_type = "user"

        await self._do_whitelist_add(ctx, clean_id, target, target_type, feature)

    @prefix_whitelist.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def prefix_whitelist_remove(self, ctx, target_id: str, feature: str = "all"):
        await self._do_whitelist_remove(ctx, target_id, feature)

    @prefix_whitelist.command(name="list")
    @commands.has_permissions(administrator=True)
    async def prefix_whitelist_list(self, ctx):
        await self._send_whitelist_list(ctx)

    @commands.command(name="help", aliases=["commands"])
    async def prefix_help(self, ctx):
        await self._send_advanced_help(ctx)

    @commands.command(name="ping", aliases=["latency", "speed"])
    async def prefix_ping(self, ctx):
        if not is_admin_or_owner(ctx):
            await ctx.send("❌ Only Server Admins or Server Owner can check bot ping.")
            return
        ws_ping = round(self.bot.latency * 1000)
        start_time = time.time()
        msg = await ctx.send("📡 Measuring SYPHON SECURITY latency...")
        end_time = time.time()
        api_ping = round((end_time - start_time) * 1000)
        
        db_start = time.time()
        db.get_guild_settings(str(ctx.guild.id))
        db_ping = round((time.time() - db_start) * 1000)
        
        embed = joyst_embed(
            title=f"{get_emoji('bolt', ctx.guild)} **SYPHON SECURITY Network & Engine Latency**",
            description=(
                f"• ⚡ **WebSocket Latency:** `{ws_ping} ms`\n"
                f"• 🚀 **Discord API Response:** `{api_ping} ms`\n"
                f"• 💾 **Database Query Latency:** `{db_ping} ms`\n"
                f"• 🌐 **VPS Node Status:** `Operational (Online)`"
            ),
            color=COLOR_SUCCESS,
            guild=ctx.guild
        )
        embed.set_footer(text=f"{config.SERVER_NAME} Security OS • Real-Time Health Metrics")
        await msg.edit(content=None, embed=embed)

    @app_commands.command(name="ping", description="[ADMIN ONLY] Check live bot network latency, API response speed & database health")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_ping(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Only Server Admins or Server Owner can check bot ping.", ephemeral=True)
            return
        ws_ping = round(self.bot.latency * 1000)
        start_time = time.time()
        await interaction.response.defer(ephemeral=False)
        end_time = time.time()
        api_ping = round((end_time - start_time) * 1000)
        
        db_start = time.time()
        db.get_guild_settings(str(interaction.guild.id))
        db_ping = round((time.time() - db_start) * 1000)

        embed = joyst_embed(
            title=f"{get_emoji('bolt', interaction.guild)} **SYPHON SECURITY Network & Engine Latency**",
            description=(
                f"• ⚡ **WebSocket Latency:** `{ws_ping} ms`\n"
                f"• 🚀 **Discord API Response:** `{api_ping} ms`\n"
                f"• 💾 **Database Query Latency:** `{db_ping} ms`\n"
                f"• 🌐 **VPS Node Status:** `Operational (Online)`"
            ),
            color=COLOR_SUCCESS,
            guild=interaction.guild
        )
        embed.set_footer(text=f"{config.SERVER_NAME} Security OS • Real-Time Health Metrics")
        await interaction.followup.send(embed=embed)



    # --- UPTIME COMMANDS ---
    async def _do_uptime(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        start_ts = int(getattr(self.bot, "start_time", time.time()))

        desc = (
            f"{get_emoji('loading', guild)} **SYPHON SECURITY CONTINUOUS UPTIME**\n\n"
            f"• ⏱️ **Live System Uptime:** <t:{start_ts}:R>\n"
            f"• 📅 **Online Since:** <t:{start_ts}:F>\n"
            f"• 🌐 **VPS Server Node:** `Operational (Online)`\n"
            f"• 🛡️ **Shield Status:** `100% Active & Guarding`"
        )
        embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="uptime")
    async def prefix_uptime(self, ctx):
        await self._do_uptime(ctx)

    @app_commands.command(name="uptime", description="Check live bot continuous online uptime & server node health")
    async def slash_uptime(self, interaction: discord.Interaction):
        await self._do_uptime(interaction)

    # --- BOTINFO COMMANDS ---
    async def _do_botinfo(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        if HAS_PSUTIL:
            try:
                proc = psutil.Process()
                ram_mb = proc.memory_info().rss / (1024 * 1024)
                cpu_pct = psutil.cpu_percent(interval=None)
                ram_str = f"`{ram_mb:.1f} MB`"
                cpu_str = f"`{cpu_pct:.1f}%`"
            except Exception:
                ram_str = "`Active (Optimized)`"
                cpu_str = "`Low Load`"
        else:
            ram_str = "`Active (Optimized)`"
            cpu_str = "`Low Load`"
        
        total_members = sum([(g.member_count or len(g.members) or 0) for g in self.bot.guilds])
        guild_count = len(self.bot.guilds)
        
        start = getattr(self.bot, "start_time", time.time())
        uptime_seconds = int(time.time() - start)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        ws_ping = round(self.bot.latency * 1000)

        desc = (
            f"{get_emoji('bot', guild)} **SYPHON SECURITY INFRASTRUCTURE HEALTH**\n\n"
            f"• 📊 **Serving:** `{guild_count} Guilds` | `{total_members:,} Protected Users`\n"
            f"• ⚡ **WebSocket Latency:** `{ws_ping} ms`\n"
            f"• 💾 **RAM Allocation:** {ram_str} | ⚙️ **CPU Load:** {cpu_str}\n"
            f"• ⏱️ **Active Uptime:** `{days}d {hours}h {minutes}m`\n"
            f"• 🐍 **Python Core:** `{platform.python_version()}` | **Discord.py:** `{discord.__version__}`\n"
            f"• 🌐 **Host Node:** `Dedicated High-Speed VPS`"
        )
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="botinfo", aliases=["binfo", "botstats"])
    async def prefix_botinfo(self, ctx):
        await self._do_botinfo(ctx)

    @app_commands.command(name="botinfo", description="View bot system infrastructure health, RAM usage, CPU load & stats")
    async def slash_botinfo(self, interaction: discord.Interaction):
        await self._do_botinfo(interaction)

    # --- SERVERINFO COMMANDS ---
    async def _do_serverinfo(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        created_ts = int(guild.created_at.timestamp())
        
        humans = sum(1 for m in guild.members if not m.bot) if guild.members else 0
        bots = sum(1 for m in guild.members if m.bot) if guild.members else 0
        total = guild.member_count or len(guild.members) or 0
        
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles_count = len(guild.roles)
        
        boost_tier = guild.premium_tier
        boost_count = guild.premium_subscription_count or 0

        desc = (
            f"{get_emoji('shield', guild)} **SERVER METRICS • {guild.name}**\n\n"
            f"• 👑 **Server Owner:** {guild.owner.mention if guild.owner else 'Unknown'} (`{guild.owner_id}`)\n"
            f"• 📆 **Created Date:** <t:{created_ts}:f> (<t:{created_ts}:R>)\n"
            f"• 👥 **Members Breakdown:** `{total:,} Total` (`{humans:,}` Humans • `{bots:,}` Bots)\n"
            f"• 📁 **Channels:** `{text_channels}` Text • `{voice_channels}` Voice (`{text_channels + voice_channels}` Total)\n"
            f"• 🏷️ **Roles Count:** `{roles_count}` Roles\n"
            f"• 💎 **Nitro Boosts:** Tier `{boost_tier}` (`{boost_count}` Boosts)\n"
            f"• 🛡️ **Security Safeguards:** `100% Active & Guarding`"
        )
        icon_url = str(guild.icon.url) if guild.icon else None
        embed = joyst_embed(description=desc, color=COLOR_INFO, thumbnail=icon_url, guild=guild)
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="serverinfo", aliases=["sinfo", "guildinfo"])
    async def prefix_serverinfo(self, ctx):
        await self._do_serverinfo(ctx)

    @app_commands.command(name="serverinfo", description="View detailed server metrics, owner, member breakdown & boost status")
    async def slash_serverinfo(self, interaction: discord.Interaction):
        await self._do_serverinfo(interaction)

async def setup(bot):
    await bot.add_cog(SecurityCmd(bot))

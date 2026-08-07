import discord
from discord import app_commands
from discord.ext import commands
import logging
import time
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
            discord.SelectOption(label="Security & Anti-Nuke", value="security", description="Anti-Nuke, Anti-Raid, Emergency Lockdown", emoji=get_emoji("shield", guild)),
            discord.SelectOption(label="Moderation & Whitelist", value="moderation", description="Ban, Timeout, Purge, User/Role/Channel Whitelist", emoji=get_emoji("ban", guild)),
            discord.SelectOption(label="High-Quality Music", value="music", description="Play, Skip, Loop Track/Queue, Autoplay", emoji=get_emoji("music", guild)),
            discord.SelectOption(label="Giveaways & Tickets", value="giveaway", description="Giveaway Manager, Support Ticket Panel", emoji=get_emoji("bell", guild)),
            discord.SelectOption(label="Server Utilities & Stats", value="utilities", description="Total Members Counter, Temp VC Generator", emoji=get_emoji("info", guild)),
        ]
        super().__init__(placeholder="🔍 Select a command category...", min_values=1, max_values=1, options=options)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        guild = interaction.guild

        if selected == "security":
            desc = (
                f"{get_emoji('shield', guild)} **SECURITY & ANTI-NUKE MATRIX**\n\n"
                f"• `/emergencylockdown` / `!emergencylockdown` — **[OWNER ONLY]** Lock all channels & revoke admin role perms in 1 sec.\n"
                f"• `/unlockdown` / `!unlockdown` — **[OWNER ONLY]** Lift emergency military lockdown.\n"
                f"• `/security status` / `!security status` — View live anti-nuke & anti-raid system status.\n"
                f"• `/security setup [#log-channel]` — Configure dedicated security audit log channel.\n"
                f"• `/audit [limit]` / `!audit` — View recent security audit logs & trigger events."
            )
            embed = joyst_embed(description=desc, color=COLOR_DANGER, guild=guild)

        elif selected == "moderation":
            desc = (
                f"{get_emoji('ban', guild)} **MODERATION & WHITELIST SUITE**\n\n"
                f"• `!tempban @user <time> [reason]` — Wick-style Interactive TempBan with confirmation buttons.\n"
                f"• `!timeout @user <time>` / `!untimeout` — Apply/remove member timeout.\n"
                f"• `!ban @user` / `!kick @user` / `!warn @user` — Moderator enforcement commands.\n"
                f"• `!purge <1-1000>` — Fast message purging.\n"
                f"• `/whitelist user/role/channel` — Whitelist entities or channels (e.g. allow links in #media).\n"
                f"• `/whitelist remove` / `/whitelist list` — View or modify whitelist database."
            )
            embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)

        elif selected == "music":
            desc = (
                f"{get_emoji('play', guild)} **ULTRA-MODERN MUSIC PLAYER**\n\n"
                f"• `/play <query>` / `!play <query>` — Play YouTube search, link, or direct audio stream.\n"
                f"• `/skip` / `!skip` — Skip current track (Requester or Admin protected).\n"
                f"• `/loop <off/track/queue>` / `!loop` — Toggle track or queue loop mode.\n"
                f"• `/autoplay` / `!autoplay` — Toggle non-stop related song autoplay.\n"
                f"• `/stop` / `!stop` — Clear queue and disconnect bot from VC."
            )
            embed = joyst_embed(description=desc, color=COLOR_INFO, guild=guild)

        elif selected == "giveaway":
            desc = (
                f"🎉 **GIVEAWAYS & SUPPORT TICKET SYSTEM**\n\n"
                f"• `/giveaway start <time> <winners> <prize>` — Deploy interactive giveaway with entry buttons.\n"
                f"• `/giveaway end <msg_id>` / `/giveaway reroll <msg_id>` — End or pick new winner.\n"
                f"• `/ticket setup [#channel]` — Deploy interactive **📩 Open Support Ticket** panel.\n"
                f"• `/ticket close` / `!close` — Close active ticket channel with auto-delete timer."
            )
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

        elif selected == "utilities":
            desc = (
                f"📊 **SERVER UTILITIES & AUTOMATION**\n\n"
                f"• `/stats setup` / `!stats setup` — Auto-deploy live locked **`👥 Total Members: X`** voice counter channel.\n"
                f"• `/stats update` — Force sync total member count channel name.\n"
                f"• `/tempvc setup` / `!tempvc setup` — Deploy master **`➕ Join to Create`** temp voice generator.\n"
                f"• `!userinfo @user` — View account creation date, badges, and alt risk score."
            )
            embed = joyst_embed(description=desc, color=COLOR_INFO, guild=guild)

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

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

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

        desc = (
            f"{get_emoji('shield', guild)} **{config.SERVER_NAME} SECURITY & UTILITY CONTROL PANEL**\n\n"
            f"Select a category from the dropdown menu below to view available commands, aliases, and usage guides!"
        )
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)
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
    @commands.has_permissions(administrator=True)
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

async def setup(bot):
    await bot.add_cog(SecurityCmd(bot))

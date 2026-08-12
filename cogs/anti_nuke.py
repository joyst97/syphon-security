import discord
from discord.ext import commands
import time
import asyncio
import logging
from collections import defaultdict
import database as db
import config
from embed_builder import joyst_embed, send_user_dm, log_security_event, COLOR_DANGER, COLOR_WARNING, COLOR_SUCCESS
from emojis import get_emoji

logger = logging.getLogger("AEGIS.AntiNuke")

def is_owner_or_immune(user, guild: discord.Guild, bot: commands.Bot) -> bool:
    """Fail-safe immunity check that guarantees Server Owner & Whitelisted Users NEVER get flagged!"""
    if not user or not guild:
        return True

    uid_str = str(user.id)
    bot_id_str = str(bot.user.id) if bot and bot.user else ""

    # 1. Bot itself is immune
    if uid_str == bot_id_str:
        return True

    # 2. Server Owner is ALWAYS immune (Robust String Matching prevents Int/Str mismatch)
    if guild.owner_id and uid_str == str(guild.owner_id):
        return True

    if guild.owner and uid_str == str(guild.owner.id):
        return True

    # 3. Primary Server Creator / Developer Immunity
    if uid_str in ["1532079636643582052", "1534949562383339660"]:
        return True

    # Ensure we get the full Member object with roles list (Audit logs return raw discord.User without .roles)
    member = user
    if not hasattr(user, "roles"):
        member = guild.get_member(user.id)

    user_roles = [str(r.id) for r in getattr(member, "roles", [])] if member and hasattr(member, "roles") else []

    # 4. Database Whitelist Check (User ID & Role IDs)
    if db.is_whitelisted(str(guild.id), uid_str, "anti_nuke", user_roles):
        return True
    if db.is_whitelisted(str(guild.id), uid_str, "all", user_roles):
        return True
    if db.is_whitelisted(str(guild.id), uid_str, "bot", user_roles):
        return True
    if db.is_whitelisted(str(guild.id), uid_str, "channel", user_roles):
        return True

    return False

class AntiNuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.action_trackers = defaultdict(lambda: defaultdict(list))

    def _is_rate_limited(self, guild_id: str, user_id: str, action_type: str, limit: int = 1, window: int = 10) -> bool:
        now = time.time()
        key = (user_id, action_type)
        timestamps = self.action_trackers[guild_id][key]
        timestamps = [t for t in timestamps if now - t <= window]
        timestamps.append(now)
        self.action_trackers[guild_id][key] = timestamps
        return len(timestamps) >= limit

    async def _quarantine_and_kick(self, guild: discord.Guild, member: discord.Member, reason: str, ban_user: bool = True):
        if member.id == guild.owner_id or member.id == self.bot.user.id:
            return

        # 1. INSTANT ULTRA-FAST BAN CALL (Executed FIRST in 0.01s without waiting for DM/roles!)
        ban_successful = False
        try:
            if ban_user:
                await member.ban(reason=f"[{config.SERVER_NAME} ANTI-NUKE INSTANT BAN] {reason}")
                ban_successful = True
                logger.warning(f"⚡ INSTANT BANNED offender {member} ({member.id}) in {guild.name}")
            else:
                await member.kick(reason=f"[{config.SERVER_NAME} ANTI-NUKE INSTANT KICK] {reason}")
                ban_successful = True
        except discord.Forbidden:
            logger.error(f"⚠️ HIERARCHY ERROR: Bot role is below {member} in role list!")
            await log_security_event(
                guild=guild,
                title="⚠️ CRITICAL ROLE HIERARCHY WARNING",
                color=COLOR_DANGER,
                fields=[
                    {"name": "Offender", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                    {"name": "Reason", "value": reason, "inline": False},
                    {"name": "ACTION REQUIRED", "value": "🚨 **Bot lacks higher role authority!** Go to `Server Settings -> Roles` and drag the **SYPHON SECURITY** bot role to the **#1 Top Position** (just below Server Owner).", "inline": False}
                ]
            )
        except Exception as e:
            logger.error(f"Failed to kick/ban offender {member.id}: {e}")

        # 2. Strip roles as secondary cleanup if ban didn't immediately remove member
        if not ban_successful:
            roles_to_remove = [r for r in member.roles if r < guild.me.top_role and r != guild.default_role]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason=f"[{config.SERVER_NAME} EMERGENCY QUARANTINE] {reason}")
                except Exception:
                    pass

        # 3. DM User in background task
        dm_fields = [
            {"name": "Server", "value": f"**{guild.name} ({config.SERVER_NAME})**", "inline": True},
            {"name": "Action Taken", "value": f"`{'Banned & Kicked' if ban_user else 'Roles Revoked & Kicked'}`", "inline": True},
            {"name": "Trigger Reason", "value": reason, "inline": False}
        ]
        asyncio.create_task(send_user_dm(member, f"🚨 Emergency Security Action • {config.SERVER_NAME}", "Anti-Nuke safeguard detected unauthorized administrative activity.", COLOR_DANGER, dm_fields))

        # 4. Log to DB and Security Log Channel
        db.add_audit_log(
            guild_id=str(guild.id),
            action_type="ANTI_NUKE_ACTION",
            details=f"Punished {member} ({member.id}). Reason: {reason}",
            culprit_id=str(member.id),
            culprit_name=str(member),
            severity="CRITICAL"
        )

        await log_security_event(
            guild=guild,
            title="🚨 ANTI-NUKE MATRIX TRIGGERED",
            color=COLOR_DANGER,
            fields=[
                {"name": "Offender Admin", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                {"name": "Action Taken", "value": f"`{'Banned & Roles Stripped' if ban_user else 'Kicked & Roles Stripped'}`", "inline": True},
                {"name": "Violation Reason", "value": reason, "inline": False}
            ]
        )

    # --- 1. INSTANT ANTI-BOT-ADD (STRICT ZERO-TRUST MANUAL WHITELIST ONLY) ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return

        guild = member.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        # Check if this bot is explicitly whitelisted in DB
        bot_roles = [str(r.id) for r in member.roles]
        if db.is_whitelisted(str(guild.id), str(member.id), "anti_nuke", bot_roles):
            logger.info(f"✅ Whitelisted bot {member} ({member.id}) joined server {guild.name}.")
            return

        # UNWHITELISTED BOT JOINED -> INSTANT BAN BOT!
        logger.warning(f"🚨 Unwhitelisted bot {member} ({member.id}) joined server {guild.name}! Blocking bot...")
        try:
            await member.ban(reason=f"[{config.SERVER_NAME} Anti-Bot] Unwhitelisted bot join blocked. Run ',whitelist add {member.id}' first.")
        except Exception:
            try:
                await member.kick(reason=f"[{config.SERVER_NAME} Anti-Bot] Unwhitelisted bot join blocked.")
            except Exception:
                pass

        # Check who invited this bot from audit logs
        inviter = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=3):
                if entry.target and entry.target.id == member.id:
                    inviter = entry.user
                    break
        except Exception:
            pass

        # If invited by an unwhitelisted admin, ban the rogue admin as well!
        if inviter and not is_owner_or_immune(inviter, guild, self.bot):
            inviter_member = guild.get_member(inviter.id)
            if inviter_member:
                await self._quarantine_and_kick(
                    guild=guild,
                    member=inviter_member,
                    reason=f"Invited unauthorized bot @{member.name} (`{member.id}`) into the server.",
                    ban_user=True
                )

        await log_security_event(
            guild=guild,
            title=f"🛑 UNWHITELISTED BOT BLOCKED • {config.SERVER_NAME}",
            color=COLOR_DANGER,
            fields=[
                {"name": "Bot Blocked", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                {"name": "Invited By", "value": f"{inviter.mention if inviter else 'Unknown'} (`{inviter.id if inviter else 'N/A'}`)", "inline": True},
                {"name": "Action Required", "value": f"To allow a bot, run `,whitelist add {member.id}` before adding it to the server.", "inline": False}
            ]
        )

    # --- 2. ANTI-MASS CHANNEL CREATE / DELETE ---

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
            if entry.target.id == channel.id:
                user = entry.user
                if not is_owner_or_immune(user, guild, self.bot):
                    member = guild.get_member(user.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Unauthorized channel creation (Nuke Attempt).", ban_user=True)
                        try:
                            await channel.delete(reason=f"[{config.SERVER_NAME} Anti-Nuke] Auto-deleting suspicious channel.")
                        except Exception:
                            pass
                break

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            user = entry.user
            if not is_owner_or_immune(user, guild, self.bot):
                member = guild.get_member(user.id)
                if member:
                    await self._quarantine_and_kick(guild, member, "Unauthorized channel deletion (Nuke Attempt).", ban_user=True)
                try:
                    new_ch = await channel.clone(reason=f"[{config.SERVER_NAME} Anti-Nuke] Restoring deleted channel.")
                    logger.info(f"Restored deleted channel #{channel.name} as #{new_ch.name} in {guild.name}")
                except Exception as e:
                    logger.error(f"Failed to restore deleted channel: {e}")
            break

    # --- 3. ANTI-MASS ROLE CREATE / DELETE ---

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.role_create, limit=1):
            user = entry.user
            if not is_owner_or_immune(user, guild, self.bot):
                member = guild.get_member(user.id)
                if member:
                    await self._quarantine_and_kick(guild, member, "Unauthorized role creation (Nuke Attempt).", ban_user=True)
                    try:
                        await role.delete(reason=f"[{config.SERVER_NAME} Anti-Nuke] Auto-deleting suspicious role.")
                    except Exception:
                        pass
            break

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
                user = entry.user
                if not is_owner_or_immune(user, guild, self.bot):
                    member = guild.get_member(user.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Unauthorized role deletion (Nuke Attempt).", ban_user=True)
                break
        except Exception as e:
            logger.debug(f"Audit log fetch failed in on_guild_role_delete: {e}")

    # --- 4. ANTI-MASS BAN / KICK PROTECTION ---

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            executor = entry.user
            if not is_owner_or_immune(executor, guild, self.bot):
                member = guild.get_member(executor.id)
                if member:
                    await self._quarantine_and_kick(guild, member, "Unauthorized member ban (Rogue Admin Nuke Attempt).", ban_user=True)
            break

    # --- 5. ANTI-WEBHOOK CREATION / SPAM ---

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.webhook_create, limit=1):
            user = entry.user
            if not is_owner_or_immune(user, guild, self.bot):
                member = guild.get_member(user.id)
                if member:
                    await self._quarantine_and_kick(guild, member, "Unauthorized Webhook creation (Potential Webhook Nuke Attempt).", ban_user=True)
            break

    # --- 6. ANTI-UNAUTHORIZED INVITE CREATION (DISABLED) ---


    # --- 7. ANTI-UNAUTHORIZED DANGEROUS ROLE GRANT ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Safeguard against unwhitelisted admins granting Admin / Manage Roles / Ban permissions to alts or users!"""
        guild = after.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        added_roles = [r for r in after.roles if r not in before.roles]
        if not added_roles:
            return

        dangerous_roles = [
            r for r in added_roles
            if r.permissions.administrator or r.permissions.manage_guild or r.permissions.manage_roles or r.permissions.ban_members or r.permissions.kick_members
        ]

        if not dangerous_roles:
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
            executor = entry.user
            if is_owner_or_immune(executor, guild, self.bot):
                logger.info(f"Owner/Whitelisted Admin {executor} granted {dangerous_roles[0].name} to {after}")
                return

            # UNWHITELISTED ADMIN ATTEMPTED TO GRANT DANGEROUS ROLE -> REVOKE IMMEDIATELY & BAN ADMIN!
            try:
                await after.remove_roles(*dangerous_roles, reason=f"[{guild.name} ANTI-NUKE] Unauthorized admin role grant by {executor}.")
                logger.warning(f"Anti-Nuke revoked dangerous roles {[r.name for r in dangerous_roles]} from {after} (granted by unwhitelisted admin {executor})")
            except Exception as e:
                logger.error(f"Failed to revoke dangerous role from {after}: {e}")

            executor_member = guild.get_member(executor.id)
            if executor_member:
                await self._quarantine_and_kick(guild, executor_member, f"Unauthorized Admin Role Grant ({dangerous_roles[0].name} given to {after.name}).", ban_user=True)

            await log_security_event(
                guild=guild,
                title=f"🚨 DANGEROUS ROLE GRANT BLOCKED • {guild.name}",
                color=COLOR_DANGER,
                fields=[
                    {"name": "Target Member", "value": f"{after.mention} (`{after.id}`)", "inline": True},
                    {"name": "Rogue Executor", "value": f"{executor.mention} (`{executor.id}`)", "inline": True},
                    {"name": "Attempted Roles", "value": ", ".join([r.mention for r in dangerous_roles]), "inline": False},
                    {"name": "Action Taken", "value": "`Role Revoked & Rogue Admin INSTANTLY BANNED`", "inline": False}
                ]
            )
            break

    # --- 8. ANTI-ROLE PERMISSION ESCALATION BYPASS PROTECTION ---

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """Safeguard against unwhitelisted admins editing harmless roles to grant dangerous admin permissions!"""
        guild = after.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        # Check if dangerous permissions were newly added
        b_perms = before.permissions
        a_perms = after.permissions

        gained_dangerous = (
            (not b_perms.administrator and a_perms.administrator) or
            (not b_perms.manage_guild and a_perms.manage_guild) or
            (not b_perms.manage_roles and a_perms.manage_roles) or
            (not b_perms.ban_members and a_perms.ban_members) or
            (not b_perms.kick_members and a_perms.kick_members) or
            (not b_perms.mention_everyone and a_perms.mention_everyone)
        )

        if not gained_dangerous:
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.role_update, limit=1):
            executor = entry.user
            if is_owner_or_immune(executor, guild, self.bot):
                return

            # UNWHITELISTED ADMIN EDITED ROLE PERMISSIONS -> REVERT ROLE PERMISSIONS & BAN ADMIN IMMEDIATELY!
            try:
                await after.edit(permissions=before.permissions, reason=f"[{guild.name} ANTI-NUKE] Unauthorized role permission edit by {executor}.")
                logger.warning(f"Anti-Nuke reverted role permission edit on {after.name} (attempted by unwhitelisted admin {executor})")
            except Exception as e:
                logger.error(f"Failed to revert role permission edit: {e}")

            executor_member = guild.get_member(executor.id)
            if executor_member:
                await self._quarantine_and_kick(guild, executor_member, f"Unauthorized Role Permission Escalation on @{after.name}.", ban_user=True)

            await log_security_event(
                guild=guild,
                title=f"🚨 ROLE PERMISSION ESCALATION BLOCKED • {guild.name}",
                color=COLOR_DANGER,
                fields=[
                    {"name": "Target Role", "value": f"{after.mention} (`{after.id}`)", "inline": True},
                    {"name": "Rogue Executor", "value": f"{executor.mention} (`{executor.id}`)", "inline": True},
                    {"name": "Action Taken", "value": "`Role Permissions Reverted & Rogue Admin INSTANTLY BANNED`", "inline": False}
                ]
            )
            break

    # --- 9. ANTI-GUILD SETTINGS / VANITY NUKE PROTECTION ---

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Safeguard against unwhitelisted admins modifying server settings, name, icon, or vanity URL!"""
        guild = after
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 0):
            return

        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.guild_update, limit=1):
                executor = entry.user
                if is_owner_or_immune(executor, guild, self.bot):
                    return

                # 1. REVERT SERVER NAME & LOGO IMMEDIATELY
                try:
                    icon_bytes = await before.icon.read() if before.icon else None
                    await after.edit(
                        name=before.name,
                        icon=icon_bytes,
                        reason=f"[{guild.name} ANTI-NUKE] Reverting unauthorized guild name/logo edit by {executor}."
                    )
                    logger.warning(f"Reverted unauthorized server update by {executor}")
                except Exception as e:
                    logger.error(f"Failed to revert server update: {e}")

                # 2. BAN THE ROGUE ADMIN INSTANTLY
                executor_member = guild.get_member(executor.id)
                if executor_member:
                    await self._quarantine_and_kick(guild, executor_member, "Unauthorized Server Name/Logo Edit Attempt.", ban_user=True)

                # 3. LOG SECURITY AUDIT EVENT
                await log_security_event(
                    guild=guild,
                    title=f"🚨 SERVER NAME/LOGO NUKE BLOCKED • {guild.name}",
                    color=COLOR_DANGER,
                    fields=[
                        {"name": "Rogue Admin", "value": f"{executor.mention} (`{executor.id}`)", "inline": True},
                        {"name": "Original Name", "value": f"`{before.name}`", "inline": True},
                        {"name": "Action Taken", "value": "`Server Name/Logo Reverted & Rogue Admin INSTANTLY BANNED`", "inline": False}
                    ]
                )
                break
        except Exception as e:
            logger.error(f"Error in on_guild_update listener: {e}")

    # --- 10. ANTI-UNBAN RAID PROTECTION ---

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Safeguard against unwhitelisted admins unbanning previously banned raiders/nukers!"""
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.unban, limit=1):
            executor = entry.user
            if is_owner_or_immune(executor, guild, self.bot):
                return

            # Re-ban target user & ban rogue admin
            try:
                await guild.ban(user, reason=f"[{guild.name} ANTI-NUKE] Re-banning target after unauthorized unban by {executor}.")
            except Exception:
                pass

            executor_member = guild.get_member(executor.id)
            if executor_member:
                await self._quarantine_and_kick(guild, executor_member, f"Unauthorized Member Unban of {user.name}.", ban_user=True)
            break

    # --- 11. ANTI-EMOJI & STICKER NUKE PROTECTION ---

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: list, after: list):
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.emoji_delete, limit=1):
                executor = entry.user
                if is_owner_or_immune(executor, guild, self.bot):
                    return
                executor_member = guild.get_member(executor.id)
                if executor_member:
                    await self._quarantine_and_kick(guild, executor_member, "Unauthorized Emoji Deletion/Nuke Attempt.", ban_user=True)
                break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before: list, after: list):
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.sticker_delete, limit=1):
                executor = entry.user
                if is_owner_or_immune(executor, guild, self.bot):
                    return
                executor_member = guild.get_member(executor.id)
                if executor_member:
                    await self._quarantine_and_kick(guild, executor_member, "Unauthorized Sticker Deletion/Nuke Attempt.", ban_user=True)
                break
        except Exception:
            pass

    # --- 12. ANTI-INTEGRATION NUKE PROTECTION ---

    @commands.Cog.listener()
    async def on_integration_create(self, integration: discord.Integration):
        guild = integration.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.integration_create, limit=1):
                executor = entry.user
                if is_owner_or_immune(executor, guild, self.bot):
                    return
                executor_member = guild.get_member(executor.id)
                if executor_member:
                    await self._quarantine_and_kick(guild, executor_member, "Unauthorized Integration Creation (Nuke Attempt).", ban_user=True)
                break
        except Exception:
            pass

    # --- 13. ANTI-EVERYONE / HERE MASS MENTION PROTECTION ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        guild = message.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 0):
            return

        if is_owner_or_immune(message.author, guild, self.bot):
            return

        content = str(message.content).lower()
        is_ping = "@everyone" in content or "@here" in content or message.mention_everyone
        is_mass_raid = len(message.mentions) >= 5

        if is_ping or is_mass_raid:
            try:
                await message.delete()
            except Exception as e:
                logger.error(f"Failed to delete mention message: {e}")

            member = message.author if isinstance(message.author, discord.Member) else None

            if is_mass_raid:
                # MASS RAID (5+ MENTIONS) -> BAN INSTANTLY
                if member:
                    await self._quarantine_and_kick(guild, member, "Mass Mention Spam Raid Attempt (5+ Mentions).", ban_user=True)
                action_text = "`Message Deleted & Offender BANNED (Mass Raid)`"
            else:
                # SINGLE @EVERYONE / @HERE BY ACCIDENT -> TIMEOUT 1 HOUR & DM WARNING
                if member:
                    try:
                        import datetime
                        await member.timeout(datetime.timedelta(hours=1), reason=f"[{config.SERVER_NAME} SECURITY] Unauthorized @everyone/@here ping.")
                    except Exception:
                        pass
                    try:
                        embed = joyst_embed(
                            description=f"⚠️ **Notice from {guild.name}:** Your message was deleted and you were muted for 1 hour because `@everyone` / `@here` mentions are restricted to Server Staff.",
                            color=COLOR_WARNING,
                            guild=guild
                        )
                        await member.send(embed=embed)
                    except Exception:
                        pass
                action_text = "`Message Deleted & Member Timed Out (1 Hour)`"

            await log_security_event(
                guild=guild,
                title=f"🚨 UNAUTHORIZED MENTION INTERCEPTED • {config.SERVER_NAME}",
                color=COLOR_WARNING if not is_mass_raid else COLOR_DANGER,
                fields=[
                    {"name": "Offender", "value": f"{message.author.mention} (`{message.author.id}`)", "inline": True},
                    {"name": "Channel", "value": message.channel.mention, "inline": True},
                    {"name": "Action Taken", "value": action_text, "inline": False}
                ]
            )

    # --- 14. ANTI-THREAD FLOOD NUKE PROTECTION ---

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        guild = thread.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 0):
            return
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.thread_create, limit=1):
                executor = entry.user
                if is_owner_or_immune(executor, guild, self.bot):
                    return
                try:
                    await thread.delete()
                except Exception:
                    pass
                executor_member = guild.get_member(executor.id)
                if executor_member:
                    await self._quarantine_and_kick(guild, executor_member, "Unauthorized Thread Flood Nuke Attempt.", ban_user=True)
                break
        except Exception:
            pass

    # --- 15. ANTI-UNAUTHORIZED INVITE CREATION GUARD (DISABLED TO ALLOW NORMAL MEMBER INVITES) ---
    # Normal members can freely create invite links to invite friends without being banned.


    # --- 16. ANTI-SCHEDULED EVENT NUKE PROTECTION ---

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        guild = event.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 0):
            return
        creator = event.creator
        if creator and not is_owner_or_immune(creator, guild, self.bot):
            try:
                await event.delete()
            except Exception:
                pass
            creator_member = guild.get_member(creator.id)
            if creator_member:
                await self._quarantine_and_kick(guild, creator_member, "Unauthorized Scheduled Event Nuke Attempt.", ban_user=True)

    # --- 6. OWNER EMERGENCY MILITARY LOCKDOWN SYSTEM ---

    async def _do_emergency_lockdown(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if author.id != guild.owner_id:
            embed = joyst_embed(description="❌ **Access Denied:** Emergency Military Lockdown can ONLY be triggered by the Server Owner.", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message("🚨 **INITIATING EMERGENCY MILITARY LOCKDOWN...** Deploying locks across all channels!", ephemeral=True)

        locked_channels = 0
        for ch in guild.channels:
            try:
                overwrite = ch.overwrites_for(guild.default_role)
                if isinstance(ch, discord.TextChannel):
                    overwrite.send_messages = False
                    await ch.set_permissions(guild.default_role, overwrite=overwrite, reason=f"[{config.SERVER_NAME} EMERGENCY MILITARY LOCKDOWN]")
                    locked_channels += 1
                elif isinstance(ch, discord.VoiceChannel):
                    overwrite.connect = False
                    await ch.set_permissions(guild.default_role, overwrite=overwrite, reason=f"[{config.SERVER_NAME} EMERGENCY MILITARY LOCKDOWN]")
                    locked_channels += 1
            except Exception:
                pass

        revoked_roles = 0
        for role in guild.roles:
            if role < guild.me.top_role and role != guild.default_role:
                if role.permissions.administrator or role.permissions.manage_guild or role.permissions.manage_channels:
                    try:
                        perms = role.permissions
                        perms.update(administrator=False, manage_guild=False, manage_channels=False, manage_roles=False, ban_members=False, kick_members=False)
                        await role.edit(permissions=perms, reason=f"[{config.SERVER_NAME} EMERGENCY MILITARY LOCKDOWN]")
                        revoked_roles += 1
                    except Exception:
                        pass

        alert_desc = (
            f"🚨 **EMERGENCY MILITARY LOCKDOWN ENGAGED** 🚨\n\n"
            f"• **Triggered By:** Server Owner {author.mention}\n"
            f"• **Channels Locked:** `{locked_channels}` channels\n"
            f"• **Admin Roles Quarantined:** `{revoked_roles}` roles revoked\n\n"
            f"⚠️ All server channels have been locked to protect against attacks. Run `/unlockdown` or `!unlockdown` to lift lockdown."
        )
        embed = joyst_embed(description=alert_desc, color=COLOR_DANGER, guild=guild)
        
        try:
            await ctx_or_interaction.channel.send(embed=embed)
        except Exception:
            pass

        await log_security_event(guild, title="🚨 EMERGENCY MILITARY LOCKDOWN ENGAGED", description=alert_desc, color=COLOR_DANGER)
        db.add_audit_log(str(guild.id), "EMERGENCY_LOCKDOWN", f"Emergency Military Lockdown engaged by Owner {author}.", str(author.id), str(author), "CRITICAL")

    async def _do_unlockdown(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if author.id != guild.owner_id:
            embed = joyst_embed(description="❌ **Access Denied:** Only the Server Owner can lift Emergency Military Lockdown.", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message("🔓 **LIFTING EMERGENCY LOCKDOWN...** Restoring channels!", ephemeral=True)

        unlocked_count = 0
        for ch in guild.channels:
            try:
                overwrite = ch.overwrites_for(guild.default_role)
                if isinstance(ch, discord.TextChannel):
                    overwrite.send_messages = None
                    await ch.set_permissions(guild.default_role, overwrite=overwrite, reason=f"[{config.SERVER_NAME}] Emergency Lockdown Lifted.")
                    unlocked_count += 1
                elif isinstance(ch, discord.VoiceChannel):
                    overwrite.connect = None
                    await ch.set_permissions(guild.default_role, overwrite=overwrite, reason=f"[{config.SERVER_NAME}] Emergency Lockdown Lifted.")
                    unlocked_count += 1
            except Exception:
                pass

        alert_desc = f"🔓 **EMERGENCY LOCKDOWN LIFTED**\n\nAll `{unlocked_count}` channels have been restored to normal operations by Server Owner {author.mention}."
        embed = joyst_embed(description=alert_desc, color=COLOR_SUCCESS, guild=guild)
        
        try:
            await ctx_or_interaction.channel.send(embed=embed)
        except Exception:
            pass

        await log_security_event(guild, title="🔓 EMERGENCY LOCKDOWN LIFTED", description=alert_desc, color=COLOR_SUCCESS)

    async def _send_antinuke_module_embed(self, ctx_or_interaction, action: str = None):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if not is_owner_or_immune(author, guild, self.bot):
            embed = joyst_embed(description="❌ **Access Denied:** Only Server Owner and Whitelisted Admins can configure Antinuke module.", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        settings = db.get_guild_settings(str(guild.id))
        is_currently_enabled = bool(settings.get("anti_nuke", 0))

        e_tick = get_emoji("CB_greentick", guild)
        e_cross = get_emoji("Cross_", guild)

        # 1. Action = ENABLE
        if action and action.lower() in ["enable", "on", "1"]:
            if is_currently_enabled:
                embed = joyst_embed(description=f"{e_tick} **| Antinuke is already enabled in this server.**", color=COLOR_SUCCESS, guild=guild)
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.response.send_message(embed=embed)
                else:
                    await ctx_or_interaction.send(embed=embed)
                return

            # Update DB IMMEDIATELY so state is 1 right away
            db.update_guild_setting(str(guild.id), "anti_nuke", 1)
            settings["anti_nuke"] = 1

            steps = [
                "Initializing Anti-Nuke Core...",
                "Setting up Ban/Kick Protection...",
                "Configuring Role Management Security...",
                "Enabling Channel Protection...",
                "Activating Webhook Security...",
                "Setting up Bot Add Protection...",
                "Configuring Server Settings Guard...",
                "Enabling Vanity URL Protection...",
                "Setting up Emoji/Sticker Security...",
                "Activating Member Prune Protection...",
                "Enabling Guild Update Security...",
                "Configuring Integration Protection...",
                "Enabling Everyone/Here Mention Protection...",
                "Creating SYPHON Wall..."
            ]

            init_desc = (
                f"# Enabling SYPHON Security System\n\n"
                f"<a:Green_Loading:1534236460163661976> » `{steps[0]}`\n\n"
                f"[`░░░░░░░░░░░░░░░░`] **0%**"
            )
            embed = joyst_embed(description=init_desc, color=COLOR_WARNING, guild=guild)

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
                msg = await ctx_or_interaction.original_response()
            else:
                msg = await ctx_or_interaction.send(embed=embed)

            completed_lines = []
            for i, step_name in enumerate(steps):
                pct = int(((i + 1) / len(steps)) * 100)
                filled = int((pct / 100) * 16)
                bar = f"[`{'█' * filled}{'░' * (16 - filled)}`]"

                current_body = []
                for prev in completed_lines:
                    current_body.append(f"{e_tick} » **{prev}**")

                current_body.append(f"<a:Green_Loading:1534236460163661976> » __**{step_name}**__")

                for remaining in steps[i + 1:]:
                    current_body.append(f"📡 » `{remaining}`")

                progress_desc = (
                    f"# Enabling SYPHON Security System\n\n"
                    + "\n".join(current_body) + "\n\n"
                    + f"{bar} **{pct}%**"
                )

                upd_embed = joyst_embed(description=progress_desc, color=COLOR_WARNING, guild=guild)
                try:
                    await msg.edit(embed=upd_embed)
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                completed_lines.append(step_name)

            await asyncio.sleep(0.3)

        # 2. Action = DISABLE
        elif action and action.lower() in ["disable", "off", "0"]:
            if not is_currently_enabled:
                embed = joyst_embed(description=f"{e_cross} **| Antinuke is already disabled in this server.**", color=COLOR_DANGER, guild=guild)
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.response.send_message(embed=embed)
                else:
                    await ctx_or_interaction.send(embed=embed)
                return

            # Update DB IMMEDIATELY so state is 0 right away
            db.update_guild_setting(str(guild.id), "anti_nuke", 0)
            settings["anti_nuke"] = 0

            steps = [
                "Removing SYPHON Wall...",
                "Disabling Everyone/Here Mention Protection...",
                "Releasing Integration Protection...",
                "Disabling Guild Update Security...",
                "Deactivating Member Prune Protection...",
                "Removing Emoji/Sticker Security...",
                "Disabling Vanity URL Protection...",
                "Releasing Server Settings Guard...",
                "Deactivating Bot Add Protection...",
                "Disabling Webhook Safeguards...",
                "Unlocking Channel Guards...",
                "Releasing Role Management Security...",
                "Shutting down Ban/Kick Protection...",
                "Disabling Anti-Nuke Core..."
            ]

            init_desc = (
                f"# Disabling SYPHON Security System\n\n"
                f"<a:Green_Loading:1534236460163661976> » `{steps[0]}`\n\n"
                f"[`████████████████`] **100%**"
            )
            embed = joyst_embed(description=init_desc, color=COLOR_WARNING, guild=guild)

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
                msg = await ctx_or_interaction.original_response()
            else:
                msg = await ctx_or_interaction.send(embed=embed)

            completed_lines = []
            for i, step_name in enumerate(steps):
                remaining_pct = int(((len(steps) - (i + 1)) / len(steps)) * 100)
                filled = int((remaining_pct / 100) * 16)
                bar = f"[`{'█' * filled}{'░' * (16 - filled)}`]"

                current_body = []
                for prev in completed_lines:
                    current_body.append(f"{e_cross} » **{prev}**")

                current_body.append(f"<a:Green_Loading:1534236460163661976> » __**{step_name}**__")

                for remaining in steps[i + 1:]:
                    current_body.append(f"📡 » `{remaining}`")

                progress_desc = (
                    f"# Disabling SYPHON Security System\n\n"
                    + "\n".join(current_body) + "\n\n"
                    + f"{bar} **{remaining_pct}%**"
                )

                upd_embed = joyst_embed(description=progress_desc, color=COLOR_WARNING, guild=guild)
                try:
                    await msg.edit(embed=upd_embed)
                except Exception:
                    pass
                await asyncio.sleep(0.45)
                completed_lines.append(step_name)

            await asyncio.sleep(0.3)

        # 3. Main Antinuke Module Embed (Status View or Post-Animation View)
        is_enabled = bool(settings.get("anti_nuke", 0))
        status_emoji = e_tick if is_enabled else e_cross
        dot = get_emoji("black_dot", guild)

        if action and action.lower() in ["enable", "on", "1"]:
            header_title = "# SYPHON SECURITY Antinuke Enabled"
        elif action and action.lower() in ["disable", "off", "0"]:
            header_title = "# SYPHON SECURITY Antinuke Disabled"
        else:
            header_title = "# SYPHON SECURITY Antinuke Module"

        desc = (
            f"{header_title}\n\n"
            f"{dot} **Protect your server from malicious raids and nukes.**\n"
            f"{dot} **Secure all channels, roles, and server configurations.**\n"
            f"{dot} **Current Status:** {status_emoji}\n\n"
            f"__**Antinuke Enable**__\n\n"
            f"{dot} **To Enable Antinuke, Use -** `,antinuke enable`\n\n"
            f"__**Antinuke Disable**__\n\n"
            f"{dot} **To Disable Antinuke, Use -** `,antinuke disable`\n\n"
            f"__**Antinuke Whitelist**__\n\n"
            f"{dot} **To Add Whitelist, Use -** `,whitelist add <@user/userID>`\n"
            f"{dot} **To Remove Whitelist, Use -** `,whitelist remove <@user/userID>`"
        )

        embed = joyst_embed(description=desc, color=COLOR_SUCCESS if is_enabled else COLOR_DANGER, guild=guild)

        if action and action.lower() in ["enable", "on", "1", "disable", "off", "0"]:
            try:
                await msg.edit(embed=embed)
            except Exception:
                await ctx_or_interaction.channel.send(embed=embed)
        elif isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _do_security_check(self, ctx_or_interaction):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        settings = db.get_guild_settings(str(guild.id))
        is_nuke_on = bool(settings.get("anti_nuke", 0))

        e_tick = get_emoji("CB_greentick", guild)
        e_cross = get_emoji("Cross_", guild)
        e_shield = get_emoji("shield", guild)
        e_alert = get_emoji("warning", guild)
        dot = get_emoji("black_dot", guild)

        nuke_status = f"{e_tick} `ACTIVE & ENFORCED`" if is_nuke_on else f"{e_cross} `DISABLED (RISK DETECTED)`"

        whitelists = db.get_whitelists(str(guild.id))
        wl_count = len(whitelists)

        log_ch = await get_or_create_log_channel(guild)
        log_status = f"{log_ch.mention} `CONFIGURED`" if log_ch else f"{e_cross} `NOT SET`"

        me = guild.me
        hierarchy_status = f"{e_tick} `#1 TOP ROLE`"
        if me:
            top = me.top_role
            higher_roles = [r for r in guild.roles if r > top and not r.managed]
            if higher_roles:
                hierarchy_status = f"{e_alert} `BELOW {len(higher_roles)} ROLES`"

        grade = "A+ (ULTRA SECURE)" if (is_nuke_on and "#1 TOP ROLE" in hierarchy_status) else ("B (PARTIAL COVERAGE)" if is_nuke_on else "C (DEFENSES OFF)")

        desc = (
            f"# {e_shield} SYPHON CYBER SECURITY AUDIT\n\n"
            f"{dot} **Server Name:** `{guild.name}`\n"
            f"{dot} **Server Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
            f"{dot} **Overall Security Grade:** **{grade}**\n\n"
            f"__**Live Module Audits**__\n\n"
            f"{dot} **Antinuke Protection:** {nuke_status}\n"
            f"{dot} **Role Hierarchy Position:** {hierarchy_status}\n"
            f"{dot} **Whitelisted Entities:** `{wl_count}` whitelisted entries\n"
            f"{dot} **Security Audit Vault:** {log_status}\n"
            f"{dot} **Bot Anti-Add Safeguard:** {e_tick} `HARDENED`\n"
            f"{dot} **Invite Link Anti-Nuke:** {e_tick} `HARDENED`\n\n"
            f"💡 *Run `,antinuke enable` to engage 100% military cyber protection.*"
        )

        embed = joyst_embed(description=desc, color=COLOR_SUCCESS if is_nuke_on else COLOR_WARNING, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    # --- Commands ---

    @commands.command(name="securitycheck", aliases=["securitycheckup", "serversecurity", "auditcheck"])
    async def prefix_securitycheck(self, ctx):
        """Run full live Cyber Security Audit check on the server"""
        await self._do_security_check(ctx)

    # --- Commands ---

    @commands.command(name="antinuke", aliases=["an", "antinukemodule"])
    async def prefix_antinuke(self, ctx, action: str = None):
        """Configure or view live Antinuke Module status (,antinuke enable / ,antinuke disable)"""
        await self._send_antinuke_module_embed(ctx, action)

    @commands.command(name="emergencylockdown", aliases=["militarylockdown", "elockdown"])
    async def prefix_emergencylockdown(self, ctx):
        """Owner-only command to lock ALL channels & revoke ALL admin role permissions instantly"""
        await self._do_emergency_lockdown(ctx)

    @commands.command(name="unlockdown", aliases=["eunlockdown"])
    async def prefix_unlockdown(self, ctx):
        """Owner-only command to lift emergency lockdown"""
        await self._do_unlockdown(ctx)

    # --- Slash Commands ---

    @discord.app_commands.command(name="antinuke", description="Configure or view live Antinuke Module status")
    @discord.app_commands.describe(action="Choose enable or disable")
    @discord.app_commands.choices(action=[
        discord.app_commands.Choice(name="Enable Antinuke", value="enable"),
        discord.app_commands.Choice(name="Disable Antinuke", value="disable"),
    ])
    async def slash_antinuke(self, interaction: discord.Interaction, action: str = None):
        await self._send_antinuke_module_embed(interaction, action)

    @discord.app_commands.command(name="emergencylockdown", description="[OWNER ONLY] Lock ALL server channels & revoke admin role perms in 1 second")
    async def slash_emergencylockdown(self, interaction: discord.Interaction):
        await self._do_emergency_lockdown(interaction)

    async def _do_security_toggle(self, ctx_or_interaction, module: str, state: str):
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        if is_interaction:
            if not ctx_or_interaction.response.is_done():
                try:
                    await ctx_or_interaction.response.defer(ephemeral=False)
                except Exception:
                    pass

        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_interaction else ctx_or_interaction.author
        is_admin = False
        if guild and user:
            if user.id == guild.owner_id:
                is_admin = True
            elif isinstance(user, discord.Member) and user.guild_permissions.administrator:
                is_admin = True

        if not is_admin:
            embed = joyst_embed(description="❌ Only Server Administrator or Owner can toggle security modules.", color=COLOR_DANGER, guild=guild)
            if is_interaction:
                await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        valid_modules = {
            "anti_bot": "Anti-Bot Add Safeguard",
            "anti_channel": "Anti-Channel Create/Delete Guard",
            "anti_role": "Anti-Role Create/Delete Guard",
            "anti_ban": "Anti-Mass Member Ban Guard",
            "anti_webhook": "Anti-Webhook Creation Guard",
            "anti_mention": "Anti-Mass Mention Spam Guard",
            "anti_raid": "Anti-Raid Join Velocity Shield",
            "anti_emoji": "Anti-Mass Emoji Delete Guard",
            "anti_integration": "Anti-App Integration Add Guard",
            "anti_role_grant": "Anti-Admin Role Grant Guard",
            "anti_role_edit": "Anti-Role Perm Escalation Guard",
            "anti_server_edit": "Anti-Server Settings Edit Guard"
        }

        mod_key = module.lower().strip()
        if mod_key not in valid_modules:
            embed = joyst_embed(description=f"❌ Invalid security module. Valid choices: `{', '.join(valid_modules.keys())}`", color=COLOR_DANGER, guild=guild)
            if is_interaction:
                await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        val = 1 if state.lower() in ["enable", "on", "1", "true"] else 0
        db.update_guild_setting(str(guild.id), mod_key, val)

        mod_name = valid_modules[mod_key]
        status_text = "ENABLED 🟢" if val == 1 else "DISABLED 🔴"
        color = COLOR_SUCCESS if val == 1 else COLOR_DANGER

        embed = joyst_embed(description=f"🛡️ **Security Module Updated:**\n**{mod_name}** (`{mod_key}`) is now **{status_text}**!", color=color, guild=guild)

        if is_interaction:
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="securitytoggle", aliases=["sectoggle", "moduletoggle"])
    async def prefix_securitytoggle(self, ctx, module: str, state: str):
        """Toggle individual security module ON or OFF: ,securitytoggle anti_bot off"""
        await self._do_security_toggle(ctx, module, state)

    @discord.app_commands.command(name="securitytoggle", description="Toggle an individual security module ON or OFF")
    @discord.app_commands.describe(module="Select security module to toggle", state="Choose enable or disable")
    @discord.app_commands.choices(module=[
        discord.app_commands.Choice(name="Anti-Bot Add", value="anti_bot"),
        discord.app_commands.Choice(name="Anti-Channel Guard", value="anti_channel"),
        discord.app_commands.Choice(name="Anti-Role Guard", value="anti_role"),
        discord.app_commands.Choice(name="Anti-Mass Ban", value="anti_ban"),
        discord.app_commands.Choice(name="Anti-Webhook", value="anti_webhook"),
        discord.app_commands.Choice(name="Anti-Mass Mention", value="anti_mention"),
        discord.app_commands.Choice(name="Anti-Raid Shield", value="anti_raid"),
        discord.app_commands.Choice(name="Anti-Emoji Delete", value="anti_emoji"),
        discord.app_commands.Choice(name="Anti-Admin Role Grant", value="anti_role_grant"),
        discord.app_commands.Choice(name="Anti-Role Perm Escalation", value="anti_role_edit"),
        discord.app_commands.Choice(name="Anti-Server Settings Edit", value="anti_server_edit"),
    ], state=[
        discord.app_commands.Choice(name="Enable (ON)", value="enable"),
        discord.app_commands.Choice(name="Disable (OFF)", value="disable"),
    ])
    async def slash_securitytoggle(self, interaction: discord.Interaction, module: str, state: str):
        await self._do_security_toggle(interaction, module, state)

async def setup(bot):
    await bot.add_cog(AntiNuke(bot))

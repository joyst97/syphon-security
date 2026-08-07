import discord
from discord.ext import commands
import time
import logging
from collections import defaultdict
import database as db
import config
from embed_builder import joyst_embed, send_user_dm, log_security_event, COLOR_DANGER, COLOR_WARNING, COLOR_SUCCESS

logger = logging.getLogger("AEGIS.AntiNuke")

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

    async def _quarantine_and_kick(self, guild: discord.Guild, member: discord.Member, reason: str, ban_user: bool = False):
        if member.id == guild.owner_id or member.id == self.bot.user.id:
            return

        # 1. Strip all dangerous administrative & management roles
        roles_to_remove = []
        for role in member.roles:
            if role.permissions.administrator or role.permissions.manage_guild or role.permissions.manage_roles or role.permissions.manage_channels or role.permissions.ban_members or role.permissions.kick_members:
                if role < guild.me.top_role:
                    roles_to_remove.append(role)

        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"[{config.SERVER_NAME} EMERGENCY QUARANTINE] {reason}")
                logger.warning(f"Quarantined admin user {member} ({member.id}) in guild {guild.name}")
            except Exception as e:
                logger.error(f"Failed to remove roles from {member.id}: {e}")

        # 2. DM User
        dm_fields = [
            {"name": "Server", "value": f"**{guild.name} ({config.SERVER_NAME})**", "inline": True},
            {"name": "Action Taken", "value": f"`{'Banned & Kicked' if ban_user else 'Roles Revoked & Kicked'}`", "inline": True},
            {"name": "Trigger Reason", "value": reason, "inline": False}
        ]
        await send_user_dm(member, f"🚨 Emergency Security Action • {config.SERVER_NAME}", "Anti-Nuke safeguard detected unauthorized administrative activity.", COLOR_DANGER, dm_fields)

        # 3. Perform Kick or Ban if specified
        try:
            if ban_user:
                await member.ban(reason=f"[{config.SERVER_NAME} ANTI-NUKE BAN] {reason}")
            else:
                await member.kick(reason=f"[{config.SERVER_NAME} ANTI-NUKE KICK] {reason}")
        except Exception as e:
            logger.error(f"Failed to kick/ban inviter/offender {member.id}: {e}")

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

    # --- 1. INSTANT ANTI-BOT-ADD (KICK BOT & KICK/BAN INVITER) ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return

        guild = member.guild
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        # Fetch who invited this bot from audit logs
        async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
            if entry.target.id == member.id:
                inviter = entry.user
                if inviter and inviter.id != guild.owner_id and inviter.id != self.bot.user.id:
                    inviter_roles = [r.id for r in getattr(inviter, "roles", [])]
                    
                    # Check whitelist
                    if not db.is_whitelisted(str(guild.id), str(inviter.id), "anti_nuke", inviter_roles):
                        logger.warning(f"Unauthorized bot {member} ({member.id}) added by {inviter} ({inviter.id})!")

                        # 1. Instantly Kick/Ban the unauthorized added Bot
                        try:
                            await member.ban(reason=f"[{config.SERVER_NAME} Anti-Bot] Unauthorized bot invite by {inviter}.")
                        except Exception:
                            try:
                                await member.kick(reason=f"[{config.SERVER_NAME} Anti-Bot] Unauthorized bot invite by {inviter}.")
                            except Exception:
                                pass

                        # 2. Instantly Kick/Ban the inviter Admin/User
                        inviter_member = guild.get_member(inviter.id)
                        if inviter_member:
                            await self._quarantine_and_kick(
                                guild=guild,
                                member=inviter_member,
                                reason=f"Invited unauthorized bot @{member.name} (`{member.id}`) into the server.",
                                ban_user=True
                            )
                break

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
                if user and user.id != self.bot.user.id and user.id != guild.owner_id:
                    user_roles = [r.id for r in getattr(user, "roles", [])]
                    if db.is_whitelisted(str(guild.id), str(user.id), "anti_nuke", user_roles):
                        return
                    if self._is_rate_limited(str(guild.id), str(user.id), "channel_create"):
                        member = guild.get_member(user.id)
                        if member:
                            await self._quarantine_and_kick(guild, member, "Exceeded mass channel creation limit (Nuke Attempt).", ban_user=True)
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
            if user and user.id != self.bot.user.id and user.id != guild.owner_id:
                user_roles = [r.id for r in getattr(user, "roles", [])]
                if db.is_whitelisted(str(guild.id), str(user.id), "anti_nuke", user_roles):
                    return
                if self._is_rate_limited(str(guild.id), str(user.id), "channel_delete"):
                    member = guild.get_member(user.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Exceeded mass channel deletion limit (Nuke Attempt).", ban_user=True)
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
            if user and user.id != self.bot.user.id and user.id != guild.owner_id:
                user_roles = [r.id for r in getattr(user, "roles", [])]
                if db.is_whitelisted(str(guild.id), str(user.id), "anti_nuke", user_roles):
                    return
                if self._is_rate_limited(str(guild.id), str(user.id), "role_create"):
                    member = guild.get_member(user.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Exceeded mass role creation limit (Nuke Attempt).", ban_user=True)
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

        async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
            user = entry.user
            if user and user.id != self.bot.user.id and user.id != guild.owner_id:
                user_roles = [r.id for r in getattr(user, "roles", [])]
                if db.is_whitelisted(str(guild.id), str(user.id), "anti_nuke", user_roles):
                    return
                if self._is_rate_limited(str(guild.id), str(user.id), "role_delete"):
                    member = guild.get_member(user.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Exceeded mass role deletion limit (Nuke Attempt).", ban_user=True)
            break

    # --- 4. ANTI-MASS BAN / KICK PROTECTION ---

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        settings = db.get_guild_settings(str(guild.id))
        if not settings.get("anti_nuke", 1):
            return

        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            executor = entry.user
            if executor and executor.id != self.bot.user.id and executor.id != guild.owner_id:
                user_roles = [r.id for r in getattr(executor, "roles", [])]
                if db.is_whitelisted(str(guild.id), str(executor.id), "anti_nuke", user_roles):
                    return
                if self._is_rate_limited(str(guild.id), str(executor.id), "mass_ban"):
                    member = guild.get_member(executor.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Exceeded mass member ban limit (Rogue Admin Nuke Attempt).", ban_user=True)
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
            if user and user.id != self.bot.user.id and user.id != guild.owner_id:
                user_roles = [r.id for r in getattr(user, "roles", [])]
                if not db.is_whitelisted(str(guild.id), str(user.id), "anti_nuke", user_roles):
                    member = guild.get_member(user.id)
                    if member:
                        await self._quarantine_and_kick(guild, member, "Unauthorized Webhook creation (Potential Webhook Spam/Nuke).", ban_user=False)
            break

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

    # --- Commands ---

    @commands.command(name="emergencylockdown", aliases=["militarylockdown", "elockdown"])
    async def prefix_emergencylockdown(self, ctx):
        """Owner-only command to lock ALL channels & revoke ALL admin role permissions instantly"""
        await self._do_emergency_lockdown(ctx)

    @commands.command(name="unlockdown", aliases=["eunlockdown"])
    async def prefix_unlockdown(self, ctx):
        """Owner-only command to lift emergency lockdown"""
        await self._do_unlockdown(ctx)

    # --- Slash Commands ---

    @discord.app_commands.command(name="emergencylockdown", description="[OWNER ONLY] Lock ALL server channels & revoke admin role perms in 1 second")
    async def slash_emergencylockdown(self, interaction: discord.Interaction):
        await self._do_emergency_lockdown(interaction)

    @discord.app_commands.command(name="unlockdown", description="[OWNER ONLY] Lift emergency military lockdown and restore all channels")
    async def slash_unlockdown(self, interaction: discord.Interaction):
        await self._do_unlockdown(interaction)

async def setup(bot):
    await bot.add_cog(AntiNuke(bot))

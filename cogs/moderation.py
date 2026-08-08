import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import asyncio
import re
import logging
import database as db
import config
from embed_builder import joyst_embed, send_user_dm, log_security_event, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji

logger = logging.getLogger("AEGIS.Moderation")

def parse_duration(duration_str: str) -> int:
    """Parses duration strings like 10s, 5m, 2h, 7d, 1w, 10mins, 2hours, 1day into total seconds."""
    text = duration_str.strip().lower()
    text = re.sub(r"\b(seconds?|secs?)\b", "s", text)
    text = re.sub(r"\b(minutes?|mins?)\b", "m", text)
    text = re.sub(r"\b(hours?|hrs?)\b", "h", text)
    text = re.sub(r"\b(days?)\b", "d", text)
    text = re.sub(r"\b(weeks?)\b", "w", text)
    text = re.sub(r"\s+", "", text)

    regex = re.compile(r"^(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")
    match = regex.match(text)
    if not match:
        return 0

    weeks, days, hours, minutes, seconds = match.groups()
    total_seconds = 0
    if weeks:
        total_seconds += int(weeks) * 604800
    if days:
        total_seconds += int(days) * 86400
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)
    return total_seconds

# --- Wick-Style Interactive Confirmation View ---

class ModerationConfirmView(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member, action_name: str, guild: discord.Guild = None):
        super().__init__(timeout=30)
        self.author = author
        self.action_name = action_name
        self.guild = guild
        self.confirmed = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{get_emoji('warning', interaction.guild)} Only {self.author.mention} can confirm or cancel this action.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm Action", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        if not interaction.response.is_done():
            await interaction.response.defer()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tempban_checker.start()

    def cog_unload(self):
        self.tempban_checker.cancel()

    @tasks.loop(seconds=20)
    async def tempban_checker(self):
        current_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        expired_bans = db.get_expired_tempbans(current_ts)

        for ban_record in expired_bans:
            guild_id = int(ban_record["guild_id"])
            user_id = int(ban_record["user_id"])
            guild = self.bot.get_guild(guild_id)
            
            if guild:
                try:
                    user = await self.bot.fetch_user(user_id)
                    await guild.unban(user, reason=f"[{config.SERVER_NAME} Ban Timeout] Scheduled tempban expired.")
                    logger.info(f"Auto-unbanned user {user_id} in guild {guild_id}.")

                    desc = f"{get_emoji('success', guild)} Your temporary ban on **{guild.name}** has expired. You may rejoin."
                    await send_user_dm(user, "Ban Expired", desc, COLOR_SUCCESS)
                    
                    db.add_audit_log(str(guild_id), "BAN_TIMEOUT_EXPIRED", f"Auto-unbanned {user} ({user_id}).", str(user_id), str(user), "LOW")
                except Exception as e:
                    logger.error(f"Error auto-unbanning {user_id}: {e}")

            db.remove_tempban(str(guild_id), str(user_id))

    @tempban_checker.before_loop
    async def before_tempban_checker(self):
        await self.bot.wait_until_ready()

    # --- Global Command Error Listener ---

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        guild = ctx.guild
        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            desc = f"❌ **Permission Denied:** You are missing `{perms}` permission to run this command."
            embed = joyst_embed(description=desc, color=COLOR_DANGER, guild=guild)
            await ctx.send(embed=embed, delete_after=6)
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            desc = f"❌ **Bot Error:** I am missing `{perms}` permission to execute this."
            embed = joyst_embed(description=desc, color=COLOR_DANGER, guild=guild)
            await ctx.send(embed=embed, delete_after=6)
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"⚠️ **Missing Argument:** `{error.param.name}` is required. Usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`"
            embed = joyst_embed(description=desc, color=COLOR_WARNING, guild=guild)
            await ctx.send(embed=embed, delete_after=8)
        elif isinstance(error, commands.MemberNotFound):
            desc = f"⚠️ **Member Not Found:** Could not find target member in server."
            embed = joyst_embed(description=desc, color=COLOR_WARNING, guild=guild)
            await ctx.send(embed=embed, delete_after=6)
        elif isinstance(error, commands.CommandNotFound):
            pass # Ignore unknown command typos cleanly

    async def _reply_embed(self, ctx_or_interaction, title: str = None, description: str = None, color=COLOR_DARK, ephemeral=False):
        guild = ctx_or_interaction.guild if hasattr(ctx_or_interaction, "guild") else None
        embed = joyst_embed(title=title, description=description, color=color, guild=guild)
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _prompt_confirmation(self, ctx_or_interaction, action_name: str, target_name: str, reason: str) -> bool:
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        desc = (
            f"{get_emoji('question', guild)} **Confirm {action_name}?**\n\n"
            f"👤 **Target:** **{target_name}**\n"
            f"📝 **Reason:** {reason}"
        )
        confirm_embed = joyst_embed(description=desc, color=COLOR_WARNING, guild=guild)
        view = ModerationConfirmView(author, action_name, guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)
            msg = None
        else:
            msg = await ctx_or_interaction.send(embed=confirm_embed, view=view)

        await view.wait()

        if view.confirmed is not True:
            cancel_desc = f"{get_emoji('cancel', guild)} Action **{action_name}** on **{target_name}** was cancelled."
            cancel_embed = joyst_embed(description=cancel_desc, color=COLOR_DARK, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.edit_original_response(embed=cancel_embed, view=None)
            elif msg:
                await msg.edit(embed=cancel_embed, view=None)
            return False
        else:
            if not isinstance(ctx_or_interaction, discord.Interaction) and msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
            return True

    # --- Core Execution Functions ---

    async def _do_ban(self, ctx_or_interaction, member: discord.Member | discord.User, reason: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if isinstance(member, discord.Member):
            if member.id == guild.owner_id or member.top_role >= guild.me.top_role:
                await self._reply_embed(ctx_or_interaction, description="❌ Cannot ban this user (Hierarchy error).", color=COLOR_DANGER, ephemeral=True)
                return

        confirmed = await self._prompt_confirmation(ctx_or_interaction, "Permanent Ban", str(member), reason)
        if not confirmed:
            return

        dm_desc = f"🔨 You have been permanently banned from **{guild.name}**.\n📝 **Reason:** {reason}"
        dm_success = await send_user_dm(member, "Ban Notice", dm_desc, COLOR_DANGER)
        await asyncio.sleep(0.3)

        try:
            await guild.ban(member, reason=f"[{config.SERVER_NAME} PermBan] {reason}")

            desc = (
                f"{get_emoji('ban', guild)} **Permanently Banned** **{member}** (`{member.id}`)\n"
                f"👮 **Mod:** {author.mention} • 📝 **Reason:** {reason}\n"
                f"📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
            )
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_DANGER)
            await log_security_event(guild, title=f"{get_emoji('ban', guild)} Member Permanent Ban", description=desc, color=COLOR_DANGER)
            db.add_audit_log(str(guild.id), "BAN", f"Permanently banned {member} ({member.id}).", str(author.id), str(author), "HIGH")
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Ban Error: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_tempban(self, ctx_or_interaction, member: discord.Member, duration: str, reason: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if member.id == guild.owner_id or member.top_role >= guild.me.top_role:
            await self._reply_embed(ctx_or_interaction, description="❌ Cannot ban this user (Hierarchy error).", color=COLOR_DANGER, ephemeral=True)
            return

        seconds = parse_duration(duration)
        if seconds <= 0:
            await self._reply_embed(ctx_or_interaction, description="⚠️ Invalid duration (e.g. `10m`, `2h`, `7d`).", color=COLOR_WARNING, ephemeral=True)
            return

        confirmed = await self._prompt_confirmation(ctx_or_interaction, "TempBan", str(member), f"{reason} ({duration})")
        if not confirmed:
            return

        unban_timestamp = db.add_tempban(str(guild.id), str(member.id), str(member), reason, str(author), seconds)

        dm_desc = f"🔨 You were tempbanned from **{guild.name}** for `{duration}`.\n📝 **Reason:** {reason}"
        dm_success = await send_user_dm(member, "Temporary Ban Notice", dm_desc, COLOR_DANGER)
        await asyncio.sleep(0.3)

        try:
            await member.ban(reason=f"[{config.SERVER_NAME} TempBan: {duration}] {reason}")

            desc = (
                f"{get_emoji('ban', guild)} **Tempbanned** {member.mention} (`{member.id}`)\n"
                f"⏱️ **Duration:** `{duration}` • <t:{unban_timestamp}:R>\n"
                f"👮 **Mod:** {author.mention} • 📝 **Reason:** {reason}\n"
                f"📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
            )
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_DANGER)
            await log_security_event(guild, title=f"{get_emoji('ban', guild)} Member Tempbanned", description=desc, color=COLOR_DANGER)
            db.add_audit_log(str(guild.id), "TEMPBAN", f"Tempbanned {member} for {duration}.", str(author.id), str(author), "HIGH")
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Ban Error: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_unban(self, ctx_or_interaction, user_id: str, reason: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        confirmed = await self._prompt_confirmation(ctx_or_interaction, "Unban", f"User ID `{user_id}`", reason)
        if not confirmed:
            return

        try:
            uid = int(user_id)
            user = await self.bot.fetch_user(uid)
            await guild.unban(user, reason=f"[{config.SERVER_NAME} Unban] {reason}")
            db.remove_tempban(str(guild.id), str(uid))

            dm_success = await send_user_dm(user, "Ban Revoked", f"Your ban on **{guild.name}** was unbanned.", COLOR_SUCCESS)

            desc = (
                f"{get_emoji('success', guild)} **Unbanned** **{user}** (`{user_id}`)\n"
                f"👮 **Mod:** {author.mention} • 📝 **Reason:** {reason}\n"
                f"📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
            )
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_SUCCESS)
            await log_security_event(guild, title=f"{get_emoji('success', guild)} Member Unbanned", description=desc, color=COLOR_SUCCESS)
            db.add_audit_log(str(guild.id), "UNBAN", f"Unbanned {user} ({user_id}).", str(author.id), str(author), "MEDIUM")
        except discord.NotFound:
            await self._reply_embed(ctx_or_interaction, description="⚠️ Target user ID is not banned.", color=COLOR_WARNING, ephemeral=True)
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Unban Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_timeout(self, ctx_or_interaction, member: discord.Member, duration: str, reason: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        seconds = parse_duration(duration)
        if seconds <= 0 or seconds > 28 * 86400:
            await self._reply_embed(ctx_or_interaction, description="⚠️ Specify duration under 28 days.", color=COLOR_WARNING, ephemeral=True)
            return

        confirmed = await self._prompt_confirmation(ctx_or_interaction, "Timeout", str(member), f"{reason} ({duration})")
        if not confirmed:
            return

        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=f"[{config.SERVER_NAME} Timeout] {reason}")

            dm_desc = f"🔇 You were timed out in **{guild.name}** for `{duration}`.\n📝 **Reason:** {reason}"
            dm_success = await send_user_dm(member, "Timeout Applied", dm_desc, COLOR_WARNING)

            desc = (
                f"{get_emoji('timeout', guild)} **Timed Out** {member.mention} (`{member.id}`)\n"
                f"⏱️ **Duration:** `{duration}` • <t:{int(until.timestamp())}:R>\n"
                f"👮 **Mod:** {author.mention} • 📝 **Reason:** {reason}\n"
                f"📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
            )
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_WARNING)
            await log_security_event(guild, title=f"{get_emoji('timeout', guild)} Member Timed Out", description=desc, color=COLOR_WARNING)
            db.add_audit_log(str(guild.id), "TIMEOUT", f"Timed out {member} for {duration}.", str(author.id), str(author), "MEDIUM")
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Timeout Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_untimeout(self, ctx_or_interaction, member: discord.Member):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        try:
            await member.timeout(None, reason=f"[{config.SERVER_NAME}] Untimeout.")
            dm_success = await send_user_dm(member, "Timeout Removed", f"Your timeout on **{guild.name}** was removed.", COLOR_SUCCESS)
            
            desc = (
                f"{get_emoji('untimeout', guild)} **Timeout Removed** for {member.mention}\n"
                f"👮 **Mod:** {author.mention} • 📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
            )
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_SUCCESS)
            await log_security_event(guild, title=f"{get_emoji('untimeout', guild)} Timeout Removed", description=desc, color=COLOR_SUCCESS)
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_warn(self, ctx_or_interaction, member: discord.Member, reason: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        confirmed = await self._prompt_confirmation(ctx_or_interaction, "Warn", str(member), reason)
        if not confirmed:
            return

        count = db.add_warning(str(guild.id), str(member.id), reason, str(author.id))

        dm_desc = f"⚠️ You received a warning in **{guild.name}**.\n📝 **Reason:** {reason} (Warning #{count})"
        dm_success = await send_user_dm(member, "Warning Issued", dm_desc, COLOR_WARNING)

        desc = (
            f"{get_emoji('warning', guild)} **Warned** {member.mention} (`{member.id}`)\n"
            f"⚠️ **Total Warnings:** `{count}`\n"
            f"👮 **Mod:** {author.mention} • 📝 **Reason:** {reason}\n"
            f"📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
        )
        await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_WARNING)
        await log_security_event(guild, title=f"{get_emoji('warning', guild)} Warning Issued", description=desc, color=COLOR_WARNING)

    async def _do_clearwarns(self, ctx_or_interaction, member: discord.Member):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        db.clear_warnings(str(guild.id), str(member.id))
        desc = f"{get_emoji('success', guild)} Cleared all warnings for {member.mention}."
        await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_SUCCESS)

    async def _do_slowmode(self, ctx_or_interaction, seconds: int, target_channel: discord.TextChannel = None):
        channel = target_channel or ctx_or_interaction.channel
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        try:
            await channel.edit(slowmode_delay=seconds)
            desc = f"⏱️ Slowmode in {channel.mention} set to **`{seconds}s`**." if seconds > 0 else f"⏱️ Slowmode in {channel.mention} **Disabled**."
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_WARNING)
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_kick(self, ctx_or_interaction, member: discord.Member, reason: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        confirmed = await self._prompt_confirmation(ctx_or_interaction, "Kick", str(member), reason)
        if not confirmed:
            return

        dm_desc = f"👢 You were kicked from **{guild.name}**.\n📝 **Reason:** {reason}"
        dm_success = await send_user_dm(member, "Kick Notice", dm_desc, COLOR_DANGER)
        await asyncio.sleep(0.3)

        try:
            await member.kick(reason=f"[{config.SERVER_NAME} Kick] {reason}")

            desc = (
                f"{get_emoji('kick', guild)} **Kicked** **{member}** (`{member.id}`)\n"
                f"👮 **Mod:** {author.mention} • 📝 **Reason:** {reason}\n"
                f"📩 **DM:** {'✅ Delivered' if dm_success else '⚠️ DMs Closed'}"
            )
            await self._reply_embed(ctx_or_interaction, description=desc, color=COLOR_DANGER)
            await log_security_event(guild, title=f"{get_emoji('kick', guild)} Member Kicked", description=desc, color=COLOR_DANGER)
            db.add_audit_log(str(guild.id), "KICK", f"Kicked {member} ({member.id}).", str(author.id), str(author), "HIGH")
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Kick Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_purge(self, ctx_or_interaction, amount: int, member: discord.Member = None):
        channel = ctx_or_interaction.channel
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if amount <= 0:
            await self._reply_embed(ctx_or_interaction, description="⚠️ Specify number of messages to purge.", color=COLOR_WARNING, ephemeral=True)
            return

        if amount > 1000:
            amount = 1000

        if amount >= 50:
            confirmed = await self._prompt_confirmation(ctx_or_interaction, "Purge", f"{amount} msgs in {channel.mention}", "Bulk cleanup")
            if not confirmed:
                return

        if not isinstance(ctx_or_interaction, discord.Interaction):
            try:
                await ctx_or_interaction.message.delete()
            except Exception:
                pass

        def check_msg(m):
            return m.author.id == member.id if member else True

        try:
            deleted = await channel.purge(limit=amount, check=check_msg)
            count = len(deleted)

            desc = (
                f"{get_emoji('purge', guild)} Cleared **`{count}`** messages in {channel.mention}.\n"
                f"👮 **Mod:** {author.mention}"
            )
            if member:
                desc += f" • 👤 **Target:** {member.mention}"

            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

            if isinstance(ctx_or_interaction, discord.Interaction):
                if not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
            else:
                reply_msg = await channel.send(embed=embed)
                await reply_msg.delete(delay=4)

            await log_security_event(guild, title=f"{get_emoji('purge', guild)} Bulk Message Clear", description=desc, color=COLOR_SUCCESS)
            db.add_audit_log(str(guild.id), "PURGE", f"Purged {count} msgs in #{channel.name}", str(author.id), str(author), "MEDIUM")
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Purge Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_say(self, ctx_or_interaction, message_content: str, target_channel: discord.TextChannel = None):
        channel = target_channel or ctx_or_interaction.channel
        if not isinstance(ctx_or_interaction, discord.Interaction):
            try:
                await ctx_or_interaction.message.delete()
            except Exception:
                pass

        try:
            await channel.send(content=message_content)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(f"✅ Message sent to {channel.mention}.", ephemeral=True)
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    async def _do_sayembed(self, ctx_or_interaction, title: str, description: str, target_channel: discord.TextChannel = None, color_str: str = "blue"):
        channel = target_channel or ctx_or_interaction.channel
        if not isinstance(ctx_or_interaction, discord.Interaction):
            try:
                await ctx_or_interaction.message.delete()
            except Exception:
                pass

        color_map = {"blue": COLOR_INFO, "green": COLOR_SUCCESS, "gold": COLOR_WARNING, "red": COLOR_DANGER, "purple": COLOR_PURPLE}
        color = color_map.get(color_str.lower(), COLOR_INFO)

        embed = joyst_embed(title=title, description=description, color=color, guild=ctx_or_interaction.guild)

        try:
            await channel.send(embed=embed)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(f"✅ Announcement sent to {channel.mention}.", ephemeral=True)
        except Exception as e:
            await self._reply_embed(ctx_or_interaction, description=f"❌ Failed: {e}", color=COLOR_DANGER, ephemeral=True)

    # --- Commands ---

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def prefix_ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        await self._do_ban(ctx, member, reason)

    @commands.command(name="tempban", aliases=["tban"])
    @commands.has_permissions(ban_members=True)
    async def prefix_tempban(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        await self._do_tempban(ctx, member, duration, reason)

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def prefix_unban(self, ctx, user_id: str, *, reason: str = "No reason provided"):
        await self._do_unban(ctx, user_id, reason)

    @commands.command(name="timeout", aliases=["mute"])
    @commands.has_permissions(moderate_members=True)
    async def prefix_timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        await self._do_timeout(ctx, member, duration, reason)

    @commands.command(name="untimeout", aliases=["unmute"])
    @commands.has_permissions(moderate_members=True)
    async def prefix_untimeout(self, ctx, member: discord.Member):
        await self._do_untimeout(ctx, member)

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def prefix_warn(self, ctx, member: discord.Member, *, reason: str):
        await self._do_warn(ctx, member, reason)

    @commands.command(name="clearwarns")
    @commands.has_permissions(moderate_members=True)
    async def prefix_clearwarns(self, ctx, member: discord.Member):
        await self._do_clearwarns(ctx, member)

    @commands.command(name="warnings", aliases=["warns"])
    async def prefix_warnings(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        warns = db.get_user_warnings(str(ctx.guild.id), str(target.id))
        guild = ctx.guild
        if not warns:
            await self._reply_embed(ctx, description=f"{get_emoji('success', guild)} **{target.mention}** has **0 warnings**.", color=COLOR_SUCCESS)
            return
        warn_lines = [f"• **#{w['id']}** `{w['created_at']}`: {w['reason']}" for w in warns[:5]]
        desc = f"⚠️ **Warning History • {target.mention}** (`{len(warns)}` total):\n\n" + "\n".join(warn_lines)
        await self._reply_embed(ctx, description=desc, color=COLOR_WARNING)

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def prefix_kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        await self._do_kick(ctx, member, reason)

    @commands.command(name="purge", aliases=["clean", "clear"])
    @commands.has_permissions(manage_messages=True)
    async def prefix_purge(self, ctx, amount: int, member: discord.Member = None):
        await self._do_purge(ctx, amount, member)

    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def prefix_slowmode(self, ctx, seconds: int, channel: discord.TextChannel = None):
        await self._do_slowmode(ctx, seconds, channel)

    @commands.command(name="say", aliases=["echo", "speak"])
    @commands.has_permissions(manage_messages=True)
    async def prefix_say(self, ctx, *, message: str):
        await self._do_say(ctx, message)

    @commands.command(name="sayembed", aliases=["announce", "embedsay"])
    @commands.has_permissions(manage_messages=True)
    async def prefix_sayembed(self, ctx, *, text: str):
        if "|" in text:
            parts = text.split("|", 1)
            title = parts[0].strip()
            desc = parts[1].strip()
        else:
            title = "📢 Announcement"
            desc = text.strip()

        await self._do_sayembed(ctx, title, desc)

    @commands.command(name="lockdown", aliases=["lock"])
    @commands.has_permissions(manage_channels=True)
    async def prefix_lockdown(self, ctx, state: str = "true"):
        is_lock = state.lower() in ["true", "on", "1", "yes", "lock"]
        guild = ctx.guild
        overwrite = ctx.channel.overwrites_for(guild.default_role)
        overwrite.send_messages = not is_lock
        try:
            await ctx.channel.set_permissions(guild.default_role, overwrite=overwrite)
            status_str = "🔒 LOCKED DOWN" if is_lock else "🔓 UNLOCKED"
            desc = f"{get_emoji('shield', guild)} Channel {ctx.channel.mention} is now **{status_str}**."
            await self._reply_embed(ctx, description=desc, color=COLOR_WARNING)
        except Exception as e:
            await self._reply_embed(ctx, description=f"❌ Error: {e}", color=COLOR_DANGER)

    # --- ROLE MANAGEMENT SYSTEM ---

    async def _do_add_role(self, ctx_or_interaction, member: discord.Member, role: discord.Role, reason: str = None):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author
        reason_str = reason or f"Role assigned by {author} via SYPHON SECURITY"

        me = guild.me
        if not me.guild_permissions.manage_roles:
            embed = joyst_embed(description="❌ **Bot Error:** I lack `Manage Roles` permission to assign roles.", color=COLOR_DANGER, guild=guild)
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        if role >= me.top_role:
            embed = joyst_embed(
                description=f"❌ **Role Hierarchy Error:** The role {role.mention} is higher than or equal to my highest role ({me.top_role.mention}). Move my bot role above **{role.name}** in Server Settings ➔ Roles.",
                color=COLOR_DANGER,
                guild=guild
            )
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        if author.id != guild.owner_id and role >= author.top_role:
            embed = joyst_embed(
                description=f"❌ **Permission Denied:** You cannot assign {role.mention} because it is higher than or equal to your highest role ({author.top_role.mention}).",
                color=COLOR_DANGER,
                guild=guild
            )
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        if role in member.roles:
            embed = joyst_embed(
                description=f"ℹ️ User {member.mention} already has the role {role.mention}.",
                color=COLOR_WARNING,
                guild=guild
            )
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        try:
            await member.add_roles(role, reason=reason_str)
            
            e_tick = get_emoji("CB_greentick", guild)
            embed = joyst_embed(
                title=f"{e_tick} ROLE ASSIGNED SUCCESSFULLY • {guild.name}",
                description=f"Successfully granted role {role.mention} to {member.mention}!",
                color=COLOR_SUCCESS,
                guild=guild,
                fields=[
                    {"name": "👤 Target Member", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                    {"name": "🛡️ Role Granted", "value": f"{role.mention} (`{role.id}`)", "inline": True},
                    {"name": "👮 Action By", "value": f"{author.mention} (`{author.id}`)", "inline": True},
                    {"name": "🎨 Role Color", "value": f"`{str(role.color)}`", "inline": True},
                    {"name": "👥 Total Members", "value": f"`{len(role.members)} members`", "inline": True}
                ]
            )
            await self._reply_embed(ctx_or_interaction, embed=embed)
            db.add_audit_log(str(guild.id), "ROLE_ADD", f"Assigned role {role.name} ({role.id}) to member {member} ({member.id}).", str(author.id), str(author), "LOW")

        except Exception as e:
            embed = joyst_embed(description=f"❌ Failed to assign role {role.mention}: {e}", color=COLOR_DANGER, guild=guild)
            await self._reply_embed(ctx_or_interaction, embed=embed)

    async def _do_remove_role(self, ctx_or_interaction, member: discord.Member, role: discord.Role, reason: str = None):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author
        reason_str = reason or f"Role removed by {author} via SYPHON SECURITY"

        me = guild.me
        if not me.guild_permissions.manage_roles:
            embed = joyst_embed(description="❌ **Bot Error:** I lack `Manage Roles` permission to remove roles.", color=COLOR_DANGER, guild=guild)
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        if role >= me.top_role:
            embed = joyst_embed(
                description=f"❌ **Role Hierarchy Error:** The role {role.mention} is higher than or equal to my highest role ({me.top_role.mention}).",
                color=COLOR_DANGER,
                guild=guild
            )
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        if author.id != guild.owner_id and role >= author.top_role:
            embed = joyst_embed(
                description=f"❌ **Permission Denied:** You cannot remove {role.mention} because it is higher than or equal to your highest role ({author.top_role.mention}).",
                color=COLOR_DANGER,
                guild=guild
            )
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        if role not in member.roles:
            embed = joyst_embed(
                description=f"ℹ️ User {member.mention} does not have the role {role.mention}.",
                color=COLOR_WARNING,
                guild=guild
            )
            return await self._reply_embed(ctx_or_interaction, embed=embed)

        try:
            await member.remove_roles(role, reason=reason_str)
            
            e_cross = get_emoji("Cross_", guild)
            embed = joyst_embed(
                title=f"{e_cross} ROLE REVOKED SUCCESSFULLY • {guild.name}",
                description=f"Successfully removed role {role.mention} from {member.mention}!",
                color=COLOR_DANGER,
                guild=guild,
                fields=[
                    {"name": "👤 Target Member", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                    {"name": "🔇 Role Revoked", "value": f"{role.mention} (`{role.id}`)", "inline": True},
                    {"name": "👮 Action By", "value": f"{author.mention} (`{author.id}`)", "inline": True}
                ]
            )
            await self._reply_embed(ctx_or_interaction, embed=embed)
            db.add_audit_log(str(guild.id), "ROLE_REMOVE", f"Removed role {role.name} ({role.id}) from member {member} ({member.id}).", str(author.id), str(author), "LOW")

        except Exception as e:
            embed = joyst_embed(description=f"❌ Failed to remove role {role.mention}: {e}", color=COLOR_DANGER, guild=guild)
            await self._reply_embed(ctx_or_interaction, embed=embed)

    @commands.command(name="addrole", aliases=["giverole", "radd"])
    @commands.has_permissions(manage_roles=True)
    async def prefix_addrole(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = None):
        """Grants a role to a member with hierarchy verification and clean embed log."""
        await self._do_add_role(ctx, member, role, reason)

    @commands.command(name="removerole", aliases=["takerole", "rremove"])
    @commands.has_permissions(manage_roles=True)
    async def prefix_removerole(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = None):
        """Revokes a role from a member with hierarchy verification and clean embed log."""
        await self._do_remove_role(ctx, member, role, reason)

    @commands.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def prefix_role(self, ctx):
        dot = get_emoji("black_dot", ctx.guild)
        desc = (
            f"# 🛡️ SYPHON SECURITY Role Management Module\n\n"
            f"{dot} **To Grant Role:** `,addrole @User @Role` or `,role add @User @Role`\n"
            f"{dot} **To Revoke Role:** `,removerole @User @Role` or `,role remove @User @Role`"
        )
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=ctx.guild)
        await ctx.send(embed=embed)

    @prefix_role.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def prefix_role_add(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = None):
        await self._do_add_role(ctx, member, role, reason)

    @prefix_role.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def prefix_role_remove(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = None):
        await self._do_remove_role(ctx, member, role, reason)

    # --- Slash Commands ---

    @app_commands.command(name="addrole", description="Grant a role to a member")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, reason: str = None):
        await self._do_add_role(interaction, member, role, reason)

    @app_commands.command(name="removerole", description="Revoke a role from a member")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, reason: str = None):
        await self._do_remove_role(interaction, member, role, reason)

    @app_commands.command(name="ban", description="Permanently ban a user from the server")
    @app_commands.checks.has_permissions(ban_members=True)
    async def slash_ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await self._do_ban(interaction, member, reason)

    @app_commands.command(name="tempban", description="Ban a user for a specific duration (e.g. 1h, 7d, 30d)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def slash_tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
        await self._do_tempban(interaction, member, duration, reason)

    @app_commands.command(name="unban", description="Unban a user from the server and remove active tempban entry")
    @app_commands.checks.has_permissions(ban_members=True)
    async def slash_unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        await self._do_unban(interaction, user_id, reason)

    @app_commands.command(name="timeout", description="Apply a native Discord timeout to a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
        await self._do_timeout(interaction, member, duration, reason)

    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_untimeout(self, interaction: discord.Interaction, member: discord.Member):
        await self._do_untimeout(interaction, member)

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await self._do_warn(interaction, member, reason)

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def slash_clearwarns(self, interaction: discord.Interaction, member: discord.Member):
        await self._do_clearwarns(interaction, member)

    @app_commands.command(name="purge", description="Bulk delete messages from the current channel")
    @app_commands.describe(amount="Number of messages to delete (1-1000)", member="Filter by specific member (optional)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        await self._do_purge(interaction, amount, member)

    @app_commands.command(name="slowmode", description="Set channel slowmode delay in seconds")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_slowmode(self, interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
        await self._do_slowmode(interaction, seconds, channel)

async def setup(bot):
    await bot.add_cog(Moderation(bot))

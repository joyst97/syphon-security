import discord
from discord import app_commands
from discord.ext import commands
import logging
import database as db
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE
from emojis import get_emoji

logger = logging.getLogger("AEGIS.TempVC")

class TempVC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_channels = set()  # set of active temp voice channel IDs

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild

        # 1. Member joined a voice channel
        if after.channel and (after.channel.name.startswith("➕ Join to Create") or after.channel.name.startswith("➕ Create VC")):
            master_vc = after.channel
            category = master_vc.category

            target_name = f"🔊 {member.display_name}'s Room"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
                member: discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True, move_members=True),
                guild.me: discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True, move_members=True)
            }

            try:
                new_vc = await guild.create_voice_channel(
                    name=target_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"[{config.SERVER_NAME} Temp VC] Dynamic room for {member}."
                )

                self.temp_channels.add(new_vc.id)

                # Move member into new private voice channel
                await member.move_to(new_vc, reason=f"[{config.SERVER_NAME} Temp VC] Auto-moved to private room.")
                logger.info(f"Created temp voice channel {new_vc.name} for {member}")
            except Exception as e:
                logger.error(f"Error creating temp voice channel for {member}: {e}")

        # 2. Member left a voice channel (Cleanup empty temp channels)
        if before.channel and before.channel.id in self.temp_channels:
            left_ch = before.channel
            if len(left_ch.members) == 0:
                try:
                    self.temp_channels.remove(left_ch.id)
                    await left_ch.delete(reason=f"[{config.SERVER_NAME} Temp VC] Auto-cleaning empty room.")
                    logger.info(f"Cleaned up empty temp voice channel {left_ch.name}")
                except Exception as e:
                    logger.error(f"Error deleting temp voice channel {left_ch.id}: {e}")

        # 3. Voice Channel Join / Leave / Switch Real-Time Audit Log Broadcaster (ALL SERVER VOICE CHANNELS)
        try:
            if before.channel != after.channel:
                log_ch = await get_or_create_vc_log_channel(guild)
                if log_ch:
                    if before.channel is None and after.channel is not None:
                        # MEMBER JOINED VOICE CHANNEL
                        embed = joyst_embed(
                            title=f"<a:CB_greentick:1441097547350282260> VOICE CHANNEL JOINED • {guild.name}",
                            description=f"User {member.mention} (`{member.id}`) connected to **{after.channel.name}**",
                            color=COLOR_SUCCESS,
                            guild=guild,
                            fields=[
                                {"name": "👤 Member", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                                {"name": "🔊 Voice Channel Joined", "value": f"**{after.channel.name}** ({after.channel.mention})", "inline": True},
                                {"name": "📁 Category", "value": f"`{after.channel.category.name if after.channel.category else 'No Category'}`", "inline": False}
                            ]
                        )
                        await log_ch.send(embed=embed)

                    elif before.channel is not None and after.channel is None:
                        # MEMBER LEFT VOICE CHANNEL
                        embed = joyst_embed(
                            title=f"<a:Cross_:1535587084952272937> VOICE CHANNEL LEFT • {guild.name}",
                            description=f"User {member.mention} (`{member.id}`) disconnected from **{before.channel.name}**",
                            color=COLOR_DANGER,
                            guild=guild,
                            fields=[
                                {"name": "👤 Member", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                                {"name": "🔇 Voice Channel Left", "value": f"**{before.channel.name}**", "inline": True},
                                {"name": "📁 Category", "value": f"`{before.channel.category.name if before.channel.category else 'No Category'}`", "inline": False}
                            ]
                        )
                        await log_ch.send(embed=embed)

                    elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
                        # MEMBER SWITCHED VOICE CHANNEL
                        embed = joyst_embed(
                            title=f"<a:dev:1528079861283946538> VOICE CHANNEL SWITCHED • {guild.name}",
                            description=f"User {member.mention} (`{member.id}`) moved voice channels.",
                            color=COLOR_PURPLE,
                            guild=guild,
                            fields=[
                                {"name": "👤 Member", "value": f"{member.mention} (`{member.id}`)", "inline": True},
                                {"name": "📤 From VC", "value": f"**{before.channel.name}**", "inline": True},
                                {"name": "📥 To VC", "value": f"**{after.channel.name}** ({after.channel.mention})", "inline": True}
                            ]
                        )
                        await log_ch.send(embed=embed)
        except Exception as e:
            logger.debug(f"VC Audit log broadcast note in {guild.name}: {e}")

    async def _do_setup_tempvc(self, ctx_or_interaction, category: discord.CategoryChannel = None):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
            guild.me: discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True, move_members=True)
        }

        try:
            master_vc = await guild.create_voice_channel(
                name="➕ Join to Create",
                category=category,
                overwrites=overwrites,
                reason=f"[{guild.name}] Master Temp VC generator channel."
            )

            desc = (
                f"{get_emoji('success', guild)} **Temp Voice Channel Generator Deployed!**\n\n"
                f"• Master Channel: {master_vc.mention}\n"
                f"• Joining `{master_vc.name}` will automatically create a private voice room for members and auto-delete when empty!"
            )
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)

            db.add_audit_log(str(guild.id), "TEMPVC_SETUP", f"Deployed Master Temp VC channel {master_vc.name}.", str(author.id), str(author), "LOW")

        except Exception as e:
            logger.error(f"Error setting up Temp VC master channel: {e}")
            embed = joyst_embed(description=f"❌ Failed to create Temp VC generator channel: {e}", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)

    # --- Commands ---

    @commands.group(name="tempvc", aliases=["jointocreate"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def prefix_tempvc(self, ctx):
        await self._do_setup_tempvc(ctx)

    @prefix_tempvc.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def prefix_tempvc_setup(self, ctx, category: discord.CategoryChannel = None):
        await self._do_setup_tempvc(ctx, category)

    @commands.command(name="vclogs", aliases=["voicelogs", "vclog", "setvclogs"])
    @commands.has_permissions(administrator=True)
    async def prefix_vclogs(self, ctx):
        """Deploys or locates the dedicated #vc-logs voice audit log vault."""
        ch = await get_or_create_vc_log_channel(ctx.guild)
        if ch:
            embed = joyst_embed(
                description=f"{get_emoji('success', ctx.guild)} **Voice Channel Audit Log Vault Deployed!**\n\n• Channel: {ch.mention}\n• All voice joins, leaves, and channel switches will now be logged in real-time!",
                color=COLOR_SUCCESS,
                guild=ctx.guild
            )
            await ctx.send(embed=embed)
        else:
            embed = joyst_embed(description="❌ Failed to create `#vc-logs` channel. Please check bot permissions.", color=COLOR_DANGER, guild=ctx.guild)
            await ctx.send(embed=embed)

    # --- Slash Commands ---

    tempvc_group = app_commands.Group(name="tempvc", description="Temporary Voice Channel & VC Log Management")

    @tempvc_group.command(name="setup", description="Deploy the '➕ Join to Create' Temp Voice Generator channel")
    @app_commands.describe(category="Category to place master channel in (optional)")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_tempvc_setup(self, interaction: discord.Interaction, category: discord.CategoryChannel = None):
        await self._do_setup_tempvc(interaction, category)

    @tempvc_group.command(name="vclogs", description="Deploy dedicated #vc-logs channel for voice join/leave audit logging")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_vclogs(self, interaction: discord.Interaction):
        ch = await get_or_create_vc_log_channel(interaction.guild)
        if ch:
            embed = joyst_embed(
                description=f"{get_emoji('success', interaction.guild)} **Voice Channel Audit Log Vault Deployed!**\n\n• Channel: {ch.mention}\n• All voice joins, leaves, and channel switches will now be logged in real-time!",
                color=COLOR_SUCCESS,
                guild=interaction.guild
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = joyst_embed(description="❌ Failed to create `#vc-logs` channel. Please check bot permissions.", color=COLOR_DANGER, guild=interaction.guild)
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def get_or_create_vc_log_channel(guild: discord.Guild) -> discord.TextChannel:
    me = guild.me
    if not me:
        return None

    for ch in guild.text_channels:
        if ch.name in ["vc-logs", "voice-logs", "vc-log"]:
            if ch.permissions_for(me).send_messages:
                return ch

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
        me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
    }

    for r in guild.roles:
        if r.permissions.administrator or r.permissions.manage_guild or "admin" in r.name.lower() or "mod" in r.name.lower():
            overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=False)

    try:
        category = discord.utils.get(guild.categories, name="--- 🛡️ LOG VAULT ---") or discord.utils.get(guild.categories, name="LOGS")
        ch = await guild.create_text_channel(
            name="vc-logs",
            category=category,
            overwrites=overwrites,
            topic="🔊 Live Real-Time Voice Channel Join/Leave Audit Logs Stream",
            reason=f"[{guild.name}] Auto-deploying dedicated voice channel log vault."
        )
        return ch
    except Exception as e:
        logger.error(f"Failed to create #vc-logs channel in {guild.name}: {e}")
        return None

async def setup(bot):
    await bot.add_cog(TempVC(bot))

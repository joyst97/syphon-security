import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import database as db
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE
from emojis import get_emoji

logger = logging.getLogger("AEGIS.Stats")

class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_stats_counter.start()

    def cog_unload(self):
        self.update_stats_counter.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._update_guild_stats(guild)

    @tasks.loop(minutes=10)
    async def update_stats_counter(self):
        for guild in self.bot.guilds:
            await self._update_guild_stats(guild)

    @update_stats_counter.before_loop
    async def before_update_stats_counter(self):
        await self.bot.wait_until_ready()

    async def _update_guild_stats(self, guild: discord.Guild):
        if not guild:
            return

        settings = db.get_guild_settings(str(guild.id))
        counter_ch_id = settings.get("member_counter_channel_id")
        
        m_count = guild.member_count or len(guild.members) or 0
        target_name = f"👥 Total Members: {m_count:,}"

        # Find all matching stats voice channels in the guild
        matching_channels = [
            ch for ch in guild.voice_channels
            if ch.name.startswith("👥 Total Members:") or ch.name.startswith("👥 Members:")
        ]

        if matching_channels:
            primary_ch = None
            if counter_ch_id:
                primary_ch = discord.utils.get(matching_channels, id=int(counter_ch_id))

            if not primary_ch:
                primary_ch = matching_channels[0]
                db.update_guild_setting(str(guild.id), "member_counter_channel_id", str(primary_ch.id))

            # Edit primary channel name if needed
            try:
                if primary_ch.name != target_name:
                    await primary_ch.edit(name=target_name, reason=f"[{config.SERVER_NAME}] Live member stats update.")
            except Exception as e:
                logger.error(f"Error editing primary stats channel: {e}")

            # Delete all extra duplicate channels automatically!
            for extra_ch in matching_channels:
                if extra_ch.id != primary_ch.id:
                    try:
                        await extra_ch.delete(reason=f"[{config.SERVER_NAME}] Cleaning duplicate Total Members channel.")
                        logger.info(f"Deleted duplicate stats channel {extra_ch.id} in {guild.name}")
                    except Exception as e:
                        logger.error(f"Error deleting duplicate stats channel {extra_ch.id}: {e}")
        else:
            # If no channel exists at all, auto-create ONE at the top of server
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, connect=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, manage_channels=True, connect=True)
            }
            try:
                new_ch = await guild.create_voice_channel(
                    name=target_name,
                    overwrites=overwrites,
                    position=0,
                    reason=f"[{config.SERVER_NAME}] Auto-created Live Member Stats Counter."
                )
                db.update_guild_setting(str(guild.id), "member_counter_channel_id", str(new_ch.id))
                logger.info(f"Auto-created live member stats channel in {guild.name}: {target_name}")
            except Exception as e:
                logger.error(f"Failed to auto-create member stats channel: {e}")

    async def _do_setup_stats(self, ctx_or_interaction, category: discord.CategoryChannel = None):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        target_name = f"👥 Total Members: {guild.member_count:,}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, connect=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, manage_channels=True, connect=True)
        }

        try:
            new_ch = await guild.create_voice_channel(
                name=target_name,
                category=category,
                overwrites=overwrites,
                position=0,
                reason=f"[{config.SERVER_NAME}] Created Live Member Stats Counter."
            )

            db.update_guild_setting(str(guild.id), "member_counter_channel_id", str(new_ch.id))

            desc = f"{get_emoji('success', guild)} **Live Member Counter Created!** Channel {new_ch.mention} will auto-update total member count."
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)

            db.add_audit_log(str(guild.id), "STATS_SETUP", f"Created Live Member Stats counter channel {new_ch.name}.", str(author.id), str(author), "LOW")

            # Clean duplicates if any exist
            await self._update_guild_stats(guild)

        except Exception as e:
            logger.error(f"Error creating stats counter channel: {e}")
            embed = joyst_embed(description=f"❌ Failed to create stats counter channel: {e}", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._update_guild_stats(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._update_guild_stats(member.guild)

    # --- Commands ---

    @commands.group(name="stats", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def prefix_stats(self, ctx):
        await self._do_setup_stats(ctx)

    @prefix_stats.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def prefix_stats_setup(self, ctx, category: discord.CategoryChannel = None):
        await self._do_setup_stats(ctx, category)

    @prefix_stats.command(name="update")
    @commands.has_permissions(administrator=True)
    async def prefix_stats_update(self, ctx):
        await self._update_guild_stats(ctx.guild)
        await ctx.send(f"{get_emoji('success', ctx.guild)} Live member counter updated!")

    # --- Slash Commands ---

    stats_group = app_commands.Group(name="stats", description=f"{config.SERVER_NAME} Live Stats Counter Commands")

    @stats_group.command(name="setup", description="Deploy live locked Total Members counter channel at top of server")
    @app_commands.describe(category="Target category to place counter under (optional)")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_stats_setup(self, interaction: discord.Interaction, category: discord.CategoryChannel = None):
        await self._do_setup_stats(interaction, category)

    @stats_group.command(name="update", description="Force update total member counter channel name immediately")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_stats_update(self, interaction: discord.Interaction):
        await self._update_guild_stats(interaction.guild)
        await interaction.response.send_message(f"{get_emoji('success', interaction.guild)} Live member counter updated!")

async def setup(bot):
    await bot.add_cog(ServerStats(bot))

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
                reason=f"[{config.SERVER_NAME}] Master Temp VC generator channel."
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

    # --- Slash Commands ---

    tempvc_group = app_commands.Group(name="tempvc", description=f"{config.SERVER_NAME} Temporary Voice Channel Management")

    @tempvc_group.command(name="setup", description="Deploy the '➕ Join to Create' Temp Voice Generator channel")
    @app_commands.describe(category="Category to place master channel in (optional)")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_tempvc_setup(self, interaction: discord.Interaction, category: discord.CategoryChannel = None):
        await self._do_setup_tempvc(interaction, category)

async def setup(bot):
    await bot.add_cog(TempVC(bot))

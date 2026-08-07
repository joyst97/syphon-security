import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import asyncio
import random
import json
import logging
import database as db
import config
from embed_builder import joyst_embed, send_user_dm, log_security_event, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji
from cogs.moderation import parse_duration

logger = logging.getLogger("AEGIS.Giveaway")

class GiveawayEntryView(discord.ui.View):
    def __init__(self, message_id: str):
        super().__init__(timeout=None)
        self.message_id = str(message_id)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="🎉", custom_id="giveaway_entry_btn")
    async def enter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        msg_id = str(interaction.message.id)

        entered, count = db.toggle_giveaway_entry_db(msg_id, str(user.id))

        if entered:
            await interaction.response.send_message(
                f"{get_emoji('success', guild)} **You entered the giveaway!** Total entries: `{count}`",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{get_emoji('cancel', guild)} **You left the giveaway.** Total entries: `{count}`",
                ephemeral=True
            )

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_checker.start()

    def cog_unload(self):
        self.giveaway_checker.cancel()

    @tasks.loop(seconds=10)
    async def giveaway_checker(self):
        current_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        active_giveaways = db.get_active_giveaways_db()

        for g in active_giveaways:
            if current_ts >= g["end_timestamp"]:
                await self.finish_giveaway(g)

    @giveaway_checker.before_loop
    async def before_giveaway_checker(self):
        await self.bot.wait_until_ready()

    async def finish_giveaway(self, giveaway_data: dict):
        msg_id = str(giveaway_data["message_id"])
        guild_id = int(giveaway_data["guild_id"])
        channel_id = int(giveaway_data["channel_id"])
        prize = giveaway_data["prize"]
        winners_count = giveaway_data["winners_count"]
        entries = json.loads(giveaway_data["entries"])

        guild = self.bot.get_guild(guild_id)
        if not guild:
            db.end_giveaway_db(msg_id)
            return

        channel = guild.get_channel(channel_id)
        db.end_giveaway_db(msg_id)

        winners = []
        if entries:
            # Pick unique winners
            k = min(len(entries), winners_count)
            winner_ids = random.sample(entries, k)
            for uid in winner_ids:
                try:
                    u = await self.bot.fetch_user(int(uid))
                    winners.append(u)
                except Exception:
                    pass

        # Update Giveaway Message
        if channel:
            try:
                msg = await channel.fetch_message(int(msg_id))
                if winners:
                    winner_mentions = ", ".join([w.mention for w in winners])
                    desc = (
                        f"🎉 **GIVEAWAY ENDED** 🎉\n\n"
                        f"🎁 **Prize:** **{prize}**\n"
                        f"🏆 **Winner(s):** {winner_mentions}\n"
                        f"👤 **Host:** <@{giveaway_data['host_id']}> • 🎟️ **Total Entries:** `{len(entries)}`"
                    )
                    embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)
                    await msg.edit(embed=embed, view=None)

                    # Send congratulations announcement
                    congrat_desc = (
                        f"🎉 **Congratulations {winner_mentions}!**\n"
                        f"You won **{prize}** in **{guild.name}**!"
                    )
                    await channel.send(embed=joyst_embed(description=congrat_desc, color=COLOR_SUCCESS, guild=guild))
                else:
                    desc = (
                        f"🎉 **GIVEAWAY ENDED** 🎉\n\n"
                        f"🎁 **Prize:** **{prize}**\n"
                        f"⚠️ **Winner:** Could not determine winner (No valid entries)."
                    )
                    embed = joyst_embed(description=desc, color=COLOR_DARK, guild=guild)
                    await msg.edit(embed=embed, view=None)
            except Exception as e:
                logger.error(f"Error updating giveaway message {msg_id}: {e}")

    async def _do_start_giveaway(self, ctx_or_interaction, duration: str, winners: int, prize: str, target_channel: discord.TextChannel = None):
        guild = ctx_or_interaction.guild
        channel = target_channel or ctx_or_interaction.channel
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        seconds = parse_duration(duration)
        if seconds <= 0:
            embed = joyst_embed(description="⚠️ Invalid duration format (e.g. `10m`, `2h`, `7d`).", color=COLOR_WARNING, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        if winners <= 0:
            winners = 1

        end_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + seconds

        desc = (
            f"🎉 **GIVEAWAY STARTED** 🎉\n\n"
            f"🎁 **Prize:** **{prize}**\n"
            f"🏆 **Winners:** `{winners}`\n"
            f"⏱️ **Ends:** <t:{end_ts}:R> (<t:{end_ts}:f>)\n"
            f"👤 **Host:** {author.mention}\n\n"
            f"Click the **Enter Giveaway** button below to participate!"
        )
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(f"✅ Giveaway deployed to {channel.mention}!", ephemeral=True)
            msg = await channel.send(embed=embed)
        else:
            msg = await channel.send(embed=embed)

        # Attach Interactive Button View with Message ID
        view = GiveawayEntryView(str(msg.id))
        await msg.edit(view=view)

        db.add_giveaway_db(
            guild_id=str(guild.id),
            channel_id=str(channel.id),
            message_id=str(msg.id),
            prize=prize,
            winners_count=winners,
            end_timestamp=end_ts,
            host_id=str(author.id)
        )

        db.add_audit_log(str(guild.id), "GIVEAWAY_START", f"Started giveaway '{prize}' for {winners} winners ({duration}).", str(author.id), str(author), "LOW")

    async def _do_end_giveaway(self, ctx_or_interaction, message_id: str):
        guild = ctx_or_interaction.guild
        gdata = db.get_giveaway_db(message_id)

        if not gdata or gdata["guild_id"] != str(guild.id):
            embed = joyst_embed(description="⚠️ Giveaway not found or already ended.", color=COLOR_WARNING, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        await self.finish_giveaway(gdata)
        embed = joyst_embed(description=f"✅ Giveaway `{message_id}` force ended.", color=COLOR_SUCCESS, guild=guild)
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _do_reroll_giveaway(self, ctx_or_interaction, message_id: str):
        guild = ctx_or_interaction.guild
        gdata = db.get_giveaway_db(message_id)

        if not gdata or gdata["guild_id"] != str(guild.id):
            embed = joyst_embed(description="⚠️ Giveaway record not found.", color=COLOR_WARNING, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        entries = json.loads(gdata["entries"])
        if not entries:
            embed = joyst_embed(description="⚠️ Cannot reroll: No entries in giveaway.", color=COLOR_WARNING, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        new_winner_id = random.choice(entries)
        try:
            winner_user = await self.bot.fetch_user(int(new_winner_id))
            channel = guild.get_channel(int(gdata["channel_id"]))
            
            desc = (
                f"🎉 **GIVEAWAY REROLL** 🎉\n\n"
                f"🎁 **Prize:** **{gdata['prize']}**\n"
                f"🏆 **New Winner:** {winner_user.mention}!"
            )
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)
            
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)

            if channel:
                await channel.send(f"🎉 **Reroll Winner:** Congratulations {winner_user.mention}, you won **{gdata['prize']}**!")
        except Exception as e:
            await ctx_or_interaction.send(f"❌ Reroll error: {e}")

    # --- Commands ---

    @commands.group(name="giveaway", aliases=["g", "gstart"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway(self, ctx, duration: str = None, winners: int = 1, *, prize: str = None):
        if duration and prize:
            await self._do_start_giveaway(ctx, duration, winners, prize)
        else:
            embed = joyst_embed(description="🎉 **Usage:** `!giveaway start <time> <winners> <prize>` (e.g. `!g 24h 1 Discord Nitro`)", color=COLOR_INFO, guild=ctx.guild)
            await ctx.send(embed=embed)

    @prefix_giveaway.command(name="start")
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        await self._do_start_giveaway(ctx, duration, winners, prize)

    @prefix_giveaway.command(name="end", aliases=["gend"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway_end(self, ctx, message_id: str):
        await self._do_end_giveaway(ctx, message_id)

    @prefix_giveaway.command(name="reroll", aliases=["greroll"])
    @commands.has_permissions(manage_guild=True)
    async def prefix_giveaway_reroll(self, ctx, message_id: str):
        await self._do_reroll_giveaway(ctx, message_id)

    @prefix_giveaway.command(name="list", aliases=["glist"])
    async def prefix_giveaway_list(self, ctx):
        active_g = db.get_active_giveaways_db(str(ctx.guild.id))
        if not active_g:
            await ctx.send("ℹ️ No active giveaways in this server.")
            return

        lines = [f"• Msg ID: `{g['message_id']}` — Prize: **{g['prize']}** (Ends: <t:{g['end_timestamp']}:R>)" for g in active_g]
        desc = f"🎉 **Active Giveaways (`{len(active_g)}` total)**:\n\n" + "\n".join(lines)
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=ctx.guild)
        await ctx.send(embed=embed)

    # --- Slash Commands ---

    giveaway_group = app_commands.Group(name="giveaway", description=f"{config.SERVER_NAME} Giveaway Management Commands")

    @giveaway_group.command(name="start", description="Start an interactive giveaway in a channel")
    @app_commands.describe(duration="Giveaway duration (e.g. 10m, 2h, 7d)", winners="Number of winners", prize="Prize title/description", channel="Target channel (optional)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_giveaway_start(self, interaction: discord.Interaction, duration: str, winners: int, prize: str, channel: discord.TextChannel = None):
        await self._do_start_giveaway(interaction, duration, winners, prize, channel)

    @giveaway_group.command(name="end", description="Force end an active giveaway immediately")
    @app_commands.describe(message_id="Giveaway message ID")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_giveaway_end(self, interaction: discord.Interaction, message_id: str):
        await self._do_end_giveaway(interaction, message_id)

    @giveaway_group.command(name="reroll", description="Pick a new winner for an ended giveaway")
    @app_commands.describe(message_id="Giveaway message ID")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_giveaway_reroll(self, interaction: discord.Interaction, message_id: str):
        await self._do_reroll_giveaway(interaction, message_id)

    @giveaway_group.command(name="list", description="List all active giveaways in the server")
    async def slash_giveaway_list(self, interaction: discord.Interaction):
        active_g = db.get_active_giveaways_db(str(interaction.guild_id))
        if not active_g:
            await interaction.response.send_message("ℹ️ No active giveaways in this server.", ephemeral=True)
            return

        lines = [f"• Msg ID: `{g['message_id']}` — Prize: **{g['prize']}** (Ends: <t:{g['end_timestamp']}:R>)" for g in active_g]
        desc = f"🎉 **Active Giveaways (`{len(active_g)}` total)**:\n\n" + "\n".join(lines)
        embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=interaction.guild)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Giveaway(bot))

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
import datetime
import database as db
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji

logger = logging.getLogger("AEGIS.Tickets")

# --- Ticket King Control Panel inside Private Ticket Channel ---

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_owner_id: int = None):
        super().__init__(timeout=None)
        self.ticket_owner_id = ticket_owner_id
        self.claimed_by = None

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user

        embed = joyst_embed(
            description=f"{get_emoji('warning', guild)} **Ticket Closing:** Ticket channel will be deleted in `5 seconds` by {user.mention}.",
            color=COLOR_WARNING,
            guild=guild
        )
        await interaction.response.send_message(embed=embed)

        # Record ticket close in DB
        db.close_ticket_db(str(channel.id))
        db.add_audit_log(str(guild.id), "TICKET_CLOSE", f"Ticket channel #{channel.name} closed by {user}.", severity="INFO")

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"[{config.SERVER_NAME} Ticket King] Closed by {user}.")
        except Exception as e:
            logger.error(f"Error deleting ticket channel: {e}")

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, emoji="📜", custom_id="ticket_claim_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        if not (user.id == guild.owner_id or (hasattr(user, "guild_permissions") and (user.guild_permissions.manage_guild or user.guild_permissions.administrator))):
            await interaction.response.send_message(f"{get_emoji('cancel', guild)} Only Support Staff or Admins can claim tickets.", ephemeral=True)
            return

        if self.claimed_by:
            await interaction.response.send_message(f"⚠️ This ticket is already claimed by <@{self.claimed_by}>.", ephemeral=True)
            return

        self.claimed_by = user.id
        button.disabled = True
        button.label = f"Claimed by {user.name}"
        await interaction.message.edit(view=self)

        embed = joyst_embed(
            description=f"{get_emoji('success', guild)} **Ticket Claimed!** Staff {user.mention} is now assigned to handle this ticket.",
            color=COLOR_SUCCESS,
            guild=guild
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📄", custom_id="ticket_transcript_btn")
    async def transcript_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True)

        messages = []
        async for msg in channel.history(limit=200, oldest_first=True):
            if not msg.author.bot:
                messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author}: {msg.content}")

        transcript_text = "\n".join(messages) if messages else "No user messages recorded."
        
        embed = joyst_embed(
            title=f"📄 Ticket Transcript — #{channel.name}",
            description=f"```text\n{transcript_text[:3800]}\n```",
            color=COLOR_INFO,
            guild=guild
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

# --- Ticket King Dropdown Select Category Menu ---

class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="General Support",
                value="general",
                description="Questions, general assistance & server help",
                emoji="🎫"
            ),
            discord.SelectOption(
                label="Technical & Bug Report",
                value="tech",
                description="Report bugs, bot errors or technical issues",
                emoji="🛠️"
            ),
            discord.SelectOption(
                label="Billing & Purchases",
                value="billing",
                description="Panel purchase, VIP, boosts & billing queries",
                emoji="💎"
            ),
            discord.SelectOption(
                label="Player Report & Appeals",
                value="appeal",
                description="Report rule violations or appeal timeouts/bans",
                emoji="🛡️"
            ),
            discord.SelectOption(
                label="Partnerships & Business",
                value="partner",
                description="Server partnerships, sponsorships & collabs",
                emoji="🤝"
            )
        ]
        super().__init__(
            placeholder=" Choose Ticket Category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_king_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category_choice = self.values[0]
        guild = interaction.guild
        user = interaction.user

        clean_username = user.name.lower().replace(" ", "-")
        target_name = f"ticket-{category_choice}-{clean_username}"

        # Check for existing open ticket for user in this category
        for ch in guild.text_channels:
            if ch.name == target_name:
                await interaction.followup.send(
                    f"{get_emoji('warning', guild)} You already have an open ticket in {ch.mention}!",
                    ephemeral=True
                )
                return

        # Create or fetch Category
        cat_name = "🎫 SUPPORT TICKETS"
        category = discord.utils.get(guild.categories, name=cat_name)
        if not category:
            try:
                category = await guild.create_category(cat_name)
            except Exception:
                category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_ch = await guild.create_text_channel(
                name=target_name,
                category=category,
                overwrites=overwrites,
                reason=f"[{config.SERVER_NAME} Support] Category: {category_choice} for {user}."
            )

            db.add_ticket_db(str(guild.id), str(user.id), str(ticket_ch.id))
            db.add_audit_log(str(guild.id), "TICKET_CREATE", f"Opened ticket #{ticket_ch.name} (Category: {category_choice}) for user {user}.", severity="INFO")

            cat_titles = {
                "general": "🎫 General Support & Assistance",
                "tech": "🛠️ Technical Support & Bug Report",
                "billing": "💎 Billing, Purchases & VIP Vault",
                "appeal": "🛡️ Player Report & Ban Appeal",
                "partner": "🤝 Partnerships & Business Inquiry"
            }

            welcome_desc = (
                f"🎟️ **Welcome to {cat_titles.get(category_choice, 'Support')}!**\n\n"
                f"Hello {user.mention}, thank you for reaching out to **{guild.name} Staff**!\n"
                f"Please state your issue or request in detail below.\n\n"
                f"• **🔒 Close Ticket:** End conversation & delete channel.\n"
                f"• **📜 Claim Ticket:** Staff lock & assignment.\n"
                f"• **📄 Transcript:** Export message transcript."
            )

            embed = joyst_embed(description=welcome_desc, color=COLOR_PURPLE, guild=guild)
            embed.set_footer(text=f"{config.SERVER_NAME} Ticket King Engine • Instant Response")

            view = TicketControlView(ticket_owner_id=user.id)
            await ticket_ch.send(content=f"{user.mention} Welcome to your support ticket!", embed=embed, view=view)

            await interaction.followup.send(
                f"{get_emoji('success', guild)} **Ticket Created:** {ticket_ch.mention}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating ticket channel: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to create ticket channel: {e}", ephemeral=True)

class TicketKingDropdownView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _do_setup_tickets(self, ctx_or_interaction, target_channel: discord.TextChannel = None, title: str = None, description: str = None):
        guild = ctx_or_interaction.guild
        channel = target_channel or ctx_or_interaction.channel

        panel_title = title or f"👑 **{config.SERVER_NAME} Ticket King Support Hub**"
        panel_desc = description or (
            f"Welcome to **{config.SERVER_NAME} Official Support Center**!\n\n"
            f"Select your inquiry category from the dropdown menu below to open a private 1-on-1 support ticket with our team.\n\n"
            f"• 🎫 **General Support:** Server help & general questions\n"
            f"• 🛠️ **Technical:** Bug reports & bot setup assistance\n"
            f"• 💎 **Billing & VIP:** Panel purchases & rank upgrades\n"
            f"• 🛡️ **Appeals:** Report players or appeal mutes/bans\n"
            f"• 🤝 **Partnerships:** Collabs & sponsorship deals"
        )

        embed = joyst_embed(title=panel_title, description=panel_desc, color=COLOR_PURPLE, guild=guild)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"{config.SERVER_NAME} Ticket King OS • Select Category Below")

        view = TicketKingDropdownView()

        if isinstance(ctx_or_interaction, discord.Interaction):
            await channel.send(embed=embed, view=view)
            await ctx_or_interaction.response.send_message(f"✅ Ticket King Dropdown Panel deployed to {channel.mention}!", ephemeral=True)
        else:
            await channel.send(embed=embed, view=view)
            await ctx_or_interaction.send(f"✅ Ticket King Dropdown Panel deployed to {channel.mention}!")

    # --- Commands ---

    @commands.group(name="ticket", invoke_without_command=True)
    async def prefix_ticket(self, ctx):
        await self._do_setup_tickets(ctx)

    @prefix_ticket.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def prefix_ticket_setup(self, ctx, channel: discord.TextChannel = None):
        await self._do_setup_tickets(ctx, channel)

    @commands.command(name="close")
    async def prefix_close(self, ctx):
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("⚠️ This command can only be used inside ticket channels.")
            return

        embed = joyst_embed(description=f"{get_emoji('warning', ctx.guild)} Closing ticket channel in 5 seconds...", color=COLOR_WARNING, guild=ctx.guild)
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await ctx.channel.delete()
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")

    # --- Slash Commands ---

    ticket_group = app_commands.Group(name="ticket", description=f"{config.SERVER_NAME} Ticket King Support Commands")

    @ticket_group.command(name="setup", description="Deploy the Ticket King Multi-Category Dropdown Support Panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_ticket_setup(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await self._do_setup_tickets(interaction, channel)

    @ticket_group.command(name="close", description="Close current ticket channel")
    async def slash_ticket_close(self, interaction: discord.Interaction):
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("⚠️ This command can only be used inside ticket channels.", ephemeral=True)
            return

        embed = joyst_embed(description=f"{get_emoji('warning', interaction.guild)} Closing ticket channel in 5 seconds...", color=COLOR_WARNING, guild=interaction.guild)
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")

async def setup(bot):
    await bot.add_cog(Tickets(bot))

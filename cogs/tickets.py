import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import io
import asyncio
import os
import logging
from datetime import datetime, timezone
try:
    import chat_exporter
    HAS_CHAT_EXPORTER = True
except ModuleNotFoundError:
    HAS_CHAT_EXPORTER = False
    logging.getLogger("AEGIS.Tickets").warning("chat_exporter module not installed. Fallback transcript exporter active.")

import config
import database as db
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO

logger = logging.getLogger("AEGIS.Tickets")

TICKETS_DATA_FILE = 'tickets_data.json'
CONFIG_FILE = 'config.json'

# ===========================
# CONFIG LOAD / SAVE
# ===========================
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config.json: {e}")
    return {}

def save_config(data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving config.json: {e}")

# ===========================
# TICKETS DATA LOAD / SAVE
# ===========================
def load_tickets_data():
    try:
        if os.path.exists(TICKETS_DATA_FILE):
            with open(TICKETS_DATA_FILE, 'r') as f:
                data = json.load(f)
                if "staff_stats" not in data:
                    data["staff_stats"] = {}
                if "active" not in data:
                    data["active"] = {}
                if "closed" not in data:
                    data["closed"] = {}
                return data
    except Exception as e:
        logger.error(f"Error loading tickets_data.json: {e}")
    return {"active": {}, "closed": {}, "staff_stats": {}}

def save_tickets_data(data):
    try:
        with open(TICKETS_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving tickets_data.json: {e}")

tickets_data = load_tickets_data()
open_tickets = tickets_data.get("active", {})

# ===========================
# HELPERS
# ===========================
def is_strict_admin(user: discord.User) -> bool:
    cfg = load_config()
    admin_id = cfg.get('admin_user_id')
    if admin_id and str(user.id) == str(admin_id):
        return True
    if hasattr(user, "guild_permissions") and user.guild_permissions:
        return user.guild_permissions.administrator or user.guild_permissions.manage_guild
    return False

def has_backup_role(user_roles: list) -> bool:
    REQUIRED_BACKUP_ROLE_ID = 1384457502284058685
    for role in user_roles:
        if role.id == REQUIRED_BACKUP_ROLE_ID:
            return True
    return False

def get_ticket_data_by_channel_id(channel_id: int):
    # active tickets
    for user_id, data in open_tickets.items():
        if data.get("channel_id") == channel_id:
            return {"user_id": user_id, **data}

    # closed tickets
    closed_ticket = tickets_data.get("closed", {}).get(str(channel_id))
    if closed_ticket:
        return closed_ticket

    return None

def cleanup_stuck_ticket(user_id: str, guild: discord.Guild) -> bool:
    if user_id not in open_tickets:
        return False

    ch_id = open_tickets[user_id].get("channel_id")
    if not ch_id:
        del open_tickets[user_id]
        tickets_data["active"] = open_tickets
        save_tickets_data(tickets_data)
        return True

    ch = guild.get_channel(int(ch_id))

    if ch is None:
        del open_tickets[user_id]
        tickets_data["active"] = open_tickets
        save_tickets_data(tickets_data)
        return True

    if isinstance(ch, discord.TextChannel) and ch.name.startswith("closed-"):
        del open_tickets[user_id]
        tickets_data["active"] = open_tickets
        save_tickets_data(tickets_data)
        return True

    return False

async def can_manage_ticket_command_check(interaction_or_ctx) -> bool:
    cfg = load_config()
    user = interaction_or_ctx.user if isinstance(interaction_or_ctx, discord.Interaction) else interaction_or_ctx.author
    guild = interaction_or_ctx.guild
    channel = interaction_or_ctx.channel

    admin_id = cfg.get('admin_user_id')
    if admin_id and str(user.id) == str(admin_id):
        return True

    if hasattr(user, "guild_permissions") and user.guild_permissions:
        if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
            return True

    if not isinstance(channel, discord.TextChannel):
        return False

    ticket_data = get_ticket_data_by_channel_id(channel.id)
    if not ticket_data:
        return False

    ticket_type = ticket_data.get("type")
    role_id_str = cfg.get(f'{ticket_type}_role_id')

    # If the ticket is claimed, only the claiming staff member (or admin) can manage it
    claimed_by = ticket_data.get("claimed_by")
    if claimed_by and str(user.id) != claimed_by:
        return False

    if role_id_str:
        try:
            role_id = int(role_id_str)
            required_role = guild.get_role(role_id)
            if required_role and required_role in user.roles:
                return True
        except ValueError:
            pass

    return True

# ===========================
# MODAL
# ===========================
class TicketModal(discord.ui.Modal):
    def __init__(self, ticket_type: str, *args, **kwargs) -> None:
        super().__init__(title=f"{ticket_type.capitalize()} Request", *args, **kwargs)
        self.ticket_type = ticket_type
        self.request = discord.ui.TextInput(
            label=self.get_label(),
            style=discord.TextStyle.paragraph,
            min_length=5,
            max_length=1000
        )
        self.add_item(self.request)
        self.response_value = None

    def get_label(self):
        if self.ticket_type == "purchase":
            return "Product Name & Details"
        elif self.ticket_type == "exchange":
            return "Currencies & Amount (e.g., I2C to C2I)"
        elif self.ticket_type == "support":
            return "Reason for Support (be detailed)"
        elif self.ticket_type == "tools":
            return "Tool Name & Specific Request"
        return "Details of your request"

    async def on_submit(self, interaction: discord.Interaction):
        self.response_value = self.request.value
        await interaction.response.defer(ephemeral=True, thinking=False)
        self.stop()

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Error in TicketModal: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("An error occurred with the form. Please try again.", ephemeral=True)
        else:
            await interaction.followup.send("An error occurred with the form. Please try again.", ephemeral=True)
        self.stop()

# ===========================
# REMINDER DM SYSTEM
# ===========================
async def send_ticket_reminder_dm(bot_instance: commands.Bot, user_id: int, guild: discord.Guild, ticket_channel: discord.TextChannel, ticket_type: str = None):
    user_obj = bot_instance.get_user(user_id)
    if not user_obj:
        user_obj = await bot_instance.fetch_user(user_id)

    if not ticket_type:
        ticket_data = get_ticket_data_by_channel_id(ticket_channel.id)
        if ticket_data:
            ticket_type = ticket_data.get("type", "Support")
        else:
            ticket_type = "Support"

    embed = discord.Embed(
        title="🔔 **TICKET REMINDER** 🔔",
        description=f"### 📬 **You have an open ticket in {guild.name}**\n\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"**🎟️ Ticket Channel:** {ticket_channel.mention}\n"
                   f"**📋 Ticket Type:** `{ticket_type.capitalize()}`\n"
                   f"**⏰ Created:** <t:{int(datetime.now().timestamp())}:R>\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                   f"### ⚠️ **Action Required!**\n"
                   f"• Please complete your deal or clarify any doubts in your ticket.\n"
                   f"• If your issue is resolved, kindly request the staff to close the ticket.\n"
                   f"• **Unresolved tickets may be closed after 48 hours of inactivity.**\n\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"### ✅ **Next Steps:**\n"
                   f"1️⃣ Reply in your ticket channel with updates\n"
                   f"2️⃣ Tag the staff if you need immediate assistance\n"
                   f"3️⃣ Click the button below to open your ticket\n\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"*Thank you for choosing Joyst Corporation!*",
        color=discord.Color.from_rgb(255, 165, 0)
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.set_footer(text="© Joyst Corporation | Ticket System", icon_url=bot_instance.user.avatar.url if bot_instance.user and bot_instance.user.avatar else None)
    embed.timestamp = datetime.now()

    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="🎫 Open My Ticket",
            style=discord.ButtonStyle.link,
            url=ticket_channel.jump_url,
            emoji="📬"
        )
    )

    await user_obj.send(embed=embed, view=view)

async def send_in_channel_reminder(channel: discord.TextChannel, user_mention: str):
    embed = discord.Embed(
        title="🔔 **REMINDER** 🔔",
        description=f"### {user_mention}\n\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"**⏰ Your ticket has been inactive!**\n\n"
                   f"• Please complete your deal or clarify any doubts\n"
                   f"• If you're waiting for staff, kindly be patient\n"
                   f"• **If your issue is resolved, let us know so we can close the ticket**\n\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"### 📝 **What you can do:**\n"
                   f"> `,close` - Close this ticket when done\n"
                   f"> `,remind` - Send another reminder\n"
                   f"> Reply here - Continue your conversation\n\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"*Tickets inactive for 48 hours may be automatically closed.*",
        color=discord.Color.orange()
    )
    embed.set_footer(text="Joyst Corporation Ticket System")
    embed.timestamp = datetime.now()
    
    await channel.send(embed=embed)

# ===========================
# TRANSCRIPT SYSTEM
# ===========================
async def send_transcript(channel: discord.TextChannel, ticket_owner_id: str, ticket_type: str, bot_instance: commands.Bot, is_mass_operation: bool = False, operation_type: str = "closed"):
    cfg = load_config()
    transcript_channel_config = cfg.get('transcript_channels', {})
    transcript_log_channel_id_str = transcript_channel_config.get(ticket_type)

    ticket_owner_user = None
    if ticket_owner_id != "unknown_owner":
        try:
            ticket_owner_id_int = int(ticket_owner_id)
            ticket_owner_user = bot_instance.get_user(ticket_owner_id_int)
            if not ticket_owner_user:
                try:
                    ticket_owner_user = await bot_instance.fetch_user(ticket_owner_id_int)
                except Exception:
                    pass
        except ValueError:
            pass

    try:
        html_content = None
        if HAS_CHAT_EXPORTER:
            try:
                html_content = await chat_exporter.export(
                    channel,
                    guild=channel.guild,
                    bot=bot_instance,
                    tz_info="UTC"
                )
            except Exception as e_exp:
                logger.error(f"chat_exporter error: {e_exp}")
                html_content = None

        if not html_content:
            lines = [f"Ticket Transcript for #{channel.name} (ID: {channel.id})\nGenerated: {datetime.now(timezone.utc)}\n" + "="*60 + "\n"]
            async for msg in channel.history(limit=500, oldest_first=True):
                lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author} ({msg.author.id}): {msg.content}")
            html_content = "\n".join(lines)

        html_content_bytes = html_content.encode('utf-8') if isinstance(html_content, str) else html_content

        # DM owner transcript
        if ticket_owner_user:
            file_for_dm = discord.File(io.BytesIO(html_content_bytes), filename=f"{channel.name}-transcript-{ticket_owner_id}.html")
            
            if is_mass_operation:
                dm_message = f"## 📋 **Ticket {operation_type.capitalize()} - Mass Cleanup**\n\nYour ticket **{channel.name}** has been {operation_type} as part of a server mass cleanup operation.\n\n📎 **Transcript attached below**\n\nIf you need further assistance, please create a new ticket using the panel."
            else:
                dm_message = f"## 📋 **Ticket Transcript**\n\nHere is the transcript for your ticket **{channel.name}**.\n\n📎 **Transcript attached below**"
            
            try:
                await ticket_owner_user.send(dm_message, file=file_for_dm)
            except Exception as e_dm:
                logger.error(f"Error sending transcript to DM for {ticket_owner_id}: {e_dm}")

        # Log channel transcript
        if transcript_log_channel_id_str:
            try:
                transcript_log_channel_id = int(transcript_log_channel_id_str)
                log_channel = bot_instance.get_channel(transcript_log_channel_id)

                if log_channel and isinstance(log_channel, discord.TextChannel):
                    file_for_log = discord.File(io.BytesIO(html_content_bytes), filename=f"{channel.name}-transcript-{ticket_owner_id}.html")
                    owner_display = ticket_owner_user.mention if ticket_owner_user else f"UserID: `{ticket_owner_id}`"

                    embed = discord.Embed(
                        title="📄 Ticket Transcript Logged",
                        description=f"Transcript for: <#{channel.id}> (`{channel.name}`)",
                        color=discord.Color.greyple()
                    )
                    embed.add_field(name="👤 Ticket Owner", value=owner_display, inline=True)
                    embed.add_field(name="📋 Ticket Type", value=ticket_type.capitalize(), inline=True)
                    if is_mass_operation:
                        embed.add_field(name="⚠️ Note", value=f"{operation_type.capitalize()} via Mass Cleanup", inline=True)
                    embed.set_footer(text=f"Channel ID: {channel.id} | User ID: {ticket_owner_id}")
                    embed.timestamp = datetime.now()

                    await log_channel.send(embed=embed, file=file_for_log)
            except Exception as e_log:
                logger.error(f"Error sending transcript to log channel: {e_log}")

    except Exception as e_transcript:
        logger.error(f"Error during transcript generation in {channel.name}: {e_transcript}")

# ===========================
# PERSISTENT VIEWS
# ===========================
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_via_button", emoji="🔒")
    async def close_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This is not a valid ticket channel.", ephemeral=True)
            return

        if channel.name.startswith("closed-"):
            await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
            return

        await interaction.response.defer()

        ticket_data = get_ticket_data_by_channel_id(channel.id)
        if not ticket_data:
            await interaction.followup.send("Error: Ticket data not found. Cannot close.", ephemeral=True)
            return

        ticket_owner_id = ticket_data["user_id"]
        ticket_type = ticket_data.get("type", "unknown")

        ticket_owner_member = interaction.guild.get_member(int(ticket_owner_id))
        if ticket_owner_member:
            try:
                current_overwrites = channel.overwrites_for(ticket_owner_member)
                current_overwrites.view_channel = False
                current_overwrites.read_messages = False
                current_overwrites.send_messages = False
                await channel.set_permissions(ticket_owner_member, overwrite=current_overwrites, reason="Ticket closing by button")
            except Exception as e:
                logger.error(f"Error removing perms in {channel.name}: {e}")

        cog = interaction.client.get_cog("Tickets")
        bot_inst = cog.bot if cog else interaction.client
        await send_transcript(channel, ticket_owner_id, ticket_type, bot_inst, is_mass_operation=False, operation_type="closed")

        closing_embed = discord.Embed(
            title="🔒 Ticket Closing", 
            description="⏰ This ticket will close in **5** seconds...",
            color=discord.Color.orange()
        )
        msg_closing = await channel.send(embed=closing_embed)

        for i in range(5, 0, -1):
            closing_embed.description = f"⏰ This ticket will close in **{i}** seconds..."
            await msg_closing.edit(embed=closing_embed)
            await asyncio.sleep(1)

        if ticket_owner_id in open_tickets:
            ticket_info = open_tickets[ticket_owner_id]

            tickets_data["closed"][str(channel.id)] = {
                "user_id": ticket_owner_id,
                "channel_id": channel.id,
                "type": ticket_info.get("type", "unknown"),
                "owner_name": ticket_info.get("owner_name", "Unknown"),
                "closed_at": datetime.now().isoformat(),
                "closed_by": str(interaction.user.id),
                "closed_by_name": interaction.user.name
            }

            del open_tickets[ticket_owner_id]
            tickets_data["active"] = open_tickets

            staff_id = str(interaction.user.id)
            stats = tickets_data.get("staff_stats", {})
            if staff_id not in stats:
                stats[staff_id] = {"claimed": 0, "closed": 0, "username": interaction.user.name}
            stats[staff_id]["closed"] += 1
            stats[staff_id]["username"] = interaction.user.name
            tickets_data["staff_stats"] = stats

            save_tickets_data(tickets_data)

        base_name = channel.name
        new_channel_name = f"closed-{base_name[:80]}"
        try:
            await channel.edit(name=new_channel_name, reason=f"Ticket closed by {interaction.user.name}")
        except Exception:
            pass

        closing_embed.title = "✅ Ticket Closed"
        closing_embed.description = "📦 This ticket has been archived for staff review."
        closing_embed.color = discord.Color.dark_red()
        await msg_closing.edit(embed=closing_embed)

        button.disabled = True
        button.label = "Closed"
        
        try:
            await interaction.edit_original_response(view=self)
        except Exception:
            pass

class TicketClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🙋‍♂️ Claim Ticket", style=discord.ButtonStyle.success, custom_id="claim_ticket_via_button", emoji="🙋‍♂️")
    async def claim_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This is not a valid ticket channel.", ephemeral=True)
            return

        ticket_data = get_ticket_data_by_channel_id(channel.id)
        if not ticket_data:
            await interaction.response.send_message("❌ Ticket data not found.", ephemeral=True)
            return

        claimed_by = ticket_data.get("claimed_by")
        if claimed_by:
            claimed_by_name = ticket_data.get("claimed_by_name", "Unknown")
            await interaction.response.send_message(f"❌ This ticket is already claimed by **{claimed_by_name}**.", ephemeral=True)
            return

        await interaction.response.defer()

        ticket_owner_id = ticket_data["user_id"]
        if ticket_owner_id not in open_tickets:
            await interaction.followup.send("❌ This ticket is not active or has been closed.", ephemeral=True)
            return
        
        open_tickets[ticket_owner_id]["claimed_by"] = str(interaction.user.id)
        open_tickets[ticket_owner_id]["claimed_by_name"] = interaction.user.name
        tickets_data["active"] = open_tickets

        staff_id = str(interaction.user.id)
        stats = tickets_data.get("staff_stats", {})
        if staff_id not in stats:
            stats[staff_id] = {"claimed": 0, "closed": 0, "username": interaction.user.name}
        stats[staff_id]["claimed"] += 1
        stats[staff_id]["username"] = interaction.user.name
        tickets_data["staff_stats"] = stats

        save_tickets_data(tickets_data)

        cfg = load_config()
        ticket_type = ticket_data.get("type", "unknown")
        role_id_str = cfg.get(f'{ticket_type}_role_id')
        
        guild = interaction.guild
        overwrites_to_update = {}
        
        if role_id_str:
            try:
                role_to_mention = guild.get_role(int(role_id_str))
                if role_to_mention:
                    role_overwrite = channel.overwrites_for(role_to_mention)
                    role_overwrite.send_messages = False
                    overwrites_to_update[role_to_mention] = role_overwrite
            except Exception as e:
                logger.error(f"Error getting staff role for overrides: {e}")

        claiming_member = interaction.user
        member_overwrite = channel.overwrites_for(claiming_member)
        member_overwrite.read_messages = True
        member_overwrite.send_messages = True
        member_overwrite.attach_files = True
        member_overwrite.embed_links = True
        overwrites_to_update[claiming_member] = member_overwrite

        try:
            for target, overwrite in overwrites_to_update.items():
                await channel.set_permissions(target, overwrite=overwrite, reason=f"Ticket claimed by {claiming_member.name}")
        except Exception as e:
            logger.error(f"Error updating permissions for ticket claim in {channel.name}: {e}")

        embed_claimed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"**👤 Claimed By:** {claiming_member.mention}\n"
                        f"**📋 Ticket Type:** `{ticket_type.capitalize()}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"• Only {claiming_member.mention} and the ticket creator can chat here now.\n"
                        f"• Other staff members can still view the channel but cannot send messages.\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=discord.Color.green()
        )
        embed_claimed.set_footer(text=f"Claimed by {claiming_member.name} | Joyst Corporation")
        embed_claimed.timestamp = datetime.now()

        button.disabled = True
        button.label = "Claimed"
        button.style = discord.ButtonStyle.secondary

        try:
            await interaction.edit_original_response(embed=embed_claimed, view=self)
        except Exception as e:
            logger.error(f"Error editing message with claimed view: {e}")

        await channel.send(f"🙋‍♂️ **Ticket claimed by {claiming_member.mention}!**")

class TicketFAQView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📄 Terms of Service", style=discord.ButtonStyle.secondary, custom_id="faq_tos_button", emoji="📄")
    async def tos_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = load_config()
        tos_text = cfg.get("faq_tos", "No ToS configured.")
        embed = discord.Embed(
            title="📄 Terms of Service",
            description=tos_text,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💰 Pricing & Catalog", style=discord.ButtonStyle.secondary, custom_id="faq_pricing_button", emoji="💰")
    async def pricing_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = load_config()
        pricing_text = cfg.get("faq_pricing", "No pricing info configured.")
        embed = discord.Embed(
            title="💰 Pricing & Catalog",
            description=pricing_text,
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="⚡ Payment Rules", style=discord.ButtonStyle.secondary, custom_id="faq_payment_rules_button", emoji="⚡")
    async def payment_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = load_config()
        payment_text = cfg.get("faq_payment_rules", "No payment rules configured.")
        embed = discord.Embed(
            title="⚡ Payment Rules",
            description=payment_text,
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

def parse_emoji_safe(emoji_str):
    if not emoji_str:
        return "🎫"
    try:
        if (emoji_str.startswith("<:") or emoji_str.startswith("<a:")) and emoji_str.endswith(">"):
            return discord.PartialEmoji.from_str(emoji_str)
    except Exception:
        pass
    return emoji_str

class TicketDropdown(discord.ui.Select):
    def __init__(self, bot_instance: commands.Bot):
        self.bot = bot_instance
        options = [
            discord.SelectOption(label="Purchase Here", value="purchase", description="For purchase related queries", emoji=parse_emoji_safe("<:client:1411727778092679199>")),
            discord.SelectOption(label="Buy Projects", value="exchange", description="For Purchasing Joyst Corporation Projects", emoji=parse_emoji_safe("<:trick_supreme:1411728276342308945>")),
            discord.SelectOption(label="Request Support", value="support", description="For technical support", emoji=parse_emoji_safe("<:warning:1396401353231831123>")),
            discord.SelectOption(label="Buy Tools", value="tools", description="To buy our tools", emoji=parse_emoji_safe("<:94046dev:1411728964380004413>"))
        ]
        super().__init__(
            placeholder="Click here to Buy Panel / Projects & For Support",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_type_dropdown"
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        if user_id in open_tickets:
            removed = cleanup_stuck_ticket(user_id, interaction.guild)
            if not removed:
                existing_ticket_channel_id = open_tickets[user_id].get("channel_id")
                await interaction.response.send_message(
                    f"❌ You already have an open ticket: <#{existing_ticket_channel_id}>.\nPlease close it before creating a new one.",
                    ephemeral=True
                )
                return

        selected_option = self.values[0]
        modal = TicketModal(ticket_type=selected_option)

        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()

        if timed_out or modal.response_value is None:
            try:
                await interaction.followup.send("Ticket creation cancelled or timed out.", ephemeral=True)
            except Exception:
                pass
            return

        guild = interaction.guild
        user = interaction.user

        sanitized_user_name = "".join(c for c in user.name if c.isalnum() or c in ['-', '_']).lower()
        if not sanitized_user_name:
            sanitized_user_name = "user"

        user_id_str = str(user.id)
        channel_name = f"{selected_option}-{sanitized_user_name[:20]}-{user_id_str[-4:]}"

        cfg = load_config()

        purchase_role_id = cfg.get('purchase_role_id')
        exchange_role_id = cfg.get('exchange_role_id')
        support_role_id = cfg.get('support_role_id')
        tools_role_id = cfg.get('tools_role_id')

        role_to_mention = None
        category_id = None
        staff_overwrites = {}

        if selected_option == "purchase":
            cat_val = cfg.get('purchase_category_id')
            if cat_val: category_id = int(cat_val)
            if purchase_role_id: role_to_mention = guild.get_role(int(purchase_role_id))

        elif selected_option == "exchange":
            cat_val = cfg.get('exchange_category_id')
            if cat_val: category_id = int(cat_val)
            if exchange_role_id: role_to_mention = guild.get_role(int(exchange_role_id))

        elif selected_option == "support":
            cat_val = cfg.get('support_category_id')
            if cat_val: category_id = int(cat_val)
            if support_role_id: role_to_mention = guild.get_role(int(support_role_id))

        elif selected_option == "tools":
            cat_val = cfg.get('tools_category_id')
            if cat_val: category_id = int(cat_val)
            if tools_role_id: role_to_mention = guild.get_role(int(tools_role_id))

        if role_to_mention:
            staff_overwrites[role_to_mention] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=False,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )

        if not category_id:
            category = discord.utils.get(guild.categories, name="TICKETS")
            if not category:
                category = await guild.create_category("TICKETS")
        else:
            category = guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                category = discord.utils.get(guild.categories, name="TICKETS")
                if not category:
                    category = await guild.create_category("TICKETS")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        overwrites.update(staff_overwrites)

        try:
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket created by {user.name}"
            )

            open_tickets[user_id] = {
                "channel_id": channel.id,
                "type": selected_option,
                "owner_name": user.name,
                "created_at": datetime.now().isoformat()
            }
            tickets_data["active"][user_id] = open_tickets[user_id]
            save_tickets_data(tickets_data)

            # 1. Main Ticket Embed
            embed = discord.Embed(
                title=f"🎫 {selected_option.capitalize()} Ticket Created",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                           f"**📋 Request Details:**\n```{discord.utils.escape_markdown(modal.response_value)}```\n"
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                           f"### ✅ **Next Steps:**\n"
                           f"• A staff member will assist you shortly\n"
                           f"• Please provide any additional details if needed\n"
                           f"• Use `,close` when your issue is resolved\n\n"
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.green()
            )
            embed.set_author(name=f"{user.name} ({user.id})", icon_url=user.avatar.url if user.avatar else user.default_avatar.url)
            embed.set_footer(text=f"Ticket ID: {channel.id} | Joyst Corporation")
            embed.timestamp = datetime.now()

            ticket_close_view = TicketCloseView()
            await channel.send(
                f"🎫 New ticket created by {user.mention}!",
                embed=embed,
                view=ticket_close_view
            )

            # 2. Claim Ticket Embed
            claim_embed = discord.Embed(
                title="⌛ Waiting for Staff Claim",
                description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"⏳ **This ticket is currently waiting to be claimed by a staff member.**\n"
                            f"• Staff members cannot send messages in this ticket until it is claimed.\n"
                            f"• Staff members: Click the **Claim Ticket** button below to claim this ticket.\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.orange()
            )
            claim_embed.set_footer(text="Joyst Corporation | Ticket Claim System")
            claim_embed.timestamp = datetime.now()

            ticket_claim_view = TicketClaimView()
            mention_message = f"{role_to_mention.mention if role_to_mention else ''}"
            await channel.send(
                content=mention_message,
                embed=claim_embed,
                view=ticket_claim_view
            )

            # 3. FAQ Panel Embed
            faq_embed = discord.Embed(
                title="📝 Quick FAQ & Information",
                description="### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "Click the buttons below to read our Terms of Service, pricing catalog, or payment rules.\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.blurple()
            )
            faq_embed.set_footer(text="Joyst Corporation | FAQ System")
            faq_embed.timestamp = datetime.now()
            
            ticket_faq_view = TicketFAQView()
            await channel.send(
                embed=faq_embed,
                view=ticket_faq_view
            )

            # 4. DM Alert Staff
            if role_to_mention:
                async def alert_staff_members():
                    for staff_member in role_to_mention.members:
                        if staff_member.bot:
                            continue
                        try:
                            dm_embed = discord.Embed(
                                title="🎟️ Joyst Corporation | New Ticket Alert",
                                description=f"### 📬 **New ticket created in {guild.name}**\n\n"
                                           f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                           f"**🎟️ Ticket Channel:** {channel.mention}\n"
                                           f"**📋 Ticket Type:** `{selected_option.capitalize()}`\n"
                                           f"**👤 Creator:** {user.name} ({user.mention})\n"
                                           f"**⏰ Time:** <t:{int(datetime.now().timestamp())}:R>\n"
                                           f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                           f"### 📋 **Details / Reason:**\n"
                                           f"```{discord.utils.escape_markdown(modal.response_value)}```\n\n"
                                           f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                           f"Please click the button below to view and claim this ticket.",
                                color=discord.Color.from_rgb(0, 200, 200)
                            )
                            dm_view = discord.ui.View()
                            dm_view.add_item(
                                discord.ui.Button(
                                    label="🎫 Go To Ticket",
                                    style=discord.ButtonStyle.link,
                                    url=channel.jump_url
                                )
                            )
                            await staff_member.send(embed=dm_embed, view=dm_view)
                        except Exception:
                            pass
                
                asyncio.create_task(alert_staff_members())

            await interaction.followup.send(f"✅ Ticket created successfully! <#{channel.id}>", ephemeral=True)

        except Exception as e_create:
            logger.error(f"Error creating channel: {e_create}")
            await interaction.followup.send(f"Error creating ticket channel: `{e_create}`", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self, bot_instance: commands.Bot = None):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(bot_instance=bot_instance))

# Backward compatibility alias
TicketKingDropdownView = TicketView
TicketControlView = TicketCloseView

# ===========================
# COG MAIN CLASS
# ===========================
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.payment_cooldowns = {}

    async def cog_load(self):
        if not self.check_inactive_tickets_loop.is_running():
            self.check_inactive_tickets_loop.start()
        if not self.check_escalation_tickets_loop.is_running():
            self.check_escalation_tickets_loop.start()

    async def cog_unload(self):
        if self.check_inactive_tickets_loop.is_running():
            self.check_inactive_tickets_loop.cancel()
        if self.check_escalation_tickets_loop.is_running():
            self.check_escalation_tickets_loop.cancel()

    # --- SLA ESCALATION TASK ---
    @tasks.loop(minutes=5)
    async def check_escalation_tickets_loop(self):
        cfg = load_config()
        escalation_threshold = cfg.get("escalation_threshold_seconds", 1800)
        
        for user_id, ticket_data in list(open_tickets.items()):
            if ticket_data.get("claimed_by") or ticket_data.get("escalated"):
                continue
                
            channel_id = ticket_data.get("channel_id")
            if not channel_id:
                continue
                
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                continue
                
            if channel.name.startswith("closed-"):
                continue
                
            created_at_str = ticket_data.get("created_at")
            if not created_at_str:
                continue
                
            try:
                created_at_dt = datetime.fromisoformat(created_at_str)
                elapsed = (datetime.now() - created_at_dt).total_seconds()
                
                if elapsed >= escalation_threshold:
                    ticket_type = ticket_data.get("type", "support")
                    role_id_key = f"{ticket_type}_role_id"
                    role_id = cfg.get(role_id_key)
                    
                    escalation_ping = f"<@&{role_id}> " if role_id else ""
                    
                    escalate_embed = discord.Embed(
                        title="🚨 **SLA Escalation Alert** 🚨",
                        description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"⏳ **This ticket has been unclaimed for over 30 minutes!**\n\n"
                                    f"• **Ticket Creator:** <@{user_id}>\n"
                                    f"• Please claim and assist the user as soon as possible.\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                        color=discord.Color.red()
                    )
                    escalate_embed.set_footer(text="Joyst Corporation | SLA Escalation System")
                    escalate_embed.timestamp = datetime.now()
                    
                    await channel.send(content=escalation_ping, embed=escalate_embed)
                    open_tickets[user_id]["escalated"] = True
                    tickets_data["active"] = open_tickets
                    save_tickets_data(tickets_data)
            except Exception as e:
                logger.error(f"Error escalating ticket for {channel.name}: {e}")

    # --- INACTIVITY TASK ---
    @tasks.loop(hours=1)
    async def check_inactive_tickets_loop(self):
        for user_id, ticket_data in list(open_tickets.items()):
            channel_id = ticket_data.get("channel_id")
            if not channel_id:
                continue
            
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                continue
                
            if channel.name.startswith("closed-"):
                continue

            try:
                last_message = None
                async for msg in channel.history(limit=1):
                    last_message = msg
                    break
                
                if not last_message:
                    continue

                tz = last_message.created_at.tzinfo
                now_with_tz = datetime.now(tz)
                inactivity_seconds = (now_with_tz - last_message.created_at).total_seconds()

                if inactivity_seconds >= 172800:  # 48h
                    try:
                        await perform_close_ticket(None, channel, self.bot)
                    except Exception as e:
                        logger.error(f"Auto-close error for {channel.name}: {e}")
                elif inactivity_seconds >= 86400 and not ticket_data.get("inactivity_warned"): # 24h
                    warn_embed = discord.Embed(
                        title="⚠️ **Inactivity Warning** ⚠️",
                        description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"**⏰ This ticket has been inactive for 24 hours.**\n\n"
                                    f"• Please send a message here to keep this ticket open.\n"
                                    f"• **If there is no activity in the next 24 hours, it will be automatically closed.**\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                        color=discord.Color.red()
                    )
                    warn_embed.set_footer(text="Joyst Corporation | Inactivity Checker")
                    warn_embed.timestamp = datetime.now()
                    
                    await channel.send(embed=warn_embed)
                    open_tickets[user_id]["inactivity_warned"] = True
                    tickets_data["active"] = open_tickets
                    save_tickets_data(tickets_data)
                    
            except Exception as e:
                logger.error(f"Error checking inactivity for {channel.name}: {e}")

    # --- AUTO PAYMENT KEYWORD LISTENER ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return

        ticket_data = get_ticket_data_by_channel_id(message.channel.id)
        if ticket_data and not message.channel.name.startswith("closed-"):
            if ticket_data.get("inactivity_warned"):
                ticket_owner_id = ticket_data.get("user_id")
                open_tickets[ticket_owner_id]["inactivity_warned"] = False
                tickets_data["active"] = open_tickets
                save_tickets_data(tickets_data)

            content_lower = message.content.lower()
            
            binance_keywords = ["binance", "bpay"]
            ltc_keywords = ["ltc", "litecoin", "crypto"]
            upi_keywords = ["qr", "scanner", "upi", "pay", "payment", "gpay", "phonepe", "paytm"]
            
            import time
            current_time = time.time()
            cfg = load_config()

            # BINANCE PAY
            if any(k in content_lower for k in binance_keywords):
                last_sent = self.payment_cooldowns.get(f"{message.channel.id}_binance", 0)
                if current_time - last_sent >= 15:
                    self.payment_cooldowns[f"{message.channel.id}_binance"] = current_time
                    binance_id = cfg.get("binance_pay_id", "1015322654")
                    
                    embed = discord.Embed(
                        title="🟡 Binance Pay Details | Joyst Corporation",
                        description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"Here are the Binance Pay details for your payment:\n\n"
                                    f"**🟡 Binance Pay ID:** `{binance_id}`\n\n"
                                    f"• Copy the **Binance Pay ID** above to make payment in Binance App.\n"
                                    f"• Please send a screenshot of the payment confirmation receipt here after paying.\n"
                                    f"• Our staff will verify and process your order immediately.\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                        color=discord.Color.from_rgb(240, 185, 11)
                    )
                    embed.set_footer(text="Joyst Corporation | Binance Pay")
                    embed.timestamp = datetime.now()
                    await message.channel.send(embed=embed)

            # LITECOIN (LTC)
            elif any(k in content_lower for k in ltc_keywords):
                last_sent = self.payment_cooldowns.get(f"{message.channel.id}_ltc", 0)
                if current_time - last_sent >= 15:
                    self.payment_cooldowns[f"{message.channel.id}_ltc"] = current_time
                    ltc_addr = cfg.get("ltc_address", "LX66S1hh84gpRDJSbQsn5K6bbJtML8bjK7")
                    
                    embed = discord.Embed(
                        title="🪙 Litecoin (LTC) Payment | Joyst Corporation",
                        description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                    f"Here are the Crypto (LTC) payment details:\n\n"
                                    f"**🪙 LTC Address:** `{ltc_addr}`\n\n"
                                    f"• Copy the **LTC Address** above to send Litecoin from your wallet.\n"
                                    f"• Please send the **TXID / Payment Screenshot** here after sending.\n"
                                    f"• Our staff will verify and process your order immediately.\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                        color=discord.Color.from_rgb(52, 93, 157)
                    )
                    embed.set_footer(text="Joyst Corporation | Crypto LTC Payment")
                    embed.timestamp = datetime.now()
                    await message.channel.send(embed=embed)

            # UPI / QR
            elif any(k in content_lower for k in upi_keywords):
                last_sent = self.payment_cooldowns.get(f"{message.channel.id}_upi", 0)
                if current_time - last_sent >= 15:
                    self.payment_cooldowns[f"{message.channel.id}_upi"] = current_time
                    upi_id = cfg.get("upi_id", "shivang-maurya@fam")
                    qr_path = cfg.get("qr_image_path", "qr.png")
                    
                    enable_stripe = cfg.get("enable_stripe", False)
                    stripe_url = cfg.get("stripe_payment_link", "https://buy.stripe.com/mock_link") if enable_stripe else None
                    
                    desc = f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"Here are the payment details for your transaction:\n\n" \
                           f"**📲 UPI ID:** `{upi_id}`\n\n"
                           
                    if enable_stripe:
                        desc += f"• **Pay via UPI**: Scan the QR code or use the UPI ID above.\n" \
                                f"• **Pay via Card**: Click the button below to pay using Stripe.\n\n"
                    else:
                        desc += f"• Please scan the QR code or use the UPI ID above to pay.\n\n"
                        
                    desc += f"• Please send a screenshot of the payment receipt here after paying.\n" \
                            f"• Our staff will verify and process your request immediately.\n" \
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

                    embed = discord.Embed(
                        title="💳 UPI Payment Details | Joyst Corporation",
                        description=desc,
                        color=discord.Color.from_rgb(0, 180, 255)
                    )
                    embed.set_footer(text="Joyst Corporation | UPI Payment System")
                    embed.timestamp = datetime.now()
                    
                    file = None
                    if qr_path and os.path.exists(qr_path):
                        fn = os.path.basename(qr_path)
                        file = discord.File(qr_path, filename=fn)
                        embed.set_image(url=f"attachment://{fn}")
                    
                    view = None
                    if enable_stripe and stripe_url:
                        class StripePaymentView(discord.ui.View):
                            def __init__(self, url: str):
                                super().__init__()
                                self.add_item(discord.ui.Button(label="💳 Pay with Stripe (Card)", style=discord.ButtonStyle.link, url=url))
                        view = StripePaymentView(stripe_url)
                    
                    if file:
                        if view:
                            await message.channel.send(embed=embed, file=file, view=view)
                        else:
                            await message.channel.send(embed=embed, file=file)
                    else:
                        if view:
                            await message.channel.send(embed=embed, view=view)
                        else:
                            await message.channel.send(embed=embed)

    # --- COMMANDS ---

    async def _send_ticket_panel(self, interaction_or_ctx):
        is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
        guild = interaction_or_ctx.guild
        cfg = load_config()
        banner_url = cfg.get("banner_url") or (guild.banner.url if guild and guild.banner else None)

        embed = discord.Embed(
            title="🎫 **Joyst Corporation Support**",
            description="# <a:13969niebieskipiorun:1441085314272722959> Create Ticket\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "** Welcome To Joyst Corporation **\n\n"
                        "・ Use Drop Down Menu And Select What You Want\n"
                        "・ Our Staff Will Reach Out To You After Creating A Ticket\n"
                        "・ Strictly Don't Create Tickets For Fun\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=discord.Color.teal()
        )
        embed.set_footer(text="© Joyst Corporation , All Rights Reserved.")
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if banner_url:
            embed.set_image(url=banner_url)

        if is_interaction:
            await interaction_or_ctx.response.send_message(embed=embed, view=TicketView(bot_instance=self.bot), ephemeral=False)
            panel_msg = await interaction_or_ctx.original_response()
        else:
            panel_msg = await interaction_or_ctx.send(embed=embed, view=TicketView(bot_instance=self.bot))

        cfg['panel_message_id'] = panel_msg.id
        cfg['panel_channel_id'] = panel_msg.channel.id
        save_config(cfg)

    @commands.command(name="ticketpanel", aliases=["tp", "ticket", "tickets"])
    async def ticket_panel_prefix(self, ctx: commands.Context):
        """Send the official Joyst Corporation Ticket Creation Panel"""
        await self._send_ticket_panel(ctx)

    @app_commands.command(name="ticketpanel", description="Displays the ticket creation panel for users.")
    async def ticket_panel_slash(self, interaction: discord.Interaction):
        await self._send_ticket_panel(interaction)

    @app_commands.command(name="ticket", description="Displays the ticket creation panel for users.")
    async def ticket_slash(self, interaction: discord.Interaction):
        await self._send_ticket_panel(interaction)

    @app_commands.command(name="tickets", description="Displays the ticket creation panel for users.")
    async def tickets_slash(self, interaction: discord.Interaction):
        await self._send_ticket_panel(interaction)

    @commands.command(name="remind")
    async def remind_prefix(self, ctx: commands.Context):
        """Send a reminder to ticket creator: ,remind"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return

        ticket_data = get_ticket_data_by_channel_id(ctx.channel.id)
        if not ticket_data:
            await ctx.send("❌ This channel is not recognized as an active ticket.", delete_after=10)
            return

        if ctx.channel.name.startswith("closed-"):
            await ctx.send("❌ This ticket is already closed.", delete_after=10)
            return

        ticket_creator_id = int(ticket_data.get("user_id"))
        ticket_type = ticket_data.get("type")

        try:
            await send_ticket_reminder_dm(
                bot_instance=self.bot,
                user_id=ticket_creator_id,
                guild=ctx.guild,
                ticket_channel=ctx.channel,
                ticket_type=ticket_type
            )
            
            ticket_creator = ctx.guild.get_member(ticket_creator_id)
            if ticket_creator:
                await send_in_channel_reminder(ctx.channel, ticket_creator.mention)
            
            await ctx.send("✅ Reminder sent successfully (DM + Channel).", delete_after=10)

        except Exception as e:
            await ctx.send(f"❌ Reminder failed: `{e}`", delete_after=15)

    @app_commands.command(name="remind", description="Send a reminder to the ticket creator (DM + Channel)")
    async def remind_slash(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in ticket channels.", ephemeral=True)
            return

        ticket_data = get_ticket_data_by_channel_id(interaction.channel.id)
        if not ticket_data:
            await interaction.response.send_message("❌ This channel is not recognized as an active ticket.", ephemeral=True)
            return

        if interaction.channel.name.startswith("closed-"):
            await interaction.response.send_message("❌ This ticket is already closed.", ephemeral=True)
            return

        ticket_creator_id = int(ticket_data.get("user_id"))
        ticket_type = ticket_data.get("type")
        
        await interaction.response.defer(ephemeral=True)

        try:
            await send_ticket_reminder_dm(
                bot_instance=self.bot,
                user_id=ticket_creator_id,
                guild=interaction.guild,
                ticket_channel=interaction.channel,
                ticket_type=ticket_type
            )
            
            ticket_creator = interaction.guild.get_member(ticket_creator_id)
            if ticket_creator:
                await send_in_channel_reminder(interaction.channel, ticket_creator.mention)
            
            await interaction.followup.send("✅ Reminder sent successfully (DM + Channel).", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Reminder failed: `{e}`", ephemeral=True)

    @commands.command(name="add")
    async def add_user_prefix(self, ctx: commands.Context, member: discord.Member):
        """Add a user to this ticket channel: ,add @member"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return

        ticket_data = get_ticket_data_by_channel_id(ctx.channel.id)
        if not ticket_data:
            await ctx.send("❌ This channel is not recognized as an active ticket.", delete_after=10)
            return

        try:
            overwrite = ctx.channel.overwrites_for(member)
            overwrite.read_messages = True
            overwrite.send_messages = True
            overwrite.attach_files = True
            overwrite.embed_links = True
            await ctx.channel.set_permissions(member, overwrite=overwrite, reason=f"User added by {ctx.author.name}")

            embed = discord.Embed(
                title="👤 User Added",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**Added User:** {member.mention} (`{member.id}`)\n"
                            f"**Added By:** {ctx.author.mention}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.green()
            )
            embed.set_footer(text="Joyst Corporation | Ticket System")
            embed.timestamp = datetime.now()

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Failed to add user: `{e}`", delete_after=15)

    @app_commands.command(name="add", description="Add a user to this ticket channel")
    @app_commands.describe(member="The user to add to the ticket")
    async def add_user_slash(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ This command can only be used in a text channel.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            overwrite = interaction.channel.overwrites_for(member)
            overwrite.read_messages = True
            overwrite.send_messages = True
            overwrite.attach_files = True
            overwrite.embed_links = True
            await interaction.channel.set_permissions(member, overwrite=overwrite, reason=f"User added by {interaction.user.name}")

            embed = discord.Embed(
                title="👤 User Added",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**Added User:** {member.mention} (`{member.id}`)\n"
                            f"**Added By:** {interaction.user.mention}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.green()
            )
            embed.set_footer(text="Joyst Corporation | Ticket System")
            embed.timestamp = datetime.now()

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to add user: `{e}`", ephemeral=True)

    @commands.command(name="remove")
    async def remove_user_prefix(self, ctx: commands.Context, member: discord.Member):
        """Remove a user from this ticket channel: ,remove @member"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return

        try:
            await ctx.channel.set_permissions(member, overwrite=None, reason=f"User removed by {ctx.author.name}")

            embed = discord.Embed(
                title="👤 User Removed",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**Removed User:** {member.mention} (`{member.id}`)\n"
                            f"**Removed By:** {ctx.author.mention}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.red()
            )
            embed.set_footer(text="Joyst Corporation | Ticket System")
            embed.timestamp = datetime.now()

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Failed to remove user: `{e}`", delete_after=15)

    @app_commands.command(name="remove", description="Remove a user from this ticket channel")
    @app_commands.describe(member="The user to remove from the ticket")
    async def remove_user_slash(self, interaction: discord.Interaction, member: discord.Member):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ This command can only be used in a text channel.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await interaction.channel.set_permissions(member, overwrite=None, reason=f"User removed by {interaction.user.name}")

            embed = discord.Embed(
                title="👤 User Removed",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**Removed User:** {member.mention} (`{member.id}`)\n"
                            f"**Removed By:** {interaction.user.mention}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.red()
            )
            embed.set_footer(text="Joyst Corporation | Ticket System")
            embed.timestamp = datetime.now()

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to remove user: `{e}`", ephemeral=True)

    @commands.command(name="stats")
    async def stats_prefix(self, ctx: commands.Context, member: discord.Member = None):
        """View staff ticket claiming statistics or leaderboard: ,stats"""
        stats = tickets_data.get("staff_stats", {})

        if member:
            member_id = str(member.id)
            user_stats = stats.get(member_id, {"claimed": 0, "closed": 0, "username": member.name})
            
            embed = discord.Embed(
                title=f"📊 Staff Stats: {member.name}",
                description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**👤 Staff Member:** {member.mention}\n"
                            f"**🎟️ Tickets Claimed:** `{user_stats['claimed']}`\n"
                            f"**🔒 Tickets Closed:** `{user_stats['closed']}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Joyst Corporation | Staff Performance")
            embed.timestamp = datetime.now()
            await ctx.send(embed=embed)
        else:
            if not stats:
                await ctx.send("❌ No staff statistics available yet.")
                return

            sorted_staff = sorted(stats.items(), key=lambda item: item[1].get("claimed", 0), reverse=True)[:10]

            leaderboard_text = ""
            for index, (staff_id, data) in enumerate(sorted_staff, 1):
                emoji = "🥇" if index == 1 else ("🥈" if index == 2 else ("🥉" if index == 3 else "🏅"))
                leaderboard_text += f"{emoji} **#{index}** <@{staff_id}> | Claimed: `{data.get('claimed', 0)}` | Closed: `{data.get('closed', 0)}`\n"

            embed = discord.Embed(
                title="🏆 **Staff Claim Leaderboard** 🏆",
                description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Here are the top performing staff members:\n\n"
                            f"{leaderboard_text}"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.gold()
            )
            embed.set_footer(text="Joyst Corporation | Staff Analytics")
            embed.timestamp = datetime.now()
            await ctx.send(embed=embed)

    @app_commands.command(name="stats", description="View staff ticket claiming statistics or the leaderboard")
    @app_commands.describe(member="The staff member to view stats for (optional)")
    async def stats_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        stats = tickets_data.get("staff_stats", {})

        if member:
            member_id = str(member.id)
            user_stats = stats.get(member_id, {"claimed": 0, "closed": 0, "username": member.name})
            
            embed = discord.Embed(
                title=f"📊 Staff Stats: {member.name}",
                description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"**👤 Staff Member:** {member.mention}\n"
                            f"**🎟️ Tickets Claimed:** `{user_stats['claimed']}`\n"
                            f"**🔒 Tickets Closed:** `{user_stats['closed']}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Joyst Corporation | Staff Performance")
            embed.timestamp = datetime.now()
            await interaction.followup.send(embed=embed)
        else:
            if not stats:
                await interaction.followup.send("❌ No staff statistics available yet.")
                return

            sorted_staff = sorted(stats.items(), key=lambda item: item[1].get("claimed", 0), reverse=True)[:10]

            leaderboard_text = ""
            for index, (staff_id, data) in enumerate(sorted_staff, 1):
                emoji = "🥇" if index == 1 else ("🥈" if index == 2 else ("🥉" if index == 3 else "🏅"))
                leaderboard_text += f"{emoji} **#{index}** <@{staff_id}> | Claimed: `{data.get('claimed', 0)}` | Closed: `{data.get('closed', 0)}`\n"

            embed = discord.Embed(
                title="🏆 **Staff Claim Leaderboard** 🏆",
                description=f"### ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Here are the top performing staff members:\n\n"
                            f"{leaderboard_text}"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.gold()
            )
            embed.set_footer(text="Joyst Corporation | Staff Analytics")
            embed.timestamp = datetime.now()
            await interaction.followup.send(embed=embed)

    @commands.command(name="close")
    async def close_prefix(self, ctx: commands.Context):
        """Close current ticket: ,close"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        await perform_close_ticket(ctx, ctx.channel, self.bot)

    @app_commands.command(name="close", description="Closes current ticket (renames to closed-)")
    async def close_slash(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in a guild text channel.", ephemeral=True)
            return
        await perform_close_ticket(interaction, interaction.channel, self.bot)

    @commands.command(name="delete")
    async def delete_prefix(self, ctx: commands.Context):
        """Permanently delete current ticket channel: ,delete"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        await perform_delete_ticket(ctx, ctx.channel, self.bot)

    @app_commands.command(name="delete", description="PERMANENTLY DELETES the ticket channel")
    async def delete_slash(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in a guild text channel.", ephemeral=True)
            return
        await perform_delete_ticket(interaction, interaction.channel, self.bot)

    @commands.command(name="deleteall")
    async def deleteall_prefix(self, ctx: commands.Context):
        """Mass delete all open & closed tickets: ,deleteall"""
        if not is_strict_admin(ctx.author):
            await ctx.send("❌ Only Administrators can use this command.")
            return

        tickets_to_delete = []
        for user_id, ticket_data in list(open_tickets.items()):
            ch_id = ticket_data.get("channel_id")
            if ch_id:
                ch = ctx.guild.get_channel(ch_id)
                if ch and isinstance(ch, discord.TextChannel):
                    tickets_to_delete.append({"channel": ch, "user_id": user_id, "ticket_type": ticket_data.get("type", "unknown"), "is_closed": False})

        closed_tickets_data = tickets_data.get("closed", {})
        for ch_id_str, closed_data in list(closed_tickets_data.items()):
            ch = ctx.guild.get_channel(int(ch_id_str))
            if ch and isinstance(ch, discord.TextChannel):
                tickets_to_delete.append({"channel": ch, "user_id": closed_data.get("user_id", "unknown_owner"), "ticket_type": closed_data.get("type", "unknown"), "is_closed": True})

        total = len(tickets_to_delete)
        if total == 0:
            await ctx.send("❌ No tickets to delete.")
            return

        await ctx.send(f"⚠️ **Mass Deleting {total} tickets...**")
        for idx, t_info in enumerate(tickets_to_delete, 1):
            try:
                await perform_mass_delete_ticket(t_info["channel"], t_info["user_id"], t_info["ticket_type"], ctx.author.name, str(ctx.author.id), idx, total, t_info["is_closed"], self.bot)
            except Exception as e:
                logger.error(f"Error in mass delete: {e}")
            await asyncio.sleep(1.5)
        await ctx.send("✅ **Mass Ticket Deletion Completed!**")

    @commands.command(name="clearjson")
    async def clearjson_prefix(self, ctx: commands.Context):
        """Clear tickets_data.json database: ,clearjson"""
        if not is_strict_admin(ctx.author):
            return
        fresh_data = {"active": {}, "closed": {}, "staff_stats": {}}
        save_tickets_data(fresh_data)
        global tickets_data, open_tickets
        tickets_data = fresh_data
        open_tickets = fresh_data.get("active", {})
        await ctx.send("✅ Ticket data cleared.")

    @commands.command(name="backup")
    async def backup_prefix(self, ctx: commands.Context):
        """Send tickets_data.json backup file: ,backup"""
        current_data = load_tickets_data()
        file_content = io.BytesIO(json.dumps(current_data, indent=4).encode('utf-8'))
        backup_file = discord.File(file_content, filename="tickets_data_backup.json")
        await ctx.send("📦 **Ticket Data Backup:**", file=backup_file)

    @commands.command(name="checkdata")
    async def checkdata_prefix(self, ctx: commands.Context):
        """Check active and closed tickets summary: ,checkdata"""
        if not is_strict_admin(ctx.author):
            return
        active_count = len(open_tickets)
        closed_count = len(tickets_data.get("closed", {}))
        
        msg = f"📊 **Ticket Data Summary:**\n" \
              f"• Active tickets in JSON: `{active_count}`\n" \
              f"• Closed tickets in JSON: `{closed_count}`\n" \
              f"• Total: `{active_count + closed_count}`"
        await ctx.send(msg)

    @app_commands.command(name="checkdata", description="Check active and closed tickets summary")
    async def checkdata_slash(self, interaction: discord.Interaction):
        if not is_strict_admin(interaction.user):
            await interaction.response.send_message("❌ Only Administrators can use this command.", ephemeral=True)
            return
        active_count = len(open_tickets)
        closed_count = len(tickets_data.get("closed", {}))
        
        msg = f"📊 **Ticket Data Summary:**\n" \
              f"• Active tickets in JSON: `{active_count}`\n" \
              f"• Closed tickets in JSON: `{closed_count}`\n" \
              f"• Total: `{active_count + closed_count}`"
        await interaction.response.send_message(msg, ephemeral=True)

async def perform_close_ticket(interaction_or_ctx, channel: discord.TextChannel, bot_instance):
    is_interaction = isinstance(interaction_or_ctx, discord.Interaction)

    if channel.name.startswith("closed-"):
        msg = "This ticket is already closed."
        if interaction_or_ctx is not None:
            if is_interaction:
                await interaction_or_ctx.response.send_message(msg, ephemeral=True)
            else:
                await interaction_or_ctx.send(msg, delete_after=10)
        return

    ticket_data = get_ticket_data_by_channel_id(channel.id)
    if not ticket_data:
        msg = "This channel is not recognized as an active ticket."
        if interaction_or_ctx is not None:
            if is_interaction:
                await interaction_or_ctx.response.send_message(msg, ephemeral=True)
            else:
                await interaction_or_ctx.send(msg, delete_after=10)
        return

    if interaction_or_ctx is not None and is_interaction and not interaction_or_ctx.response.is_done():
        await interaction_or_ctx.response.defer(ephemeral=False)

    ticket_owner_id = ticket_data["user_id"]
    ticket_type = ticket_data["type"]

    ticket_owner_member = channel.guild.get_member(int(ticket_owner_id))
    if ticket_owner_member:
        try:
            current_overwrites = channel.overwrites_for(ticket_owner_member)
            current_overwrites.view_channel = False
            current_overwrites.read_messages = False
            current_overwrites.send_messages = False
            await channel.set_permissions(ticket_owner_member, overwrite=current_overwrites, reason="Ticket closing by command")
        except Exception as e:
            logger.error(f"Error removing perms in {channel.name}: {e}")

    await send_transcript(channel, ticket_owner_id, ticket_type, bot_instance, is_mass_operation=False, operation_type="closed")

    closing_embed = discord.Embed(
        title="🔒 Ticket Closing", 
        description="⏰ This ticket will close in **5** seconds...",
        color=discord.Color.orange()
    )
    msg_closing = await channel.send(embed=closing_embed)

    for i in range(5, 0, -1):
        closing_embed.description = f"⏰ This ticket will close in **{i}** seconds..."
        await msg_closing.edit(embed=closing_embed)
        await asyncio.sleep(1)

    if ticket_owner_id in open_tickets:
        ticket_info = open_tickets[ticket_owner_id]

        if interaction_or_ctx is None:
            closed_by_id = "0"
            closed_by_name = "System (Inactivity)"
        else:
            closed_by_id = str(interaction_or_ctx.user.id if is_interaction else interaction_or_ctx.author.id)
            closed_by_name = interaction_or_ctx.user.name if is_interaction else interaction_or_ctx.author.name

            stats = tickets_data.get("staff_stats", {})
            if closed_by_id not in stats:
                stats[closed_by_id] = {"claimed": 0, "closed": 0, "username": closed_by_name}
            stats[closed_by_id]["closed"] += 1
            stats[closed_by_id]["username"] = closed_by_name
            tickets_data["staff_stats"] = stats

        tickets_data["closed"][str(channel.id)] = {
            "user_id": ticket_owner_id,
            "channel_id": channel.id,
            "type": ticket_info.get("type", "unknown"),
            "owner_name": ticket_info.get("owner_name", "Unknown"),
            "closed_at": datetime.now().isoformat(),
            "closed_by": closed_by_id,
            "closed_by_name": closed_by_name
        }

        del open_tickets[ticket_owner_id]
        tickets_data["active"] = open_tickets
        save_tickets_data(tickets_data)

    base_name = channel.name
    new_channel_name = f"closed-{base_name[:80]}"
    try:
        await channel.edit(name=new_channel_name, reason="Ticket closed")
    except Exception:
        pass

    closing_embed.title = "✅ Ticket Closed"
    closing_embed.description = "📦 This ticket has been archived for staff review."
    closing_embed.color = discord.Color.dark_red()
    await msg_closing.edit(embed=closing_embed)

async def perform_delete_ticket(interaction_or_ctx, channel: discord.TextChannel, bot_instance):
    is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
    
    ticket_data = get_ticket_data_by_channel_id(channel.id)
    if not ticket_data:
        ticket_owner_id = "unknown_owner"
        ticket_type = "unknown_type"
    else:
        ticket_owner_id = ticket_data["user_id"]
        ticket_type = ticket_data["type"]
    
    if is_interaction and not interaction_or_ctx.response.is_done():
        await interaction_or_ctx.response.defer(ephemeral=False)
    
    await send_transcript(channel, ticket_owner_id, ticket_type, bot_instance, is_mass_operation=False, operation_type="deleted")
    
    if ticket_owner_id in open_tickets:
        del open_tickets[ticket_owner_id]
        tickets_data["active"] = open_tickets
        save_tickets_data(tickets_data)
    else:
        closed_tickets = tickets_data.get("closed", {})
        if str(channel.id) in closed_tickets:
            del closed_tickets[str(channel.id)]
            tickets_data["closed"] = closed_tickets
            save_tickets_data(tickets_data)
    
    closing_embed = discord.Embed(
        title="🗑️ **Ticket Deletion**",
        description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"### ⚠️ This ticket is being **permanently deleted**\n\n"
                   f"⏰ This channel will be deleted in **5** seconds...\n"
                   f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=discord.Color.red()
    )
    await channel.send(embed=closing_embed)
    await asyncio.sleep(5)
    
    try:
        await channel.delete(reason=f"Ticket deleted by {(interaction_or_ctx.user.name if is_interaction else interaction_or_ctx.author.name)}")
    except Exception as e:
        logger.error(f"Delete failed: {e}")

async def perform_mass_delete_ticket(channel: discord.TextChannel, user_id: str, ticket_type: str, closer_name: str, closer_id: str, index: int, total: int, is_closed: bool, bot_instance):
    await send_transcript(channel, user_id, ticket_type, bot_instance, is_mass_operation=True, operation_type="deleted")
    
    if not is_closed and user_id in open_tickets:
        del open_tickets[user_id]
        tickets_data["active"] = open_tickets
    
    if is_closed:
        closed_tickets = tickets_data.get("closed", {})
        if str(channel.id) in closed_tickets:
            del closed_tickets[str(channel.id)]
            tickets_data["closed"] = closed_tickets
    
    save_tickets_data(tickets_data)
    
    try:
        await channel.delete(reason=f"Mass ticket deletion by {closer_name}")
    except Exception as e:
        logger.error(f"Failed to delete channel {channel.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))

import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import database as db
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE
from emojis import get_emoji

logger = logging.getLogger("AEGIS.UserInfo")

class UserInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _do_userinfo(self, ctx_or_interaction, target_member: discord.Member = None):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author
        member = target_member or author

        # Calculate Account Age & Alt Risk
        created_ts = int(member.created_at.timestamp())
        joined_ts = int(member.joined_at.timestamp()) if member.joined_at else 0
        now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        account_age_days = (now_ts - created_ts) // 86400

        if account_age_days < 7:
            risk_badge = "🔴 **HIGH RISK (Potential Alt Account)**"
            color = COLOR_DANGER
        elif account_age_days < 30:
            risk_badge = "🟡 **MEDIUM RISK (Recent Account)**"
            color = COLOR_WARNING
        else:
            risk_badge = "🟢 **LOW RISK (Verified Established Account)**"
            color = COLOR_SUCCESS

        # Roles summary
        user_roles = [r.mention for r in member.roles if r != guild.default_role]
        roles_str = ", ".join(user_roles[:5]) if user_roles else "`No Roles`"
        if len(user_roles) > 5:
            roles_str += f" *(+{len(user_roles) - 5} more)*"

        # Key Permissions
        key_perms = []
        perms = member.guild_permissions
        if perms.administrator:
            key_perms.append("Administrator 👑")
        if perms.manage_guild:
            key_perms.append("Manage Server ⚙️")
        if perms.ban_members:
            key_perms.append("Ban Members 🔨")
        if perms.kick_members:
            key_perms.append("Kick Members 👢")
        if perms.manage_channels:
            key_perms.append("Manage Channels 📁")
        if perms.manage_roles:
            key_perms.append("Manage Roles 🏷️")

        perms_str = ", ".join(key_perms) if key_perms else "`Standard Member`"

        # Flags & Badges
        flags = []
        if member.bot:
            flags.append("🤖 Bot")
        if member.id == guild.owner_id:
            flags.append("👑 Server Owner")
        if hasattr(member.public_flags, "hypesquad") and member.public_flags.hypesquad:
            flags.append("🏠 HypeSquad")

        flags_str = " • ".join(flags) if flags else "`User Account`"

        desc = (
            f"👤 **USER INFORMATION • {member.name}**\n\n"
            f"• **Mention:** {member.mention} (`{member.id}`)\n"
            f"• **Account Created:** <t:{created_ts}:f> (<t:{created_ts}:R>)\n"
            f"• **Joined Server:** <t:{joined_ts}:f> (<t:{joined_ts}:R>)\n"
            f"• **Alt Risk Score:** {risk_badge}\n"
            f"• **Key Permissions:** {perms_str}\n"
            f"• **Badges:** {flags_str}\n"
            f"• **Top Roles:** {roles_str}"
        )

        avatar_url = member.display_avatar.url if member.display_avatar else None
        embed = joyst_embed(description=desc, color=color, thumbnail=avatar_url, guild=guild)

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    # --- Commands ---

    @commands.command(name="userinfo", aliases=["uinfo", "whois", "user"])
    @commands.has_permissions(administrator=True)
    async def prefix_userinfo(self, ctx, member: discord.Member = None):
        """[ADMIN ONLY] View detailed account info, age, and alt risk score"""
        if not (ctx.author.id == ctx.guild.owner_id or (hasattr(ctx.author, "guild_permissions") and ctx.author.guild_permissions.administrator)):
            await ctx.send("❌ Only Server Admins or Server Owner can use userinfo.")
            return
        await self._do_userinfo(ctx, member)

    # --- Slash Commands ---

    @app_commands.command(name="userinfo", description="[ADMIN ONLY] View detailed member account info & alt risk assessment")
    @app_commands.describe(member="Target member to inspect (optional)")
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        user = interaction.user
        if not (user.id == interaction.guild.owner_id or (hasattr(user, "guild_permissions") and user.guild_permissions.administrator)):
            await interaction.response.send_message("❌ Only Server Admins or Server Owner can use userinfo.", ephemeral=True)
            return
        await self._do_userinfo(interaction, member)

async def setup(bot):
    await bot.add_cog(UserInfo(bot))

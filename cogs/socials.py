import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import database as db
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji

logger = logging.getLogger("AEGIS.Socials")

class Socials(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def broadcast_social_stream(self, guild: discord.Guild, channel: discord.TextChannel, platform: str, title: str, url: str, thumbnail_url: str = None, ping_role_id: str = None):
        """Dispatches live YouTube or Twitch Stream Broadcaster Embed to Discord"""
        try:
            platform_icons = {
                "youtube": "🔴 YOUTUBE LIVE BROADCAST",
                "twitch": "🟣 TWITCH STREAM LIVE",
                "video": "🎬 NEW YOUTUBE VIDEO UPLOAD"
            }
            platform_colors = {
                "youtube": discord.Color.from_rgb(239, 68, 68), # Red
                "twitch": discord.Color.from_rgb(168, 85, 247), # Purple
                "video": discord.Color.from_rgb(239, 68, 68)
            }

            p_key = platform.lower()
            header = platform_icons.get(p_key, "📢 LIVE BROADCAST")
            color = platform_colors.get(p_key, discord.Color.from_rgb(99, 102, 241))

            embed = discord.Embed(
                title=f"{header} • {title}",
                description=f"Watch live now on **{platform.title()}**!\n\n🔗 **Stream Link:** [Click Here to Watch]({url})\n",
                color=color,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_author(name=f"{config.SERVER_NAME} Official Stream", icon_url=guild.icon.url if guild.icon else None)
            if thumbnail_url and thumbnail_url.startswith("http"):
                embed.set_image(url=thumbnail_url)
            embed.set_footer(text=f"{config.SERVER_NAME} Social Sync • Don't Miss Out!")

            content = None
            if ping_role_id:
                if ping_role_id.lower() == "everyone":
                    content = "@everyone 🚨 **STREAM IS LIVE!**"
                else:
                    content = f"<@&{ping_role_id}> 🚨 **STREAM IS LIVE!**"

            await channel.send(content=content, embed=embed)
            db.add_audit_log(str(guild.id), "SOCIAL_BROADCAST", f"Dispatched {platform} broadcast '{title}' to #{channel.name}.", severity="INFO")
            return True, f"Broadcast sent to #{channel.name}!"
        except Exception as e:
            logger.error(f"Broadcaster Error: {e}", exc_info=True)
            return False, str(e)

    # --- Slash Commands ---

    broadcast_group = app_commands.Group(name="broadcast", description="Live Stream & YouTube Broadcaster Commands")

    @broadcast_group.command(name="stream", description="Broadcast a Live Stream Announcement")
    @app_commands.describe(platform="youtube or twitch", title="Stream Title", url="Stream URL", channel="Target Channel", ping_role="Role ID or everyone")
    async def slash_broadcast_stream(self, interaction: discord.Interaction, platform: str, title: str, url: str, channel: discord.TextChannel = None, ping_role: str = None):
        target_ch = channel or interaction.channel
        await interaction.response.defer()

        success, msg = await self.broadcast_social_stream(interaction.guild, target_ch, platform, title, url, ping_role_id=ping_role)
        if success:
            await interaction.followup.send(f"✅ {msg}")
        else:
            await interaction.followup.send(f"❌ Broadcast Failed: `{msg}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Socials(bot))

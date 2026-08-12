import discord
from discord.ext import commands
import time
import logging
from collections import defaultdict
import database as db

logger = logging.getLogger("AEGIS.AntiRaid")

class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Persistent view

    @discord.ui.button(label="🛡️ Verify Access", style=discord.ButtonStyle.success, custom_id="aegis_verify_button")
    async def verify_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return

        settings = db.get_guild_settings(str(guild.id))
        verified_role_id = settings.get("verified_role_id")
        unverified_role_id = settings.get("unverified_role_id")

        if not verified_role_id:
            await interaction.response.send_message("❌ Verification system is not fully configured by administrators.", ephemeral=True)
            return

        verified_role = guild.get_role(int(verified_role_id))
        if not verified_role:
            await interaction.response.send_message("❌ Verified role could not be found.", ephemeral=True)
            return

        member = interaction.user
        if isinstance(member, discord.Member):
            try:
                await member.add_roles(verified_role, reason="[AEGIS Verification] Verification button clicked.")
                if unverified_role_id:
                    unverified_role = guild.get_role(int(unverified_role_id))
                    if unverified_role:
                        await member.remove_roles(unverified_role, reason="[AEGIS Verification] Removed unverified role.")
                
                await interaction.response.send_message(f"✅ **Verification Successful!** You have been granted the {verified_role.mention} role. Welcome!", ephemeral=True)
                
                db.add_audit_log(
                    guild_id=str(guild.id),
                    action_type="VERIFICATION",
                    details=f"User {member} ({member.id}) passed verification.",
                    culprit_id=str(member.id),
                    culprit_name=str(member),
                    severity="LOW"
                )
            except discord.Forbidden:
                await interaction.response.send_message("❌ Bot lacks permission to assign roles.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error assigning verification role: {e}")
                await interaction.response.send_message("❌ An error occurred during verification.", ephemeral=True)

class AntiRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Join tracker: dict[guild_id] = list of join timestamps
        self.join_trackers = defaultdict(list)
        self.raid_mode_active = defaultdict(bool)

    def cog_load(self):
        # Register persistent verification view
        self.bot.add_view(VerificationView())

    def _is_raid_velocity(self, guild_id: str, limit: int = 10, window: int = 10) -> bool:
        now = time.time()
        joins = self.join_trackers[guild_id]
        joins = [t for t in joins if now - t <= window]
        joins.append(now)
        self.join_trackers[guild_id] = joins
        return len(joins) > limit

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = member.guild
        guild_id_str = str(guild.id)
        settings = db.get_guild_settings(guild_id_str)
        
        if not settings.get("anti_raid"):
            return

        # Check Join Velocity (>10 joins in 10 seconds)
        if self._is_raid_velocity(guild_id_str, limit=10, window=10):
            if not self.raid_mode_active[guild_id_str]:
                self.raid_mode_active[guild_id_str] = True
                logger.warning(f"Raid mode automatically ACTIVATED for guild {guild.name} ({guild.id})")
                
                db.add_audit_log(
                    guild_id=guild_id_str,
                    action_type="ANTI_RAID_ACTIVATED",
                    details=f"High join velocity detected (>10 joins in 10s). Automated Raid Shield Engaged.",
                    severity="HIGH"
                )

                # Send security alert
                log_channel_id = settings.get("log_channel_id")
                if log_channel_id:
                    channel = guild.get_channel(int(log_channel_id))
                    if channel:
                        embed = discord.Embed(
                            title="🛡️ ANTI-RAID MODE ENGAGED",
                            description="⚡ High join velocity detected! New member joins are being monitored under strict security.",
                            color=discord.Color.gold(),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.set_footer(text="AEGIS Anti-Raid Shield")
                        try:
                            await channel.send(embed=embed)
                        except Exception:
                            pass

        # If verification is enabled, assign unverified role
        if settings.get("verification_enabled"):
            unverified_role_id = settings.get("unverified_role_id")
            if unverified_role_id:
                unverified_role = guild.get_role(int(unverified_role_id))
                if unverified_role:
                    try:
                        await member.add_roles(unverified_role, reason="[AEGIS] Assigned unverified role on join.")
                    except Exception as e:
                        logger.error(f"Failed to assign unverified role to {member.id}: {e}")

        # All human member joins are 100% allowed with ZERO kicks or bans.
        pass

async def setup(bot):
    await bot.add_cog(AntiRaid(bot))

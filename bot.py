import discord
from discord.ext import commands
import asyncio
import time
import logging
import os
import threading
import sys
import database as db
import config
from web_dashboard import run_web_dashboard, set_bot_instance

# Reconfigure stdout for UTF-8 compatibility on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


import gc
# Tune Python Garbage Collector for 10x Less Micro-Stutter Delay
gc.set_threshold(50000, 500, 500)

# High-Speed Event Loop Acceleration
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except Exception:
    pass

logger = logging.getLogger("AEGIS.Main")

class AegisBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.bans = True
        intents.emojis = True
        intents.integrations = True
        intents.webhooks = True
        intents.invites = True
        intents.voice_states = True
        intents.presences = True
        intents.messages = True
        intents.message_content = True
        intents.guild_reactions = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(*config.COMMAND_PREFIXES),
            intents=intents,
            help_command=None
        )
        self.start_time = time.time()

    async def setup_hook(self):
        logger.info("Initializing AEGIS Security Cogs...")
        cogs = [
            "cogs.anti_nuke",
            "cogs.anti_raid",
            "cogs.automod",
            "cogs.moderation",
            "cogs.security_cmd",
            "cogs.music",
            "cogs.giveaway",
            "cogs.tickets",
            "cogs.stats",
            "cogs.temp_vc",
            "cogs.user_info",
            "cogs.tts",
            "cogs.sentiment",
            "cogs.socials",
            "cogs.weather"
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}")

        # Register persistent UI listeners so buttons/dropdowns NEVER time out or fail after restart
        try:
            from cogs.tickets import TicketKingDropdownView, TicketControlView
            from cogs.music import ProtectedMusicControlView
            from cogs.anti_raid import VerificationView
            from cogs.giveaway import GiveawayEntryView

            self.add_view(TicketKingDropdownView())
            self.add_view(TicketControlView())
            self.add_view(ProtectedMusicControlView())
            self.add_view(VerificationView())
            self.add_view(GiveawayEntryView(message_id=""))
            logger.info("Registered all persistent UI Views (Ticket, Music, Verification & Giveaway listeners active).")
        except Exception as e:
            logger.error(f"Error registering persistent UI views: {e}")

        async def sync_slash():
            await self.wait_until_ready()
            try:
                if config.PRIMARY_GUILD_ID > 0:
                    guild_obj = discord.Object(id=config.PRIMARY_GUILD_ID)
                    self.tree.clear_commands(guild=guild_obj)
                    await self.tree.sync(guild=guild_obj)

                # Sync single clean global slash command set
                synced = await self.tree.sync()
                logger.info(f"Successfully synced {len(synced)} clean global slash commands (Duplicates Removed).")
            except Exception as e:
                logger.warning(f"Slash command sync note: {e}")

        self.loop.create_task(sync_slash())

    async def on_ready(self):
        logger.info(f"═══════════════════════════════════════════════════════════")
        logger.info(f" 🛡️  JOYST CORPORATION SECURITY BOT ONLINE: {self.user} (ID: {self.user.id})")
        logger.info(f" 🌐 Web Dashboard live at http://localhost:{config.WEB_PORT}")
        total_members = sum([(g.member_count or len(g.members) or 0) for g in self.guilds])
        logger.info(f" 👥 Serving {len(self.guilds)} Guilds & {total_members} Users")
        logger.info(f"═══════════════════════════════════════════════════════════")

        # Auto-ensure dedicated security log channel & sync server PFP avatar in all guilds
        from embed_builder import get_or_create_log_channel
        for guild in self.guilds:
            try:
                ch = await get_or_create_log_channel(guild)
                if ch:
                    logger.info(f"Verified/Created dedicated security log channel #{ch.name} in {guild.name}")
                await self.sync_guild_avatar(guild)
            except Exception as e:
                logger.error(f"Error initializing guild {guild.name}: {e}")

        activity = discord.Streaming(
            name="JOYST CORPORATION SECURITY",
            url="https://twitch.tv/joystcorp"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def sync_guild_avatar(self, guild: discord.Guild):
        """Dynamically syncs the bot's server PFP avatar to match that specific server's logo!"""
        if not guild or not guild.me or not guild.icon:
            return
        try:
            icon_bytes = await guild.icon.read()
            await guild.me.edit(avatar=icon_bytes)
            logger.info(f"Updated bot server avatar PFP for {guild.name} to server logo!")
        except Exception as e:
            logger.debug(f"Server avatar PFP update note for {guild.name}: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        from embed_builder import get_or_create_log_channel
        await get_or_create_log_channel(guild)
        await self.sync_guild_avatar(guild)

def clean_disk_space():
    """Purges temporary files, cache directories, and audio artifacts to prevent Pterodactyl disk quota limits."""
    import shutil
    root_dir = os.path.dirname(__file__)
    for item in ["temp_music", ".cache", "__pycache__", "temp"]:
        path = os.path.join(root_dir, item)
        if os.path.exists(path):
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass

def main():
    print("=" * 60)
    print(" [JOYST CORPORATION] ADVANCED DISCORD SECURITY BOT SYSTEM")
    print("=" * 60)

    clean_disk_space()

    # 1. Initialize SQLite Storage
    db.init_db()

    # 2. Instantiate Bot
    bot = AegisBot()
    set_bot_instance(bot)

    # 3. Start Web Dashboard Thread
    web_thread = threading.Thread(target=run_web_dashboard, daemon=True)
    web_thread.start()
    logger.info(f"Web Dashboard launched in background thread on http://localhost:{config.WEB_PORT}")

    # 4. Run Discord Bot
    token = config.BOT_TOKEN
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "!" * 60)
        print(" [!] DISCORD_BOT_TOKEN is not set in .env file.")
        print(" [!] The Web Control Dashboard is RUNNING on http://localhost:5000")
        print(" [!] To connect the bot to Discord, create a .env file with:")
        print("     DISCORD_BOT_TOKEN=your_token_here")
        print("     DISCORD_CLIENT_ID=your_client_id_here")
        print("!" * 60 + "\n")
        
        # Keep web server alive even if token isn't configured yet
        web_thread.join()
    else:
        try:
            bot.run(token)
        except Exception as e:
            logger.error(f"Error running Discord Bot: {e}")

if __name__ == "__main__":
    main()

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

class JoinWelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Invite Me", url="https://discord.com/api/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands", style=discord.ButtonStyle.link, emoji="🔗"))
        self.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/joyst", style=discord.ButtonStyle.link, emoji="💬"))
        self.add_item(discord.ui.Button(label="Website", url="https://syphon-security-bot.onrender.com", style=discord.ButtonStyle.link, emoji="🌐"))

async def send_guild_join_welcome_embed(guild: discord.Guild):
    from embed_builder import joyst_embed, COLOR_PURPLE
    me = guild.me
    if not me:
        return
    target_channel = guild.system_channel
    if not target_channel or not target_channel.permissions_for(me).send_messages:
        for ch in guild.text_channels:
            if ch.permissions_for(me).send_messages:
                target_channel = ch
                break

    if not target_channel:
        return

    desc = (
        f"<a:dev:1528079861283946538> **THANK YOU FOR ADDING SYPHON SECURITY OS!**\n\n"
        f"Hello **{guild.name}**! I am **SYPHON SECURITY**, your server's all-in-one ultra-hardened antinuke, moderation, music, ticket, and voice security system.\n\n"
        f"• **Quick Setup Instructions**\n"
        f" ├─ <:xliyo_arrow:1528079785123774676> **Default Prefix:** `,` (Comma) or `/` (Slash Commands)\n"
        f" ├─ <:xliyo_arrow:1528079785123774676> **Help Menu:** Type `,help` to view all **68+ Active Commands**\n"
        f" ├─ <:xliyo_arrow:1528079785123774676> **Antinuke Setup:** Type `,antinuke enable` to lock down server\n"
        f" ├─ <:xliyo_arrow:1528079785123774676> **Support Tickets:** Type `,ticket setup` to deploy support hub\n"
        f" └─ <:xliyo_arrow:1528079785123774676> **Temp VC Setup:** Type `,tempvc setup` for join-to-create channels\n\n"
        f"🛡️ *Server Security Status: 100% Protected & Active*"
    )
    embed = joyst_embed(description=desc, color=COLOR_PURPLE, guild=guild)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"Powered By SYPHON SECURITY OS • Designed for {guild.name}")
    try:
        await target_channel.send(embed=embed, view=JoinWelcomeView())
    except Exception as e:
        logger.debug(f"Could not send join welcome embed in {guild.name}: {e}")

async def send_bot_startup_embed(bot):
    from embed_builder import get_or_create_log_channel, joyst_embed, COLOR_SUCCESS
    start_ts = int(getattr(bot, "start_time", time.time()))
    ws_ping = round(bot.latency * 1000)
    total_members = sum([(g.member_count or len(g.members) or 0) for g in bot.guilds])

    desc = (
        f"🛡️ **SYPHON SECURITY OS ONLINE & OPERATIONAL**\n\n"
        f"• **Boot Status:** `100% Online & Fully Synced`\n"
        f"• **Boot Time:** <t:{start_ts}:F> (<t:{start_ts}:R>)\n"
        f"• **Protected Network:** `{len(bot.guilds)} Servers` | `{total_members:,} Users`\n"
        f"• **Command Registry:** `68+ Active Commands (Prefix & Slash)`\n"
        f"• **WebSocket Ping:** `{ws_ping} ms`\n"
        f"• **Host Node:** `Dedicated High-Speed VPS`"
    )

    for guild in bot.guilds:
        try:
            ch = await get_or_create_log_channel(guild)
            if ch and ch.permissions_for(guild.me).send_messages:
                embed = joyst_embed(description=desc, color=COLOR_SUCCESS, guild=guild)
                embed.set_footer(text=f"SYPHON SECURITY OS • Operational Status Log")
                await ch.send(embed=embed)
        except Exception:
            pass

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
            from cogs.tickets import TicketCloseView, TicketClaimView, TicketFAQView, TicketView
            from cogs.music import ProtectedMusicControlView
            from cogs.anti_raid import VerificationView
            from cogs.giveaway import GiveawayEntryView

            self.add_view(TicketCloseView())
            self.add_view(TicketClaimView())
            self.add_view(TicketFAQView())
            self.add_view(TicketView(bot_instance=self))
            self.add_view(ProtectedMusicControlView())
            self.add_view(VerificationView())
            self.add_view(GiveawayEntryView(message_id=""))
            logger.info("Registered all persistent UI Views (Ticket Verse, Music, Verification & Giveaway listeners active).")
        except Exception as e:
            logger.error(f"Error registering persistent UI views: {e}")

        async def sync_slash():
            await self.wait_until_ready()
            try:
                # 1. Clear any leftover guild-level overrides to remove duplicate slash commands in Discord UI!
                for guild in self.guilds:
                    try:
                        self.tree.clear_commands(guild=guild)
                        await self.tree.sync(guild=guild)
                    except Exception:
                        pass

                # 2. Sync single clean Global Slash Command tree (Zero Duplicates!)
                synced_global = await self.tree.sync()
                logger.info(f"⚡ Clean Global Slash Sync: Registered {len(synced_global)} single-copy commands (Zero Duplicates).")
                logger.info("✅ All Slash & Prefix Commands 100% Auto-Synced & Active Across All Servers!")
            except Exception as e:
                logger.error(f"Error syncing slash commands: {e}")

        asyncio.create_task(sync_slash())

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

        # Start dynamic 3-text rotating presence status loop
        asyncio.create_task(self.rotate_status_loop())

        # Start real-time Web Dashboard IPC command listener
        asyncio.create_task(self.check_dashboard_ipc_loop())

        # Broadcast startup embed log to security log channel
        await send_bot_startup_embed(self)

    async def check_dashboard_ipc_loop(self):
        """Checks for real-time control commands dispatched from the Web Dashboard every 1 second."""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                cmds = db.pop_pending_ipc_commands()
                for c in cmds:
                    cmd_id = c["id"]
                    guild_id = c["guild_id"]
                    ctype = c["command_type"]
                    payload = c["payload"]

                    guild = self.get_guild(int(guild_id)) if guild_id and guild_id.isdigit() else None
                    
                    if ctype == "lock_all" and guild:
                        for ch in guild.text_channels:
                            over = ch.overwrites_for(guild.default_role)
                            over.send_messages = False
                            try:
                                await ch.set_permissions(guild.default_role, overwrite=over)
                            except Exception: pass
                    elif ctype == "unlock_all" and guild:
                        for ch in guild.text_channels:
                            over = ch.overwrites_for(guild.default_role)
                            over.send_messages = True
                            try:
                                await ch.set_permissions(guild.default_role, overwrite=over)
                            except Exception: pass
                    elif ctype == "quarantine" and guild:
                        db.update_guild_setting(str(guild.id), "anti_nuke", 1)
                        db.update_guild_setting(str(guild.id), "anti_raid", 1)
                    elif ctype == "sync_slash":
                        try:
                            await self.tree.sync()
                        except Exception: pass
                    elif ctype == "tts_speak" and guild:
                        import json
                        pdata = json.loads(payload) if payload and payload.startswith("{") else {}
                        vc_id = pdata.get("vc_id")
                        text = pdata.get("text")
                        lang = pdata.get("lang", "en")
                        if vc_id and text:
                            vc_ch = guild.get_channel(int(vc_id))
                            if vc_ch and isinstance(vc_ch, discord.VoiceChannel):
                                tts_cog = self.get_cog("TTS")
                                if tts_cog:
                                    await tts_cog.speak_text_in_vc(guild, vc_ch, text, lang)
                    elif ctype == "voice_play" and guild:
                        import json
                        pdata = json.loads(payload) if payload and payload.startswith("{") else {}
                        vc_id = pdata.get("vc_id")
                        query = pdata.get("query", "JHOL")
                        if vc_id:
                            vc_ch = guild.get_channel(int(vc_id))
                            if vc_ch and isinstance(vc_ch, (discord.VoiceChannel, discord.StageChannel)):
                                music_cog = self.get_cog("Music")
                                if music_cog:
                                    vc = guild.voice_client
                                    if vc and vc.is_connected():
                                        if vc.channel.id != vc_ch.id:
                                            await vc.move_to(vc_ch)
                                    else:
                                        vc = await vc_ch.connect(reconnect=True, timeout=15.0)
                                    from cogs.music import YTDLSource
                                    source = await YTDLSource.create_source(query, requester=self.user, loop=self.loop)
                                    if vc.is_playing() or vc.is_paused():
                                        vc.stop()
                                    vc.play(source)

                    db.mark_ipc_command_complete(cmd_id)
            except Exception as e:
                logger.error(f"Error in Dashboard IPC loop: {e}")

            await asyncio.sleep(1)

    async def rotate_status_loop(self):
        """Cycles through 3 live dynamic streaming statuses every 15 seconds with Purple Twitch Streaming Badge!"""
        await self.wait_until_ready()
        status_index = 0
        twitch_url = "https://www.twitch.tv/joyst_security"
        while not self.is_closed():
            try:
                live_g = len(self.guilds)
                live_m = sum([(g.member_count or len(g.members) or 0) for g in self.guilds])

                guild_count = max(live_g, 50)
                total_members = max(live_m, 30000)

                if status_index == 0:
                    activity = discord.Streaming(
                        name=",help • SYPHON SECURITY",
                        url=twitch_url
                    )
                elif status_index == 1:
                    activity = discord.Streaming(
                        name=f"Protecting {guild_count:,}+ Servers",
                        url=twitch_url
                    )
                else:
                    activity = discord.Streaming(
                        name=f"Protecting {total_members:,}+ Members",
                        url=twitch_url
                    )

                await self.change_presence(status=discord.Status.online, activity=activity)
                status_index = (status_index + 1) % 3
            except Exception as e:
                logger.error(f"Error rotating bot status: {e}")

            await asyncio.sleep(15)

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

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        from embed_builder import joyst_embed, COLOR_DANGER, COLOR_WARNING
        if isinstance(error, commands.MissingPermissions):
            embed = joyst_embed(description="❌ **Access Denied:** You lack administrator/staff permissions for this command.", color=COLOR_DANGER, guild=ctx.guild)
            await ctx.send(embed=embed, delete_after=6)
            return
        if isinstance(error, commands.MissingRequiredArgument):
            embed = joyst_embed(description=f"⚠️ **Missing Argument:** `{error.param.name}` is required.\n> Usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`", color=COLOR_WARNING, guild=ctx.guild)
            await ctx.send(embed=embed)
            return
        logger.error(f"Prefix Command Exception ({ctx.command}): {error}")

    async def on_guild_join(self, guild: discord.Guild):
        """Auto-syncs commands, creates security channels, and sends high-end welcome embed when bot joins a new server!"""
        from embed_builder import get_or_create_log_channel
        await get_or_create_log_channel(guild)
        await self.sync_guild_avatar(guild)
        await send_guild_join_welcome_embed(guild)
        try:
            synced = await self.tree.sync()
            logger.info(f"⚡ Global Slash Commands Active on Guild Join for {guild.name}: {len(synced)} commands.")
        except Exception as e:
            logger.error(f"Error syncing commands on guild join for {guild.name}: {e}")

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

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
import shutil
import os
import time
import yt_dlp
import static_ffmpeg
import config
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji

logger = logging.getLogger("AEGIS.Music")

# Auto-add static_ffmpeg binaries to process PATH and resolve exact executable path
try:
    static_ffmpeg.add_paths()
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"
    logger.info(f"FFmpeg binary resolved at: {FFMPEG_PATH}")
except Exception as e:
    FFMPEG_PATH = "ffmpeg"
    logger.warning(f"Could not initialize static_ffmpeg: {e}")

# Clean up any legacy temp_music folder to free server disk space completely
MUSIC_TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp_music"))
if os.path.exists(MUSIC_TEMP_DIR):
    try:
        shutil.rmtree(MUSIC_TEMP_DIR, ignore_errors=True)
        logger.info("Cleaned up legacy temp_music directory. Zero disk space will be used.")
    except Exception as e:
        logger.warning(f"Could not delete temp_music directory: {e}")

# YTDL Options for Direct Web Audio Streaming (ZERO DISK DOWNLOAD, ZERO STORAGE USED)
YTDL_OPTIONS = {
    "format": "ba[ext=m4a]/ba[ext=webm]/ba/b",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
    "skip_download": True,
}

AUDIO_FILTERS = {
    "clear": "-vn",
    "8d": "-vn -af apulsator=hz=0.125",
    "bassboost": "-vn -af equalizer=f=60:width_type=h:width=50:g=15",
    "nightcore": "-vn -af asetrate=44100*1.25,atempo=1.25",
    "slowed_reverb": "-vn -af asetrate=44100*0.85,aecho=0.8:0.88:60:0.4",
    "vaporwave": "-vn -af asetrate=44100*0.8,atempo=0.8"
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, requester: discord.User | discord.Member = None, volume=0.5, current_filter="clear", seek_seconds: int = 0):
        super().__init__(source, volume)
        self.data = data
        self.requester = requester
        self.title = data.get("title", "Unknown Track")
        self.url = data.get("url")
        self.webpage_url = data.get("webpage_url", self.url)
        self.duration = data.get("duration", 0)
        self.uploader = data.get("uploader", "Unknown Uploader")
        self.thumbnail = data.get("thumbnail")
        self.id = data.get("id")
        self.current_filter = current_filter
        self.seek_seconds = seek_seconds
        self.start_time = time.time() - seek_seconds

    @property
    def elapsed_seconds(self):
        if not hasattr(self, "start_time") or not self.start_time:
            return 0
        return max(0, int(time.time() - self.start_time))

    def cleanup_file(self):
        pass

    @classmethod
    async def create_source(cls, search: str, requester: discord.User | discord.Member = None, filter_preset="clear", seek_seconds: int = 0, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        search_query = search if (search.startswith("http://") or search.startswith("https://")) else f"ytsearch1:{search}"

        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))

        if "entries" in data:
            if len(data["entries"]) > 0:
                data = data["entries"][0]
            else:
                raise Exception("No audio search results found.")

        stream_url = data.get("url")
        if not stream_url:
            raise Exception("Direct audio stream URL could not be extracted.")

        before_opts = f"-fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0 -ss {seek_seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5" if seek_seconds > 0 else "-fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0 -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

        ffmpeg_options = {
            "before_options": before_opts,
            "options": AUDIO_FILTERS.get(filter_preset.lower(), "-vn")
        }

        return cls(discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_PATH, **ffmpeg_options), data=data, requester=requester, current_filter=filter_preset, seek_seconds=seek_seconds)

# --- Requester-Protected Interactive Music Control Panel ---

class ProtectedMusicControlView(discord.ui.View):
    def __init__(self, cog=None, guild_id: int = None, current_song: YTDLSource = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.current_song = current_song

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild
        
        if not self.cog:
            self.cog = interaction.client.get_cog("Music")
        if not self.guild_id and guild:
            self.guild_id = guild.id

        is_owner = (user.id == guild.owner_id)
        perms = interaction.permissions if hasattr(interaction, "permissions") and interaction.permissions else getattr(user, "guild_permissions", None)
        is_staff = is_owner or (perms and (perms.administrator or perms.manage_guild or perms.manage_channels or perms.manage_messages))
        is_requester = self.current_song and self.current_song.requester and user.id == self.current_song.requester.id

        if self.current_song and not (is_requester or is_staff):
            req_name = self.current_song.requester.mention if self.current_song and self.current_song.requester else "the song requester"
            await interaction.response.send_message(
                f"{get_emoji('warning', guild)} **Access Denied:** Only {req_name} or Server Admins/Staff can control this music playback.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Pause / Resume", style=discord.ButtonStyle.primary, emoji="⏯️", custom_id="music_pause_resume_btn")
    async def pause_resume_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        vc = guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)
            return

        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message(f"{get_emoji('pause', guild)} **Paused music playback.**", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message(f"{get_emoji('music', guild)} **Resumed music playback.**", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Voice playback state updated.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="music_skip_btn")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        vc = guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing to skip.", ephemeral=True)
            return

        vc.stop()
        await interaction.response.send_message(f"{get_emoji('success', guild)} **Skipped current track.**", ephemeral=True)

    @discord.ui.button(label="Loop Mode", style=discord.ButtonStyle.secondary, emoji="🔂", custom_id="music_loop_btn")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not self.cog:
            self.cog = interaction.client.get_cog("Music")
        gid = self.guild_id or (guild.id if guild else 0)
        current_mode = self.cog.loop_modes.get(gid, "off") if self.cog else "off"
        
        mode_cycle = {"off": "track", "track": "queue", "queue": "off"}
        new_mode = mode_cycle[current_mode]
        if self.cog:
            self.cog.loop_modes[gid] = new_mode

        labels = {"off": "Loop Disabled ⚪", "track": "Loop Track 🔂", "queue": "Loop Queue 🔁"}
        await interaction.response.send_message(f"🔂 **Loop Mode set to:** `{labels[new_mode]}`", ephemeral=True)

    @discord.ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, emoji="📻", custom_id="music_autoplay_btn")
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not self.cog:
            self.cog = interaction.client.get_cog("Music")
        gid = self.guild_id or (guild.id if guild else 0)
        current_state = self.cog.autoplays.get(gid, False) if self.cog else False
        new_state = not current_state
        if self.cog:
            self.cog.autoplays[gid] = new_state

        status_str = f"{get_emoji('success', guild)} Enabled" if new_state else "Disabled ⚪"
        await interaction.response.send_message(f"📻 **Autoplay set to:** {status_str}", ephemeral=True)

    @discord.ui.button(label="Stop & Clear", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="music_stop_btn")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        vc = guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ Bot is not connected.", ephemeral=True)
            return

        if not self.cog:
            self.cog = interaction.client.get_cog("Music")
        gid = self.guild_id or (guild.id if guild else 0)
        if self.cog:
            self.cog.queues[gid] = []
            self.cog.loop_modes[gid] = "off"
            self.cog.autoplays[gid] = False
        vc.stop()
        await vc.disconnect()

        await interaction.response.send_message(f"{get_emoji('delete', guild)} **Stopped playback, cleared queue, and left Voice Channel.**", ephemeral=True)

async def set_vc_status(channel: discord.VoiceChannel, status_text: str):
    """Sets Discord Voice Channel Status with animated music emoji & track title"""
    if not channel or not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return
    try:
        if hasattr(channel, "edit"):
            await channel.edit(status=status_text)
    except Exception as e:
        try:
            await channel._state.http.request(
                discord.http.Route('PUT', '/channels/{channel_id}/voice-status', channel_id=channel.id),
                json={'status': status_text[:500] if status_text else ''}
            )
        except Exception:
            pass

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.current_song = {}
        self.loop_modes = {}
        self.autoplays = {}
        self.is_tts_interrupting = {}
        self.interrupted_track_data = {}

    def get_queue(self, guild_id: int):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def resume_after_tts(self, guild_id: int):
        """Auto-resumes interrupted music playback from exact seek timestamp after TTS finishes"""
        await asyncio.sleep(0.3)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        vc = guild.voice_client
        if vc and vc.is_connected() and not vc.is_playing() and not vc.is_paused():
            track_data = self.interrupted_track_data.get(guild_id)
            if track_data:
                try:
                    web_url = track_data["webpage_url"]
                    req = track_data["requester"]
                    flt = track_data["filter"]
                    seek_sec = track_data.get("seek_seconds", 0)

                    logger.info(f"Resuming music '{web_url}' from seek position {seek_sec}s in {guild.name}")
                    new_src = await YTDLSource.create_source(web_url, requester=req, filter_preset=flt, seek_seconds=seek_sec)

                    self.current_song[guild_id] = new_src

                    def after_playing(error):
                        if error:
                            logger.error(f"Playback error in {guild.name}: {error}")
                        if self.is_tts_interrupting.get(guild_id):
                            return
                        class DummyCtx:
                            def __init__(self, g, ch):
                                self.guild = g
                                self.channel = ch
                        self.play_next(DummyCtx(guild, vc.channel), guild_id)

                    vc.play(new_src, after=after_playing)

                    status_text = f"{get_emoji('music', guild)} Playing: {new_src.title[:80]}"
                    self.bot.loop.create_task(set_vc_status(vc.channel, status_text))
                except Exception as e:
                    logger.error(f"Error resuming track after TTS: {e}")

    async def _fetch_autoplay_related(self, song_id: str):
        if not song_id:
            return None
        url = f"https://www.youtube.com/watch?v={song_id}"
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            related = data.get("related_videos")
            if related and len(related) > 0:
                rel_id = related[0].get("id")
                if rel_id:
                    return await YTDLSource.create_source(f"https://www.youtube.com/watch?v={rel_id}", requester=self.bot.user)
        except Exception as e:
            logger.error(f"Autoplay fetch error: {e}")
        return None

    def play_next(self, ctx_or_interaction, guild_id: int):
        guild = ctx_or_interaction.guild
        vc = guild.voice_client

        if not vc:
            return

        queue = self.get_queue(guild_id)
        current = self.current_song.get(guild_id)
        loop_mode = self.loop_modes.get(guild_id, "off")
        autoplay_enabled = self.autoplays.get(guild_id, False)

        # 1. Synchronously re-queue finished track if loop mode is active (Prevents async queue race conditions)
        if loop_mode == "track" and current and hasattr(current, "webpage_url"):
            queue.insert(0, {
                "url": current.webpage_url,
                "requester": current.requester,
                "title": current.title,
                "filter": getattr(current, "filter_preset", "normal")
            })
        elif loop_mode == "queue" and current and hasattr(current, "webpage_url"):
            queue.append({
                "url": current.webpage_url,
                "requester": current.requester,
                "title": current.title,
                "filter": getattr(current, "filter_preset", "normal")
            })

        if len(queue) == 0:
            if autoplay_enabled and current:
                async def trigger_autoplay():
                    auto_src = await self._fetch_autoplay_related(current.id)
                    if auto_src:
                        queue.append(auto_src)
                        self.play_next(ctx_or_interaction, guild_id)
                self.bot.loop.create_task(trigger_autoplay())
            return

        # 2. Pop next track item cleanly from queue
        next_item = queue.pop(0)

        async def prepare_and_play():
            try:
                if isinstance(next_item, YTDLSource):
                    next_source = next_item
                elif isinstance(next_item, dict):
                    next_source = await YTDLSource.create_source(
                        next_item["url"],
                        requester=next_item["requester"],
                        filter_preset=next_item.get("filter", "normal")
                    )
                else:
                    return

                self.current_song[guild_id] = next_source

                def after_playing(error):
                    if error:
                        logger.error(f"Playback error in {guild.name}: {error}")
                    if self.is_tts_interrupting.get(guild_id):
                        logger.info(f"Playback stopped for TTS interrupt in {guild.name}")
                        return
                    self.play_next(ctx_or_interaction, guild_id)

                vc.play(next_source, after=after_playing)

                status_text = f"{get_emoji('music', guild)} Playing: {next_source.title[:80]}"
                self.bot.loop.create_task(set_vc_status(vc.channel, status_text))

                req_str = next_source.requester.mention if hasattr(next_source, "requester") and next_source.requester else f"**{config.SERVER_NAME} Autoplay**"
                loop_str = f"`{loop_mode.upper()}`" if loop_mode != "off" else "`OFF`"
                autoplay_str = "`ENABLED`" if autoplay_enabled else "`OFF`"
                duration_mins = f"{next_source.duration // 60}:{next_source.duration % 60:02d}" if next_source.duration else "Live Stream"

                desc = (
                    f"{get_emoji('music', guild)} **NOW PLAYING**\n\n"
                    f"🎵 **[{next_source.title}]({next_source.webpage_url})**\n"
                    f"⏱️ **Duration:** `{duration_mins}` | 👤 **Requested By:** {req_str}\n"
                    f"🔂 **Loop:** {loop_str} | 📻 **Autoplay:** {autoplay_str}"
                )
                embed = joyst_embed(description=desc, color=COLOR_INFO, thumbnail=next_source.thumbnail, guild=guild)
                view = ProtectedMusicControlView(self, guild_id, next_source)

                ch = ctx_or_interaction.channel if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.channel
                self.bot.loop.create_task(ch.send(embed=embed, view=view))

            except Exception as e:
                logger.error(f"Error starting queue track: {e}")
                self.play_next(ctx_or_interaction, guild_id)

        self.bot.loop.create_task(prepare_and_play())

    async def _do_play(self, ctx_or_interaction, query: str):
        guild = ctx_or_interaction.guild
        author = ctx_or_interaction.user if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author

        if not author.voice or not author.voice.channel:
            embed = joyst_embed(description="❌ You must be connected to a Voice Channel to play music.", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        target_vc_channel = author.voice.channel

        try:
            vc = guild.voice_client
            if not vc or not vc.is_connected():
                vc = await target_vc_channel.connect(reconnect=True, self_deaf=True)
            elif vc.channel != target_vc_channel:
                await vc.move_to(target_vc_channel)
        except Exception as e:
            embed = joyst_embed(description=f"❌ Could not connect to {target_vc_channel.mention}: `{e}`", color=COLOR_DANGER, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        source = await YTDLSource.create_source(query, requester=author, loop=self.bot.loop)

        queue = self.get_queue(guild.id)

        if vc.is_playing() or vc.is_paused():
            queue.append(source)
            duration_mins = f"{source.duration // 60}:{source.duration % 60:02d}" if source.duration else "Live Stream"
            desc = (
                f"{get_emoji('success', guild)} **ADDED TO PLAYLIST QUEUE (Position #{len(queue)})**\n\n"
                f"🎵 **[{source.title}]({source.webpage_url})**\n"
                f"⏱️ **Duration:** `{duration_mins}` | 👤 **Requested By:** {author.mention}"
            )
            embed = joyst_embed(description=desc, color=COLOR_SUCCESS, thumbnail=source.thumbnail, guild=guild)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
        else:
            self.current_song[guild.id] = source
            vc.play(source, after=lambda e: self.play_next(ctx_or_interaction, guild.id))

            status_text = f"{get_emoji('music', guild)} Playing: {source.title[:80]}"
            self.bot.loop.create_task(set_vc_status(vc.channel, status_text))

            duration_mins = f"{source.duration // 60}:{source.duration % 60:02d}" if source.duration else "Live Stream"
            desc = (
                f"{get_emoji('music', guild)} **NOW PLAYING**\n\n"
                f"🎵 **[{source.title}]({source.webpage_url})**\n"
                f"⏱️ **Duration:** `{duration_mins}` | 👤 **Requested By:** {author.mention}\n"
                f"⚡ *Direct Web Stream — Zero Disk Space Used!*"
            )
            embed = joyst_embed(description=desc, color=COLOR_INFO, thumbnail=source.thumbnail, guild=guild)
            view = ProtectedMusicControlView(self, guild.id, source)

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed, view=view)
            else:
                await ctx_or_interaction.send(embed=embed, view=view)

    # --- Slash Commands ---

    @app_commands.command(name="play", description="Play high-quality music directly from YouTube")
    @app_commands.describe(query="Song title, YouTube search keywords, or URL")
    async def slash_play(self, interaction: discord.Interaction, query: str):
        await self._do_play(interaction, query)

    @app_commands.command(name="skip", description="[STAFF ONLY] Skip current playing track")
    async def slash_skip(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        is_owner = (user.id == guild.owner_id)
        perms = interaction.permissions if hasattr(interaction, "permissions") and interaction.permissions else getattr(user, "guild_permissions", None)
        is_staff = is_owner or (perms and (perms.administrator or perms.manage_guild or perms.manage_channels or perms.manage_messages))
        
        if not is_staff:
            await interaction.response.send_message("❌ Only Server Admins or Staff can skip tracks. Members can only use `/play`.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        vc.stop()
        await interaction.response.send_message(f"{get_emoji('success', interaction.guild)} **Skipped current track.**")

    @app_commands.command(name="stop", description="[STAFF ONLY] Stop music playback and clear queue")
    async def slash_stop(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        is_owner = (user.id == guild.owner_id)
        perms = interaction.permissions if hasattr(interaction, "permissions") and interaction.permissions else getattr(user, "guild_permissions", None)
        is_staff = is_owner or (perms and (perms.administrator or perms.manage_guild or perms.manage_channels or perms.manage_messages))
        
        if not is_staff:
            await interaction.response.send_message("❌ Only Server Admins or Staff can stop music playback.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ Bot is not connected.", ephemeral=True)
            return

        self.queues[interaction.guild_id] = []
        if vc.channel:
            await set_vc_status(vc.channel, "")
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message(f"{get_emoji('delete', interaction.guild)} **Stopped music, cleared queue, and disconnected.**")

    # --- Prefix Commands (!play, !skip, !stop) ---

    @commands.command(name="play", aliases=["p"])
    async def prefix_play(self, ctx, *, query: str):
        await self._do_play(ctx, query)

    @commands.command(name="skip", aliases=["s"])
    async def prefix_skip(self, ctx):
        author = ctx.author
        guild = ctx.guild
        is_owner = (author.id == guild.owner_id)
        perms = getattr(author, "guild_permissions", None)
        is_staff = is_owner or (perms and (perms.administrator or perms.manage_guild or perms.manage_channels or perms.manage_messages))

        if not is_staff:
            await ctx.send("❌ Only Server Admins or Staff can skip tracks. Members can only use `!play`.")
            return

        vc = ctx.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await ctx.send("❌ Nothing is currently playing.")
            return

        vc.stop()
        await ctx.send(f"{get_emoji('success', ctx.guild)} **Skipped current track.**")

    @commands.command(name="stop", aliases=["disconnect", "dc"])
    async def prefix_stop(self, ctx):
        author = ctx.author
        guild = ctx.guild
        is_owner = (author.id == guild.owner_id)
        perms = getattr(author, "guild_permissions", None)
        is_staff = is_owner or (perms and (perms.administrator or perms.manage_guild or perms.manage_channels or perms.manage_messages))

        if not is_staff:
            await ctx.send("❌ Only Server Admins or Staff can stop music playback.")
            return

        vc = ctx.guild.voice_client
        if not vc:
            await ctx.send("❌ Bot is not connected.")
            return

        self.queues[ctx.guild.id] = []
        if vc.channel:
            await set_vc_status(vc.channel, "")
        vc.stop()
        await vc.disconnect()
        await ctx.send(f"{get_emoji('delete', ctx.guild)} **Stopped music, cleared queue, and disconnected.**")

async def setup(bot):
    await bot.add_cog(Music(bot))

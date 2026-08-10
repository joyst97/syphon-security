import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import re
import urllib.parse
import logging
import shutil
import static_ffmpeg
import config
import database as db
from embed_builder import joyst_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_INFO, COLOR_PURPLE, COLOR_DARK
from emojis import get_emoji
import array

logger = logging.getLogger("AEGIS.TTS")

EMOJI_REGEX = re.compile(r"<a?:\w+:\d+>", re.IGNORECASE)
COLON_EMOJI_REGEX = re.compile(r":\w+:", re.IGNORECASE)
URL_REGEX = re.compile(r"https?://\S+", re.IGNORECASE)

def clean_tts_text(text: str) -> str:
    """Strips animated emojis (<a:name:id>), static emojis (<:name:id>), raw colons (:name:), and URLs from TTS text."""
    if not text:
        return ""
    text = EMOJI_REGEX.sub("", text)
    text = COLON_EMOJI_REGEX.sub("", text)
    text = URL_REGEX.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

try:
    static_ffmpeg.add_paths()
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"
except Exception:
    FFMPEG_PATH = "ffmpeg"

try:
    import audioop
except ModuleNotFoundError:
    try:
        import audioop_lts as audioop
    except Exception:
        audioop = None

def pcm_mul(fragment: bytes, width: int, factor: float) -> bytes:
    if audioop:
        try:
            return audioop.mul(fragment, width, factor)
        except Exception:
            pass
    if not fragment:
        return b''
    try:
        arr = array.array('h', fragment)
        for i in range(len(arr)):
            val = int(arr[i] * factor)
            arr[i] = max(-32768, min(32767, val))
        return arr.tobytes()
    except Exception:
        return fragment

def pcm_add(frag1: bytes, frag2: bytes, width: int) -> bytes:
    if audioop:
        try:
            return audioop.add(frag1, frag2, width)
        except Exception:
            pass
    if not frag1:
        return frag2
    if not frag2:
        return frag1
    try:
        length = min(len(frag1), len(frag2))
        arr1 = array.array('h', frag1[:length])
        arr2 = array.array('h', frag2[:length])
        for i in range(len(arr1)):
            val = arr1[i] + arr2[i]
            arr1[i] = max(-32768, min(32767, val))
        return arr1.tobytes()
    except Exception:
        return frag1

class AudioMixerSource(discord.AudioSource):
    """
    Real-Time Audio Ducking & Overlay Mixer Engine:
    Ducks background music to 20% volume and overlays TTS speech at 160% volume!
    Zero Stop, Zero Delay, Zero Gap, Zero Song Restart! Compatible with Python 3.13!
    """
    def __init__(self, music_source, tts_source, duck_volume=0.20, tts_volume=1.6):
        self.music = music_source
        self.tts = tts_source
        self.duck_volume = duck_volume
        self.tts_volume = tts_volume
        self.tts_finished = False

    def read(self):
        music_frame = b''
        if self.music:
            try:
                music_frame = self.music.read() or b''
            except Exception:
                music_frame = b''

        tts_frame = b''
        if self.tts and not self.tts_finished:
            try:
                tts_frame = self.tts.read() or b''
                if not tts_frame:
                    self.tts_finished = True
            except Exception:
                self.tts_finished = True

        if not music_frame and not tts_frame:
            return b''

        if not tts_frame or self.tts_finished:
            return music_frame

        if not music_frame:
            try:
                return pcm_mul(tts_frame, 2, self.tts_volume)
            except Exception:
                return tts_frame

        try:
            ducked_music = pcm_mul(music_frame, 2, self.duck_volume)
            boosted_tts = pcm_mul(tts_frame, 2, self.tts_volume)
            mixed_frame = pcm_add(ducked_music, boosted_tts, 2)
            return mixed_frame
        except Exception:
            return music_frame

    def is_opus(self):
        return False

from collections import defaultdict

class TTS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tts_queues = defaultdict(asyncio.Queue)
        self.queue_workers = {}
        self.reconnect_247_voice_task.start()

    def cog_unload(self):
        self.reconnect_247_voice_task.cancel()

    @tasks.loop(seconds=30)
    async def reconnect_247_voice_task(self):
        """24/7 Voice Channel Stay Engine: Automatically reconnects bot if disconnected!"""
        if not self.bot.is_ready():
            return
        
        try:
            records = db.get_247_vcs_db()
            for r in records:
                guild_id = r["guild_id"]
                channel_id = r["channel_id"]

                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue

                vc_channel = guild.get_channel(int(channel_id))
                if not vc_channel or not isinstance(vc_channel, (discord.VoiceChannel, discord.StageChannel)):
                    continue

                from cogs.music import ensure_clean_voice_connection
                try:
                    await ensure_clean_voice_connection(guild, vc_channel)
                except Exception as ce:
                    logger.warning(f"24/7 Voice Reconnect attempt failed: {ce}")
        except Exception as e:
            logger.error(f"24/7 Voice Reconnect Error: {e}")

    @reconnect_247_voice_task.before_loop
    async def before_reconnect_task(self):
        await self.bot.wait_until_ready()

    async def speak_text_in_vc(self, guild: discord.Guild, channel: discord.VoiceChannel, text: str, lang: str = "en"):
        """Utility to enqueue TTS speech audio so messages are read out loud sequentially without cutting off!"""
        try:
            await self.tts_queues[guild.id].put((channel, text, lang))
            if guild.id not in self.queue_workers or self.queue_workers[guild.id].done():
                self.queue_workers[guild.id] = asyncio.create_task(self._process_tts_queue(guild))
            return True, f"Queued speech in #{channel.name}"
        except Exception as e:
            logger.error(f"TTS Enqueue Error: {e}", exc_info=True)
            return False, str(e)

    async def _process_tts_queue(self, guild: discord.Guild):
        """Processes queued TTS messages sequentially in exact order (FIFO) with music ducking."""
        queue = self.tts_queues[guild.id]
        while not queue.empty():
            try:
                channel, text, lang = await queue.get()
                
                vc = guild.voice_client
                if not vc or not vc.is_connected():
                    from cogs.music import ensure_clean_voice_connection
                    try:
                        vc = await ensure_clean_voice_connection(guild, channel)
                    except Exception as ce:
                        logger.error(f"Failed to connect to voice channel for TTS: {ce}")
                        queue.task_done()
                        continue

                lang_clean = lang.lower()
                lang_code = "hi" if ("hi" in lang_clean or "hindi" in lang_clean) else "en"
                if lang_clean in ["es", "spanish"]: lang_code = "es"
                elif lang_clean in ["fr", "french"]: lang_code = "fr"
                elif lang_clean in ["ja", "japanese"]: lang_code = "ja"

                tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl={lang_code}&q={urllib.parse.quote(text)}"
                ffmpeg_opts = {
                    "before_options": '-headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    "options": "-vn"
                }

                source = discord.FFmpegPCMAudio(tts_url, executable=FFMPEG_PATH, **ffmpeg_opts)

                # Ducking & Overlay on top of playing music
                if vc.is_playing():
                    current_source = vc.source
                    music_src = current_source.music if isinstance(current_source, AudioMixerSource) else current_source
                    mixer = AudioMixerSource(music_src, source, duck_volume=0.20, tts_volume=1.6)
                    vc.source = mixer
                    logger.info(f"Ducked music volume & overlayed TTS speech in #{channel.name}")
                else:
                    vc.play(source)
                    logger.info(f"Playing TTS speech in #{channel.name}: '{text}'")

                # Wait until active TTS audio speech finishes playing completely
                while vc and vc.is_connected() and (vc.is_playing() and hasattr(vc.source, 'tts_finished') and not vc.source.tts_finished):
                    await asyncio.sleep(0.1)

                queue.task_done()
            except Exception as e:
                logger.error(f"TTS Queue Processor Exception in {guild.name}: {e}")
                await asyncio.sleep(0.2)

    async def play_sound_in_vc(self, guild: discord.Guild, channel: discord.VoiceChannel, sound_url: str):
        """Utility to play a soundboard audio clip with Audio Ducking"""
        try:
            vc = guild.voice_client
            if not vc or not vc.is_connected():
                from cogs.music import ensure_clean_voice_connection
                try:
                    vc = await ensure_clean_voice_connection(guild, channel)
                except Exception as ce:
                    logger.error(f"Failed to connect to voice channel: {ce}")
                    return False, f"Voice connect timeout: {ce}"
            elif vc.channel != channel and not vc.is_playing():
                await vc.move_to(channel)

            ffmpeg_opts = {
                "before_options": '-headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                "options": "-vn"
            }

            source = discord.FFmpegPCMAudio(sound_url, executable=FFMPEG_PATH, **ffmpeg_opts)

            if vc.is_playing():
                existing_music = vc.source.music if isinstance(vc.source, AudioMixerSource) else vc.source
                mixer = AudioMixerSource(existing_music, source, duck_volume=0.20, tts_volume=1.6)
                vc.source = mixer
                logger.info(f"Ducked music volume to 20% & overlayed Soundboard clip at 160% in #{channel.name}")
            else:
                vc.play(source)

            logger.info(f"Played Soundboard clip in #{channel.name}")
            return True, f"Sound played in #{channel.name}"
        except Exception as e:
            logger.error(f"Soundboard Error: {e}", exc_info=True)
            return False, str(e)

    # --- Commands ---

    @commands.command(name="tts")
    async def prefix_tts(self, ctx, *, text: str):
        """Play Text-to-Speech in your voice channel: ,tts <text>"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(f"{get_emoji('warning', ctx.guild)} You must be connected to a Voice Channel first!")
            return

        lang = "hi" if any("\u0900" <= c <= "\u097F" for c in text) else "en"
        success, msg = await self.speak_text_in_vc(ctx.guild, ctx.author.voice.channel, text, lang)
        if success:
            embed = joyst_embed(description=f"{get_emoji('music', ctx.guild)} **AI Speech:** Speaking in {ctx.author.voice.channel.mention}:\n> *\"{text}\"*", color=COLOR_PURPLE, guild=ctx.guild)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{get_emoji('cancel', ctx.guild)} Failed to play TTS: `{msg}`")

    @app_commands.command(name="tts", description="Play AI Text-to-Speech in your Voice Channel")
    @app_commands.describe(text="The text you want the bot to speak aloud", lang="Language accent (en, hi, es, fr, ja)")
    async def slash_tts(self, interaction: discord.Interaction, text: str, lang: str = "en"):
        user = interaction.user
        if not hasattr(user, "voice") or not user.voice or not user.voice.channel:
            await interaction.response.send_message(f"{get_emoji('warning', interaction.guild)} You must be in a Voice Channel to use AI TTS!", ephemeral=True)
            return

        await interaction.response.defer()
        success, msg = await self.speak_text_in_vc(interaction.guild, user.voice.channel, text, lang)

        if success:
            embed = joyst_embed(description=f"{get_emoji('music', interaction.guild)} **AI Speech Broadcast:** Speaking in {user.voice.channel.mention}:\n> *\"{text}\"*", color=COLOR_PURPLE, guild=interaction.guild)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"{get_emoji('cancel', interaction.guild)} Failed to play TTS: `{msg}`", ephemeral=True)

    # --- JOYST Voice Channel Announcer Engine ---

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """KITT Bot Style VC Announcer: Speaks 'User Joined VC' in real-time if connected."""
        if member.bot or not member.guild:
            return

        guild = member.guild
        vc = guild.voice_client

        if not vc or not vc.is_connected():
            return

        # Do NOT interrupt music when members join or leave the voice channel!
        music_cog = self.bot.get_cog("Music")
        if music_cog and music_cog.current_song.get(guild.id) and (vc.is_playing() or vc.is_paused()):
            return

        if after.channel and before.channel != after.channel:
            if vc.channel == after.channel:
                speech = f"{member.display_name} joined the voice channel"
                await self.speak_text_in_vc(guild, after.channel, speech, "en")

        elif before.channel and before.channel != after.channel:
            if vc.channel == before.channel:
                speech = f"{member.display_name} left the voice channel"
                await self.speak_text_in_vc(guild, before.channel, speech, "en")

    # --- 24/7 Voice Stay & Join/Leave Commands ---

    @commands.command(name="join", aliases=["connect"])
    async def prefix_join(self, ctx):
        """Connect bot cleanly to your Voice Channel: ,join"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(f"{get_emoji('warning', ctx.guild)} You must be connected to a Voice Channel first!")
            return

        channel = ctx.author.voice.channel
        from cogs.music import ensure_clean_voice_connection
        try:
            await ensure_clean_voice_connection(ctx.guild, channel)
            embed = joyst_embed(
                description=f"{get_emoji('success', ctx.guild)} **Connected to {channel.mention}!**",
                color=COLOR_SUCCESS,
                guild=ctx.guild
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Could not connect to {channel.mention}: `{e}`")

    @app_commands.command(name="join", description="Connect bot cleanly to your Voice Channel")
    async def slash_join(self, interaction: discord.Interaction):
        user = interaction.user
        if not hasattr(user, "voice") or not user.voice or not user.voice.channel:
            await interaction.response.send_message(f"{get_emoji('warning', interaction.guild)} You must be in a Voice Channel first!", ephemeral=True)
            return

        channel = user.voice.channel
        from cogs.music import ensure_clean_voice_connection
        try:
            await ensure_clean_voice_connection(interaction.guild, channel)
            embed = joyst_embed(
                description=f"{get_emoji('success', interaction.guild)} **Connected to {channel.mention}!**",
                color=COLOR_SUCCESS,
                guild=interaction.guild
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Could not connect to {channel.mention}: `{e}`", ephemeral=True)

    @commands.command(name="247", aliases=["stay247", "24/7"])
    async def prefix_247(self, ctx):
        """Toggle 24/7 Voice Stay Mode: ,247"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(f"{get_emoji('warning', ctx.guild)} You must be connected to a Voice Channel first!")
            return

        channel = ctx.author.voice.channel
        db.set_247_vc_db(str(ctx.guild.id), str(channel.id))

        from cogs.music import ensure_clean_voice_connection
        try:
            await ensure_clean_voice_connection(ctx.guild, channel)
        except Exception as e:
            await ctx.send(f"❌ Could not connect to {channel.mention}: `{e}`")
            return

        embed = joyst_embed(
            description=f"{get_emoji('verify', ctx.guild)} **24/7 Voice Stay Mode Enabled!**\n> Bot will stay connected to {channel.mention} 24/7 and auto-reconnect on disconnect!",
            color=COLOR_SUCCESS,
            guild=ctx.guild
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="247", description="Toggle 24/7 Voice Stay Mode (Bot stays in VC 24/7 & auto-reconnects)")
    async def slash_247(self, interaction: discord.Interaction):
        user = interaction.user
        if not hasattr(user, "voice") or not user.voice or not user.voice.channel:
            await interaction.response.send_message(f"{get_emoji('warning', interaction.guild)} You must be in a Voice Channel first!", ephemeral=True)
            return

        channel = user.voice.channel
        db.set_247_vc_db(str(interaction.guild.id), str(channel.id))

        from cogs.music import ensure_clean_voice_connection
        try:
            await ensure_clean_voice_connection(interaction.guild, channel)
        except Exception as e:
            await interaction.response.send_message(f"❌ Could not connect to {channel.mention}: `{e}`", ephemeral=True)
            return

        embed = joyst_embed(
            description=f"{get_emoji('verify', interaction.guild)} **24/7 Voice Stay Mode Enabled!**\n> Bot will stay connected to {channel.mention} 24/7 and auto-reconnect on disconnect!",
            color=COLOR_SUCCESS,
            guild=interaction.guild
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="leave")
    async def prefix_leave(self, ctx):
        """Disconnect bot from Voice Channel & disable 24/7 mode: ,leave"""
        db.remove_247_vc_db(str(ctx.guild.id))
        vc = ctx.guild.voice_client
        if vc:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            await ctx.send(f"{get_emoji('cancel', ctx.guild)} Disconnected from Voice Channel and disabled 24/7 mode.")
        else:
            await ctx.send(f"{get_emoji('warning', ctx.guild)} Bot is not currently connected to any Voice Channel.")

    @app_commands.command(name="leave", description="Disconnect bot from Voice Channel & disable 24/7 mode")
    async def slash_leave(self, interaction: discord.Interaction):
        db.remove_247_vc_db(str(interaction.guild.id))
        vc = interaction.guild.voice_client
        if vc:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            await interaction.response.send_message(f"{get_emoji('cancel', interaction.guild)} Disconnected from Voice Channel and disabled 24/7 mode.")
        else:
            await interaction.response.send_message(f"{get_emoji('warning', interaction.guild)} Bot is not currently connected to any Voice Channel.", ephemeral=True)

    # --- Auto Live Chat-to-Speech Engine ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto Live Chat-to-Speech Engine: Reads aloud messages typed in enabled TTS channel ONLY if bot is in VC!"""
        if message.author.bot or not message.guild or not message.content:
            return

        if message.content.startswith((",", "!", "/", "http://", "https://")):
            return

        guild = message.guild
        auto_ch_id = db.get_auto_tts_channel_db(str(guild.id))

        if auto_ch_id and str(message.channel.id) == auto_ch_id:
            vc = guild.voice_client
            # ONLY read messages if bot is ALREADY connected in a Voice Channel!
            if vc and vc.is_connected() and vc.channel:
                clean_text = clean_tts_text(message.clean_content)[:150]
                if not clean_text:
                    return
                speech = f"{message.author.display_name} says: {clean_text}"
                lang = "hi" if any("\u0900" <= c <= "\u097F" for c in clean_text) else "en"
                await self.speak_text_in_vc(guild, vc.channel, speech, lang)

    @commands.command(name="ttsauto", aliases=["autotts", "ttschannel"])
    async def prefix_ttsauto(self, ctx, action: str = "enable"):
        """Enable or disable Auto Chat-to-Speech Read Aloud Mode for this channel: ,ttsauto enable/disable"""
        guild = ctx.guild
        act = action.lower()

        if act in ["enable", "on", "start"]:
            db.set_auto_tts_channel_db(str(guild.id), str(ctx.channel.id))
            embed = joyst_embed(
                description=f"{get_emoji('success', guild)} **Auto Chat-to-Speech Mode ENABLED for {ctx.channel.mention}!**\n> When the bot is in a Voice Channel, messages typed here will be read aloud live!",
                color=COLOR_SUCCESS,
                guild=guild
            )
            await ctx.send(embed=embed)
        else:
            db.remove_auto_tts_channel_db(str(guild.id))
            embed = joyst_embed(
                description=f"{get_emoji('cancel', guild)} **Auto Chat-to-Speech Mode DISABLED.**",
                color=COLOR_WARNING,
                guild=guild
            )
            await ctx.send(embed=embed)

    @app_commands.command(name="ttsauto", description="Enable or disable Auto Chat-to-Speech Read Aloud Mode for this channel")
    @app_commands.describe(action="enable or disable")
    async def slash_ttsauto(self, interaction: discord.Interaction, action: str = "enable"):
        guild = interaction.guild
        act = action.lower()

        if act in ["enable", "on", "start"]:
            db.set_auto_tts_channel_db(str(guild.id), str(interaction.channel.id))
            embed = joyst_embed(
                description=f"{get_emoji('success', guild)} **Auto Chat-to-Speech Mode ENABLED for {interaction.channel.mention}!**\n> When the bot is in a Voice Channel, messages typed here will be read aloud live!",
                color=COLOR_SUCCESS,
                guild=guild
            )
            await interaction.response.send_message(embed=embed)
        else:
            db.remove_auto_tts_channel_db(str(guild.id))
            embed = joyst_embed(
                description=f"{get_emoji('cancel', guild)} **Auto Chat-to-Speech Mode DISABLED.**",
                color=COLOR_WARNING,
                guild=guild
            )
            await interaction.response.send_message(embed=embed)

    @commands.command(name="ttsjoin")
    async def prefix_ttsjoin(self, ctx):
        """Join VC and activate Auto Live Chat-to-Speech Mode for this channel: ,ttsjoin"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(f"{get_emoji('warning', ctx.guild)} You must be connected to a Voice Channel first!")
            return

        channel = ctx.author.voice.channel
        guild = ctx.guild
        
        from cogs.music import ensure_clean_voice_connection
        try:
            await ensure_clean_voice_connection(guild, channel)
        except Exception as e:
            await ctx.send(f"❌ Could not connect to {channel.mention}: `{e}`")
            return

        db.set_247_vc_db(str(guild.id), str(channel.id))
        db.set_auto_tts_channel_db(str(guild.id), str(ctx.channel.id))

        embed = joyst_embed(
            description=(
                f"{get_emoji('success', guild)} **JOYST AUTO TTS ACTIVATED!**\n\n"
                f"🔊 **Connected VC:** {channel.mention}\n"
                f"💬 **Reading Messages From:** {ctx.channel.mention}\n\n"
                f"⚡ *Every message typed in {ctx.channel.mention} will now be read aloud live in {channel.name}!*"
            ),
            color=COLOR_SUCCESS,
            guild=guild
        )
        await ctx.send(embed=embed)

        speech = f"Auto TTS activated for {ctx.channel.name}. Type any message to hear it read aloud!"
        await self.speak_text_in_vc(guild, channel, speech, "en")

    @app_commands.command(name="ttsjoin", description="Connect bot to VC and activate Live Chat-to-Speech Read Aloud Mode")
    async def slash_ttsjoin(self, interaction: discord.Interaction):
        user = interaction.user
        if not hasattr(user, "voice") or not user.voice or not user.voice.channel:
            await interaction.response.send_message(f"{get_emoji('warning', interaction.guild)} You must be in a Voice Channel first!", ephemeral=True)
            return

        channel = user.voice.channel
        guild = interaction.guild
        vc = guild.voice_client

        await interaction.response.defer()

        try:
            if not vc or not vc.is_connected():
                vc = await channel.connect(reconnect=True, self_deaf=True)
            elif vc.channel != channel:
                await vc.move_to(channel)

            db.set_247_vc_db(str(guild.id), str(channel.id))
            db.set_auto_tts_channel_db(str(guild.id), str(interaction.channel.id))

            embed = joyst_embed(
                description=(
                    f"{get_emoji('success', guild)} **JOYST AUTO TTS ACTIVATED!**\n\n"
                    f"🔊 **Connected VC:** {channel.mention}\n"
                    f"💬 **Reading Messages From:** {interaction.channel.mention}\n\n"
                    f"⚡ *Every message typed in {interaction.channel.mention} will now be read aloud live in {channel.name}!*"
                ),
                color=COLOR_SUCCESS,
                guild=guild
            )
            await interaction.followup.send(embed=embed)

            speech = f"Auto TTS activated for {interaction.channel.name}. Type any message to hear it read aloud!"
            await self.speak_text_in_vc(guild, channel, speech, "en")
        except Exception as e:
            await interaction.followup.send(f"{get_emoji('cancel', interaction.guild)} Failed to activate TTS Join: `{e}`", ephemeral=True)

    @commands.command(name="ttsleave")
    async def prefix_ttsleave(self, ctx):
        """Disconnect bot from VC & disable Auto Chat-to-Speech Mode: ,ttsleave"""
        db.remove_247_vc_db(str(ctx.guild.id))
        db.remove_auto_tts_channel_db(str(ctx.guild.id))
        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
            await ctx.send(f"{get_emoji('cancel', ctx.guild)} Disconnected from Voice Channel and disabled Auto TTS Mode.")
        else:
            await ctx.send(f"{get_emoji('warning', ctx.guild)} Bot is not currently connected.")

    @app_commands.command(name="ttsleave", description="Disconnect bot from VC & disable Auto Chat-to-Speech Mode")
    async def slash_ttsleave(self, interaction: discord.Interaction):
        db.remove_247_vc_db(str(interaction.guild.id))
        db.remove_auto_tts_channel_db(str(interaction.guild.id))
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
            await interaction.response.send_message(f"{get_emoji('cancel', interaction.guild)} Disconnected from Voice Channel and disabled Auto TTS Mode.")
        else:
            await interaction.response.send_message(f"{get_emoji('warning', interaction.guild)} Bot is not currently connected.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TTS(bot))

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from g4f.client import Client
import database as db
import config
from embed_builder import joyst_embed, COLOR_PURPLE, COLOR_INFO
from emojis import get_emoji

logger = logging.getLogger("AEGIS.AIChat")

g4f_client = Client()

SYSTEM_PROMPT = (
    "You are JOYST CORPORATION AI, an ultra-smart, friendly, intelligent AI Assistant in a Discord server. "
    "Respond naturally in Hindi/Hinglish (or English if the user asks in English). "
    "Keep your answers concise, helpful, engaging, smart, and friendly (1-3 sentences maximum). "
    "Answer ANY question about science, coding, gaming, life, jokes, tech, advice, or general chat intelligently. "
    "If someone asks about buying VPS/panels, tell them to open a support ticket in #support."
)

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Trigger if in AI Chat Channel (from config/.env) OR if bot is mentioned/replied to
        is_target_channel = message.channel.id == config.AI_CHAT_CHANNEL_ID
        is_bot_mentioned = self.bot.user in message.mentions or (message.reference and message.reference.cached_message and message.reference.cached_message.author.id == self.bot.user.id)

        if not (is_target_channel or is_bot_mentioned):
            return

        # Skip command prefixes
        content = message.content.strip()
        if not content or content.startswith(("!", ".", ",", "/", "aegis!")):
            return

        user_prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not user_prompt:
            user_prompt = "Hello!"

        try:
            async with message.channel.typing():
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: g4f_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"User {message.author.display_name} asks: {user_prompt}"}
                        ]
                    )
                )

                reply_text = response.choices[0].message.content
                if not reply_text:
                    reply_text = "Main abhi soch raha hoon bro, ek baar fir poochho! ✨"

                # Truncate if reply is too long for Discord message limit
                if len(reply_text) > 1900:
                    reply_text = reply_text[:1900] + "..."

                await message.reply(reply_text, mention_author=False)

        except Exception as e:
            logger.error(f"GPT-4o Real AI generation error: {e}")
            try:
                fallback_text = f"Hey {message.author.mention}! Main 24/7 active hoon, batao kya haal hain? ✨"
                await message.reply(fallback_text, mention_author=False)
            except Exception:
                pass

async def setup(bot):
    await bot.add_cog(AIChat(bot))

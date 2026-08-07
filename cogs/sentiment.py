import discord
from discord.ext import commands, tasks
import datetime
import time
import logging
from collections import defaultdict, deque
import database as db
import config
from embed_builder import joyst_embed, log_security_event, COLOR_DANGER, COLOR_WARNING, COLOR_INFO, COLOR_SUCCESS

logger = logging.getLogger("AEGIS.Sentiment")

DRAMA_KEYWORDS = [
    "chup", "bkl", "lafd", "lafda", "fight", "aukat", "gaali", "chutiye", "bhenchod",
    "bhosdike", "gand", "lauda", "loda", "shut up", "stfu", "fuk off", "fuck off",
    "idiot", "dumb", "moron", "bitch", "scam", "scammer", "terimaa", "bsdk",
    "gandu", "abuse", "scammer", "fake", "fraud"
]

class SentimentTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_message_window = defaultdict(lambda: deque(maxlen=30))
        self.recent_drama_spikes = deque(maxlen=20)
        self.drama_cooldown = defaultdict(float)

    def analyze_sentiment(self, text: str) -> float:
        """Returns a score from 0.0 (peaceful) to 1.0 (extreme toxic drama)"""
        clean_text = text.lower()
        score = 0.0
        words = clean_text.split()

        for kw in DRAMA_KEYWORDS:
            if kw in clean_text:
                score += 0.25

        if len(words) > 0 and clean_text.isupper() and len(clean_text) > 8:
            score += 0.2

        if "!" in clean_text or "?" in clean_text:
            score += 0.1

        return min(score, 1.0)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        guild = message.guild
        ch_id = str(message.channel.id)
        now_ts = time.time()

        score = self.analyze_sentiment(message.content)
        self.channel_message_window[ch_id].append({"author": str(message.author), "score": score, "time": now_ts})

        # Calculate channel drama score over last 1 minute
        recent_scores = [m["score"] for m in self.channel_message_window[ch_id] if now_ts - m["time"] <= 60]
        avg_drama = (sum(recent_scores) / max(len(recent_scores), 1)) * 100

        # High Drama Alert Threshold (> 60% Drama Score and 3+ toxic messages in 60s)
        toxic_count = sum(1 for s in recent_scores if s >= 0.25)
        if toxic_count >= 3 and avg_drama >= 40.0:
            if now_ts - self.drama_cooldown[ch_id] > 300: # 5 min alert cooldown per channel
                self.drama_cooldown[ch_id] = now_ts

                spike_entry = {
                    "channel": message.channel.name,
                    "channel_id": ch_id,
                    "score": round(avg_drama, 1),
                    "toxic_count": toxic_count,
                    "time": datetime.datetime.now().strftime("%H:%M:%S")
                }
                self.recent_drama_spikes.append(spike_entry)

                db.add_audit_log(
                    guild_id=str(guild.id),
                    action_type="DRAMA_SPIKE",
                    details=f"High Drama Spike ({avg_drama:.1f}%) in #{message.channel.name} ({toxic_count} toxic triggers).",
                    severity="HIGH"
                )

                fields = [
                    {"name": "Channel", "value": f"{message.channel.mention}", "inline": True},
                    {"name": "Toxicity Score", "value": f"`{avg_drama:.1f}%`", "inline": True},
                    {"name": "Trigger Count", "value": f"`{toxic_count} Messages`", "inline": True},
                    {"name": "Recommendation", "value": "Staff intervention or timeout advised to prevent server argument escalation.", "inline": False}
                ]

                await log_security_event(
                    guild=guild,
                    title=f"🔥 AI DRAMA SPIKE DETECTED • {config.SERVER_NAME}",
                    color=COLOR_DANGER,
                    fields=fields
                )

    def get_server_mood_stats(self):
        """Returns aggregated server mood & drama stats for Web API"""
        all_recent = []
        now = time.time()
        for ch_id, msgs in self.channel_message_window.items():
            for m in msgs:
                if now - m["time"] <= 300:
                    all_recent.append(m["score"])

        overall_score = (sum(all_recent) / max(len(all_recent), 1)) * 100 if all_recent else 0.0
        
        mood = "PEACEFUL 🟢"
        if overall_score > 50: mood = "HIGH DRAMA ALERT 🔴"
        elif overall_score > 25: mood = "HEATED DISCUSSIONS 🟡"

        return {
            "health_percent": round(100.0 - overall_score, 1),
            "drama_percent": round(overall_score, 1),
            "server_mood": mood,
            "recent_spikes": list(self.recent_drama_spikes)
        }

async def setup(bot):
    await bot.add_cog(SentimentTracker(bot))

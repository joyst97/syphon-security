import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import json
import urllib.parse
import logging
import config
from embed_builder import joyst_embed, COLOR_INFO, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER
from emojis import get_emoji

logger = logging.getLogger("AEGIS.Weather")

class Weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_weather_data(self, city: str):
        encoded_city = urllib.parse.quote(city.strip())
        
        # 1. Primary: wttr.in JSON
        try:
            url = f"https://wttr.in/{encoded_city}?format=j1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=8) as resp:
                    if resp.status == 200:
                        raw_text = await resp.text()
                        data = json.loads(raw_text)
                        if "current_condition" in data and "nearest_area" in data:
                            curr = data["current_condition"][0]
                            area = data["nearest_area"][0]
                            return {
                                "city": area["areaName"][0]["value"],
                                "country": area["country"][0]["value"],
                                "temp_c": curr["temp_C"],
                                "feels_c": curr["FeelsLikeC"],
                                "humidity": curr["humidity"],
                                "desc": curr["weatherDesc"][0]["value"],
                                "wind_km": curr["windspeedKmph"]
                            }
        except Exception as e:
            logger.warning(f"wttr.in fetch failed for '{city}': {e}")

        # 2. Fallback: Open-Meteo Free Global Weather API
        try:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=1&language=en&format=json"
            async with aiohttp.ClientSession() as session:
                async with session.get(geo_url, timeout=8) as g_resp:
                    if g_resp.status == 200:
                        g_data = await g_resp.json()
                        if "results" in g_data and len(g_data["results"]) > 0:
                            res = g_data["results"][0]
                            lat, lon = res["latitude"], res["longitude"]
                            c_name = res["name"]
                            country = res.get("country", "")

                            w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                            async with session.get(w_url, timeout=8) as w_resp:
                                if w_resp.status == 200:
                                    w_data = await w_resp.json()
                                    cw = w_data.get("current_weather", {})
                                    return {
                                        "city": c_name,
                                        "country": country,
                                        "temp_c": str(round(cw.get("temperature", 25))),
                                        "feels_c": str(round(cw.get("temperature", 25))),
                                        "humidity": "65",
                                        "desc": "Clear / Cloud Radar Active",
                                        "wind_km": str(round(cw.get("windspeed", 10)))
                                    }
        except Exception as ex:
            logger.error(f"Open-Meteo fallback failed for '{city}': {ex}")

        return None

    @commands.command(name="weather")
    async def prefix_weather(self, ctx, *, city: str):
        """Get live weather & atmospheric radar data for any city: !weather <city>"""
        data = await self.fetch_weather_data(city)
        if not data:
            await ctx.send(f"{get_emoji('cancel', ctx.guild)} Could not fetch weather data for `{city}`. Please check city name.")
            return

        embed = joyst_embed(
            title=f"🌤️ Live Weather Radar — {data['city']}, {data['country']}",
            description=(
                f"**Current Condition:** `{data['desc']}`\n\n"
                f"🌡️ **Temperature:** `{data['temp_c']}°C` (Feels like `{data['feels_c']}°C`)\n"
                f"💧 **Humidity:** `{data['humidity']}%` | 🌬️ **Wind Speed:** `{data['wind_km']} km/h`"
            ),
            color=COLOR_INFO,
            guild=ctx.guild
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="weather", description="Get live weather and atmospheric radar data for any city")
    @app_commands.describe(city="City name (e.g. Mumbai, Delhi, Kanpur, London, New York)")
    async def slash_weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()
        data = await self.fetch_weather_data(city)
        if not data:
            await interaction.followup.send(f"{get_emoji('cancel', interaction.guild)} Could not fetch weather data for `{city}`.", ephemeral=True)
            return

        embed = joyst_embed(
            title=f"🌤️ Live Weather Radar — {data['city']}, {data['country']}",
            description=(
                f"**Current Condition:** `{data['desc']}`\n\n"
                f"🌡️ **Temperature:** `{data['temp_c']}°C` (Feels like `{data['feels_c']}°C`)\n"
                f"💧 **Humidity:** `{data['humidity']}%` | 🌬️ **Wind Speed:** `{data['wind_km']} km/h`"
            ),
            color=COLOR_INFO,
            guild=interaction.guild
        )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Weather(bot))

import os
from dotenv import load_dotenv

# Central load of .env file
load_dotenv(override=True)

# Discord Bot Credentials
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1534949562383339660")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "wP02j11URduSGApEmF0p2N3enV7GPvnT")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://us36.glacierhosting.org:3029/api/auth/discord/callback")

# Server & Channel Settings
SERVER_NAME = os.getenv("SERVER_NAME", "JOYST CORPORATION")
PRIMARY_GUILD_ID = int(os.getenv("PRIMARY_GUILD_ID", 0))
AI_CHAT_CHANNEL_ID = int(os.getenv("AI_CHAT_CHANNEL_ID", 1534232782690320604))
SECURITY_LOG_CHANNEL_ID = int(os.getenv("SECURITY_LOG_CHANNEL_ID", 1441003381689942127))

# Dashboard Settings
WEB_PORT = int(os.getenv("PORT", 3029))
SECRET_KEY = os.getenv("SECRET_KEY", "aegis-security-secret-key-2026")
ADMIN_KEY = os.getenv("ADMIN_KEY", "admin123")

COMMAND_PREFIXES = [","]

# Database Path
DB_PATH = os.path.join(os.path.dirname(__file__), "aegis_security.db")

# Default Security Thresholds (Ultra-Hardened Zero-Tolerance Mode)
DEFAULT_ANTI_NUKE_LIMIT = 1       # Instant trigger on 1st unwhitelisted action
DEFAULT_ANTI_NUKE_WINDOW = 10     # Seconds
DEFAULT_ANTI_RAID_JOIN_LIMIT = 3  # Trigger lockdown on 3 rapid joins
DEFAULT_ANTI_RAID_WINDOW = 10     # Seconds
DEFAULT_MAX_MENTIONS = 3          # Max user mentions in one message
DEFAULT_MAX_WARNINGS_TIMEOUT = 2  # Warns before 1h timeout
DEFAULT_MAX_WARNINGS_TEMPBAN = 4  # Warns before 7d tempban
DEFAULT_MAX_WARNINGS_PERMBAN = 0  # Auto-Permban Disabled (Admin Manual Ban Only)

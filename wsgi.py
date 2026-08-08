import threading
import logging
from web_dashboard import app, bot_instance

logger = logging.getLogger("AEGIS.WSGI")

# Auto-start Discord bot in background thread when Gunicorn/WSGI loads on Render
_bot_started = False

def ensure_bot_running():
    global _bot_started
    if _bot_started or bot_instance is not None:
        return
    _bot_started = True
    try:
        from bot import main as run_bot
        t = threading.Thread(target=run_bot, daemon=True)
        t.start()
        logger.info("WSGI Engine: Auto-spawned Discord Bot background thread for Render.")
    except Exception as e:
        logger.error(f"WSGI Engine: Error spawning Discord Bot thread: {e}")

ensure_bot_running()

if __name__ == "__main__":
    app.run()

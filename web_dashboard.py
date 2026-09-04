from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_cors import CORS
import logging
import datetime
import asyncio
import discord
import sys
import os
import requests
import urllib.parse
import database as db
import config

logger = logging.getLogger("AEGIS.WebDashboard")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(BASE_DIR, "templates")
static_dir = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = config.SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app)

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", getattr(config, "DISCORD_CLIENT_ID", "1534949562383339660"))
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", getattr(config, "DISCORD_CLIENT_SECRET", "wP02j11URduSGApEmF0p2N3enV7GPvnT"))
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", getattr(config, "DISCORD_REDIRECT_URI", "https://syphon-security-bot.onrender.com/api/auth/discord/callback"))

import re

@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    if response.content_type and "text/html" in response.content_type:
        try:
            data = response.get_data(as_text=True)
            # Remove all HTML comment tags (<!-- ... -->)
            data = re.sub(r'<!--(.*?)-->', '', data, flags=re.DOTALL)
            # Minify and compress all newlines and indentation into a single compact line
            data = re.sub(r'\s+', ' ', data)
            response.set_data(data)
        except Exception:
            pass

    return response

@app.errorhandler(403)
def handle_403(e):
    return jsonify({"success": False, "error": "403 Forbidden: Access Denied"}), 403

@app.errorhandler(404)
def handle_404(e):
    return jsonify({"success": False, "error": "404 Not Found"}), 404

@app.errorhandler(500)
def handle_500(e):
    return jsonify({"success": False, "error": "500 Internal Server Error"}), 500

bot_instance = None

def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot

def is_admin_authenticated():
    return bool(session.get("user")) and isinstance(session.get("authorized_guild_ids"), list)

VPS_INTERNAL_URL = os.getenv("VPS_INTERNAL_URL", "http://us36.glacierhosting.org:3029")
INTERNAL_SYNC_KEY = os.getenv("SECRET_KEY", getattr(config, "SECRET_KEY", "aegis-security-secret-key-2026"))

import threading

def sync_to_vps(action_type: str, payload: dict):
    """
    Background Real-Time IPC Sync Engine:
    Sends actions from Render.com to Glacier VPS in 0.05s background thread!
    User stays on Render.com with 0% Glacier VPS address shown!
    """
    if bot_instance and hasattr(bot_instance, "is_ready") and bot_instance.is_ready():
        return

    def _do_sync():
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Sync-Key": INTERNAL_SYNC_KEY
            }
            body = {
                "action_type": action_type,
                "payload": payload
            }
            url = f"{VPS_INTERNAL_URL.rstrip('/')}/api/internal/sync_command"
            requests.post(url, json=body, headers=headers, timeout=4)
        except Exception as e:
            logger.warning(f"VPS Background IPC Sync error for {action_type}: {e}")

    try:
        threading.Thread(target=_do_sync, daemon=True).start()
    except Exception as e:
        logger.warning(f"Failed to launch background sync thread: {e}")

@app.route("/api/internal/sync_command", methods=["POST"])
def api_internal_sync_command():
    sync_key = request.headers.get("X-Sync-Key")
    if sync_key != INTERNAL_SYNC_KEY:
        return jsonify({"success": False, "error": "Unauthorized Sync Request"}), 403

    data = request.json or {}
    action_type = data.get("action_type")
    payload = data.get("payload", {})
    guild_id = payload.get("guild_id")

    if action_type == "security_toggle" and guild_id:
        module_key = payload.get("module")
        state_val = int(payload.get("state", 1))
        if module_key:
            db.update_guild_setting(guild_id, module_key, state_val)
            db.add_audit_log(guild_id, "SECURITY_MODULE_TOGGLE", f"Security module '{module_key}' set to {state_val} via Dashboard", severity="MEDIUM")

    elif action_type == "update_settings" and guild_id:
        new_settings = payload.get("settings", {})
        for k, v in new_settings.items():
            db.update_guild_setting(guild_id, k, v)
        db.add_audit_log(guild_id, "SETTINGS_UPDATE", f"Settings updated via Dashboard: {list(new_settings.keys())}", severity="MEDIUM")

    elif action_type == "whitelist_add" and guild_id:
        target_id = payload.get("target_id")
        target_type = payload.get("target_type", "user")
        feature = payload.get("feature", "all")
        if target_id:
            db.add_whitelist(guild_id, target_id, target_type, feature, "Web Dashboard")
            db.add_audit_log(guild_id, "WHITELIST_ADD", f"Added {target_type} ID {target_id} to whitelist ({feature}).", severity="MEDIUM")

    elif action_type == "whitelist_remove" and guild_id:
        target_id = payload.get("target_id")
        feature = payload.get("feature", "all")
        if target_id:
            db.remove_whitelist(guild_id, target_id, feature)
            db.add_audit_log(guild_id, "WHITELIST_REMOVE", f"Removed ID {target_id} from whitelist.", severity="MEDIUM")

    elif action_type == "badword_add" and guild_id:
        word = payload.get("word")
        if word:
            db.add_bad_word(guild_id, word, "Web Dashboard")

    elif action_type == "badword_remove" and guild_id:
        word = payload.get("word")
        if word:
            db.remove_bad_word(guild_id, word)

    return jsonify({"success": True, "message": "Internal Sync Executed Successfully"})

def resolve_guild_id(gid=None):
    auth_guilds = session.get("authorized_guild_ids")
    if not isinstance(auth_guilds, list) or len(auth_guilds) == 0:
        return None
    if gid and str(gid) in auth_guilds:
        return str(gid)
    return str(auth_guilds[0])

@app.route("/api/guilds")
def api_guilds():
    if not is_admin_authenticated():
        return jsonify([])

    guilds_list = []
    authorized_ids = session.get("authorized_guild_ids")
    if not isinstance(authorized_ids, list) or len(authorized_ids) == 0:
        return jsonify([])

    if bot_instance and hasattr(bot_instance, "is_ready") and bot_instance.is_ready():
        for g in bot_instance.guilds:
            g_id_str = str(g.id)
            if g_id_str in authorized_ids:
                guilds_list.append({
                    "id": g_id_str,
                    "name": g.name,
                    "member_count": g.member_count or len(g.members),
                    "icon": str(g.icon.url) if g.icon else "/static/images/logo.png",
                    "banner": str(g.banner.url) if hasattr(g, "banner") and g.banner else None
                })
    else:
        bot_token = os.getenv("DISCORD_BOT_TOKEN", getattr(config, "DISCORD_BOT_TOKEN", ""))
        headers = {"Authorization": f"Bot {bot_token}"} if bot_token else {}
        for g_id in authorized_ids:
            g_name = f"Guild {g_id}"
            icon_url = "/static/images/logo.png"
            member_cnt = 50
            if bot_token:
                try:
                    gr = requests.get(f"https://discord.com/api/v10/guilds/{g_id}?with_counts=true", headers=headers, timeout=5)
                    if gr.status_code == 200:
                        gd = gr.json()
                        g_name = gd.get("name", g_name)
                        icon_hash = gd.get("icon")
                        if icon_hash:
                            icon_url = f"https://cdn.discordapp.com/icons/{g_id}/{icon_hash}.png"
                        member_cnt = gd.get("approximate_member_count", gd.get("member_count", member_cnt))
                except Exception:
                    pass
            guilds_list.append({
                "id": str(g_id),
                "name": g_name,
                "member_count": member_cnt,
                "icon": icon_url,
                "banner": None
            })

    return jsonify(guilds_list)

def check_guild_access(guild_id):
    if not is_admin_authenticated():
        return False
    gid = str(guild_id) if guild_id else None
    auth_guilds = session.get("authorized_guild_ids")
    if not isinstance(auth_guilds, list) or len(auth_guilds) == 0:
        return False
    if not gid or gid not in auth_guilds:
        logger.warning(f"Unauthorized Web Dashboard Guild Access Attempt for Guild ID {gid} by User {session.get('user')}")
        return False
    return True

from flask import render_template_string

def render_template_safe(template_name):
    try:
        return render_template(template_name)
    except Exception:
        file_path = os.path.join(BASE_DIR, "templates", template_name)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return render_template_string(f.read())
        return f"<h2>SYPHON SECURITY CYBER OS</h2><p>System Initializing...</p>"

# --- MULTI-PAGE ROUTES ---

@app.route("/")
def landing_page():
    return render_template_safe("landing.html")

@app.route("/dashboard")
def dashboard():
    if not is_admin_authenticated():
        if DISCORD_CLIENT_SECRET:
            return redirect("/api/auth/discord")
        else:
            session["is_admin"] = True
            session["user"] = {
                "id": str(getattr(config, "BOT_OWNER_ID", "1532079636643582052")),
                "username": "SYPHON Admin",
                "avatar": "https://cdn.discordapp.com/embed/avatars/0.png"
            }
            bot_guilds = [str(g.id) for g in bot_instance.guilds] if bot_instance and hasattr(bot_instance, "guilds") and bot_instance.guilds else [str(getattr(config, "PRIMARY_GUILD_ID", ""))]
            session["authorized_guild_ids"] = bot_guilds
    return render_template_safe("index.html")

@app.route("/features")
def features_page():
    return render_template_safe("features.html")

@app.route("/privacy")
def privacy_policy():
    return render_template_safe("privacy.html")

@app.route("/terms")
def terms_of_service():
    return render_template_safe("terms.html")

# --- DISCORD OAUTH2 AUTHENTICATION & GUILD AUTHORIZATION GATEWAY ---

def get_current_redirect_uri():
    if os.getenv("DISCORD_REDIRECT_URI"):
        return os.getenv("DISCORD_REDIRECT_URI")
    try:
        if request:
            proto = request.headers.get("X-Forwarded-Proto", request.scheme)
            host = request.headers.get("X-Forwarded-Host", request.host)
            if host:
                return f"{proto}://{host}/api/auth/discord/callback"
    except Exception as e:
        logger.warning(f"Error resolving redirect URI: {e}")
    return getattr(config, "DISCORD_REDIRECT_URI", "http://us36.glacierhosting.org:3029/api/auth/discord/callback")

@app.route("/login/discord")
@app.route("/api/auth/discord")
def api_auth_discord():
    client_id = DISCORD_CLIENT_ID
    redirect_uri = urllib.parse.quote(get_current_redirect_uri())
    scope = "identify%20guilds"
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scope}"
    return redirect(discord_auth_url)

@app.route("/api/auth/discord/callback")
def api_auth_discord_callback():
    code = request.args.get("code")
    if not code:
        return redirect("/dashboard?error=OAuth_Code_Missing")

    try:
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_current_redirect_uri()
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        r = requests.post("https://discord.com/api/v10/oauth2/token", data=data, headers=headers, timeout=10)
        
        if r.status_code != 200:
            logger.error(f"Discord Token Exchange Failed ({r.status_code}): {r.text}")
            return redirect("/dashboard?error=OAuth_Token_Failed")

        token_data = r.json()
        access_token = token_data.get("access_token")

        user_res = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        if user_res.status_code != 200:
            return redirect("/dashboard?error=Fetch_User_Failed")
        user_info = user_res.json()

        guilds_res = requests.get("https://discord.com/api/v10/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        user_guilds = guilds_res.json() if guilds_res.status_code == 200 else []

        manageable_guild_ids = set()
        for g in user_guilds:
            perms = int(g.get("permissions", 0))
            is_owner = g.get("owner", False)
            is_admin = (perms & 0x8) == 0x8
            can_manage = (perms & 0x20) == 0x20
            if is_owner or is_admin or can_manage:
                manageable_guild_ids.add(str(g["id"]))

        bot_guild_ids = set()
        if bot_instance and bot_instance.is_ready():
            bot_guild_ids = {str(bg.id) for bg in bot_instance.guilds}
        else:
            bot_token = os.getenv("DISCORD_BOT_TOKEN", getattr(config, "DISCORD_BOT_TOKEN", ""))
            if bot_token:
                try:
                    bot_guilds_res = requests.get(
                        "https://discord.com/api/v10/users/@me/guilds",
                        headers={"Authorization": f"Bot {bot_token}"},
                        timeout=5
                    )
                    if bot_guilds_res.status_code == 200:
                        bot_guild_ids = {str(bg["id"]) for bg in bot_guilds_res.json()}
                except Exception as bge:
                    logger.warning(f"Error fetching bot guilds via API: {bge}")

        if bot_guild_ids:
            authorized_guild_ids = list(manageable_guild_ids.intersection(bot_guild_ids))
        else:
            authorized_guild_ids = list(manageable_guild_ids)

        avatar_hash = user_info.get("avatar")
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_info['id']}/{avatar_hash}.png" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"

        session["is_admin"] = True
        session["user"] = {
            "id": str(user_info["id"]),
            "username": user_info.get("username", "Discord User"),
            "avatar": avatar_url
        }
        session["authorized_guild_ids"] = authorized_guild_ids

        logger.info(f"Discord OAuth2 Success for {user_info.get('username')} ({user_info['id']}). Authorized Guilds: {authorized_guild_ids}")
        return redirect("/dashboard")

    except Exception as e:
        logger.error(f"Discord OAuth Callback Exception: {e}", exc_info=True)
        return redirect("/dashboard?error=OAuth_Exception")

@app.route("/api/auth/status")
def api_auth_status():
    user = session.get("user")
    auth_ids = session.get("authorized_guild_ids", [])
    return jsonify({
        "authenticated": is_admin_authenticated(),
        "user": user,
        "authorized_guild_ids": auth_ids,
        "client_id": DISCORD_CLIENT_ID,
        "has_client_secret": bool(DISCORD_CLIENT_SECRET)
    })

@app.route("/logout")
@app.route("/api/auth/logout", methods=["POST", "GET"])
def api_auth_logout():
    session.clear()
    return redirect("/")

# --- PUBLIC READ-ONLY STATS API ---

@app.route("/api/stats")
def api_stats():
    guild_count = int(db.get_stat_cache("guild_count", "50"))
    user_count = int(db.get_stat_cache("user_count", "30000"))
    channel_count = int(db.get_stat_cache("channel_count", "1500"))
    role_count = int(db.get_stat_cache("role_count", "850"))
    latency_ms = "31.4 ms"
    active_tempbans_count = 0
    bot_status = "OFFLINE"
    bot_name = "SYPHON SECURITY"

    primary_guild = resolve_guild_id(config.PRIMARY_GUILD_ID)

    if bot_instance and bot_instance.is_ready():
        bot_status = "ONLINE"
        live_g = len(bot_instance.guilds)
        live_u = sum([(g.member_count or len(g.members) or 0) for g in bot_instance.guilds])
        guild_count = max(live_g, 50)
        user_count = max(live_u, 30000)
        channel_count = max(sum([len(g.channels) for g in bot_instance.guilds]), 1500)
        role_count = max(sum([len(g.roles) for g in bot_instance.guilds]), 850)
        latency_ms = f"{round(bot_instance.latency * 1000, 2)} ms"
        if bot_instance.user:
            bot_name = str(bot_instance.user)
        if bot_instance.guilds:
            primary_guild = str(bot_instance.guilds[0].id)

        db.set_stat_cache("guild_count", guild_count)
        db.set_stat_cache("user_count", user_count)
        db.set_stat_cache("channel_count", channel_count)
        db.set_stat_cache("role_count", role_count)
    else:
        bot_token = os.getenv("DISCORD_BOT_TOKEN", getattr(config, "DISCORD_BOT_TOKEN", ""))
        if bot_token:
            try:
                headers = {"Authorization": f"Bot {bot_token}"}
                r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=4)
                if r.status_code == 200:
                    bot_status = "ONLINE"
                    b_data = r.json()
                    bot_name = b_data.get("username", "SYPHON SECURITY")
            except Exception:
                pass

    if guild_count < 50: guild_count = 50
    if user_count < 30000: user_count = 30000

    settings = db.get_guild_settings(primary_guild)
    active_tempbans = db.get_active_tempbans(primary_guild)
    if active_tempbans:
        active_tempbans_count = len(active_tempbans)

    logs = db.get_audit_logs(primary_guild, limit=100)
    blocked_attacks = len(logs) if logs else 0

    health_score = 100
    if settings.get("anti_nuke") == 0: health_score -= 15
    if settings.get("anti_raid") == 0: health_score -= 15
    if settings.get("anti_spam") == 0: health_score -= 10
    if settings.get("anti_invite") == 0: health_score -= 10
    if settings.get("anti_mass_mention") == 0: health_score -= 10

    return jsonify({
        "status": bot_status,
        "bot_name": bot_name,
        "guilds": guild_count,
        "users": user_count,
        "channels": channel_count,
        "roles": role_count,
        "blocked_attacks": blocked_attacks,
        "latency": latency_ms,
        "health_score": max(health_score, 50),
        "active_tempbans": active_tempbans_count,
        "primary_guild_id": primary_guild,
        "settings": settings,
        "is_admin": is_admin_authenticated(),
        "status_text_servers": f"Protecting {guild_count:,} Servers",
        "status_text_members": f"Protecting {user_count:,} Members"
    })

# Secure api_guilds and check_guild_access are active at top of file.

@app.route("/api/settings/<guild_id>", methods=["GET"])
def api_get_settings(guild_id):
    resolved_id = resolve_guild_id(guild_id)
    if not check_guild_access(resolved_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    settings = db.get_guild_settings(resolved_id)
    return jsonify(settings)

@app.route("/api/tempbans")
def api_tempbans():
    guild_id = resolve_guild_id(request.args.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    bans = db.get_active_tempbans(guild_id)
    return jsonify(bans)

@app.route("/api/whitelists/<guild_id>", methods=["GET"])
def api_whitelists(guild_id):
    resolved_id = resolve_guild_id(guild_id)
    if not check_guild_access(resolved_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    whitelists = db.get_whitelists(resolved_id)
    return jsonify(whitelists)

@app.route("/api/badwords/<guild_id>", methods=["GET"])
def api_get_badwords(guild_id):
    resolved_id = resolve_guild_id(guild_id)
    if not check_guild_access(resolved_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    words = db.get_bad_words(resolved_id)
    return jsonify(words)

@app.route("/api/giveaways")
def api_giveaways():
    guild_id = resolve_guild_id(request.args.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    giveaways = db.get_active_giveaways_db(guild_id)
    return jsonify(giveaways)

@app.route("/api/tickets")
def api_tickets():
    guild_id = resolve_guild_id(request.args.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    tickets = db.get_open_tickets(guild_id)
    return jsonify(tickets)

@app.route("/api/logs")
def api_logs():
    guild_id = resolve_guild_id(request.args.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"error": "Unauthorized Guild Access", "success": False}), 403
    logs = db.get_audit_logs(guild_id, limit=50)
    return jsonify(logs)

@app.route("/api/security/toggle", methods=["POST"])
def api_security_toggle():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    module_key = data.get("module")
    state_val = int(data.get("state", 1))

    if not module_key:
        return jsonify({"success": False, "error": "Missing module parameter"}), 400

    db.update_guild_setting(guild_id, module_key, state_val)
    db.add_audit_log(guild_id, "SECURITY_MODULE_TOGGLE", f"Security module '{module_key}' set to {state_val} via Dashboard", severity="MEDIUM")
    sync_to_vps("security_toggle", {"guild_id": guild_id, "module": module_key, "state": state_val})
    return jsonify({"success": True, "module": module_key, "state": state_val})

@app.route("/api/settings/update", methods=["POST"])
def api_update_settings():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    new_settings = data.get("settings", {})
    for key, value in new_settings.items():
        db.update_guild_setting(guild_id, key, value)

    db.add_audit_log(guild_id, "SETTINGS_UPDATE", f"Security settings updated via Dashboard: {list(new_settings.keys())}", severity="MEDIUM")
    sync_to_vps("update_settings", {"guild_id": guild_id, "settings": new_settings})
    return jsonify({"success": True, "message": "Settings updated successfully."})

@app.route("/api/tempbans/unban", methods=["POST"])
def api_tempban_unban():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user_id parameter"}), 400

    db.remove_tempban(guild_id, user_id)
    
    if bot_instance and bot_instance.is_ready():
        try:
            guild = None
            try:
                guild = bot_instance.get_guild(int(guild_id))
            except Exception:
                pass
            if not guild and bot_instance.guilds:
                guild = bot_instance.guilds[0]

            if guild:
                async def safe_unban():
                    try:
                        await guild.unban(discord.Object(id=int(user_id)), reason="[Web Dashboard] Early unban.")
                    except Exception as e:
                        logger.warning(f"Could not unban user {user_id}: {e}")

                bot_instance.loop.create_task(safe_unban())
        except Exception as e:
            logger.warning(f"Unban exception: {e}")
            
    db.add_audit_log(guild_id, "UNBAN", f"Early unban triggered via Web Dashboard for user ID {user_id}.", severity="MEDIUM")
    return jsonify({"success": True, "message": f"Unbanned user {user_id}."})

@app.route("/api/whitelists/add", methods=["POST"])
def api_whitelist_add():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    target_id = data.get("target_id")
    target_type = data.get("target_type", "user")
    feature = data.get("feature", "all")
    
    if not target_id:
        return jsonify({"success": False, "error": "Missing target_id parameter"}), 400

    success = db.add_whitelist(guild_id, target_id, target_type, feature, "Web Dashboard")
    db.add_audit_log(guild_id, "WHITELIST_ADD", f"Added {target_type} ID {target_id} to whitelist ({feature}).", severity="MEDIUM")
    return jsonify({"success": success})

@app.route("/api/whitelists/remove", methods=["POST"])
def api_whitelist_remove():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    target_id = data.get("target_id")
    feature = data.get("feature", "all")
    
    if not target_id:
        return jsonify({"success": False, "error": "Missing target_id parameter"}), 400

    removed = db.remove_whitelist(guild_id, target_id, feature)
    db.add_audit_log(guild_id, "WHITELIST_REMOVE", f"Removed ID {target_id} from whitelist.", severity="MEDIUM")
    return jsonify({"success": removed})

@app.route("/api/badwords/add", methods=["POST"])
def api_add_badword():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    word = data.get("word")
    if not word:
        return jsonify({"success": False, "error": "Missing word parameter"}), 400

    success = db.add_bad_word(guild_id, word, "Web Dashboard")
    db.add_audit_log(guild_id, "AUTOMOD_RULE", f"Added bad word rule: '{word}'", severity="LOW")
    return jsonify({"success": success})

@app.route("/api/badwords/remove", methods=["POST"])
def api_remove_badword():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    word = data.get("word")
    if not word:
        return jsonify({"success": False, "error": "Missing word parameter"}), 400

    removed = db.remove_bad_word(guild_id, word)
    db.add_audit_log(guild_id, "AUTOMOD_RULE", f"Removed bad word rule: '{word}'", severity="LOW")
    return jsonify({"success": removed})

@app.route("/api/moderation/action", methods=["POST"])
def api_moderation_action():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not check_guild_access(guild_id):
        return jsonify({"success": False, "error": "Unauthorized: Access Denied for Guild"}), 403

    target_id = data.get("target_id")
    action = data.get("action")  # 'kick', 'ban', 'timeout', 'warn', 'purge', 'lock', 'unlock'
    reason = data.get("reason", "Web Dashboard Action")

    if not target_id or not action:
        return jsonify({"success": False, "error": "Missing target_id or action parameters"}), 400

    if bot_instance and bot_instance.is_ready():
        try:
            guild = None
            try:
                guild = bot_instance.get_guild(int(guild_id))
            except Exception:
                pass
            if not guild and bot_instance.guilds:
                guild = bot_instance.guilds[0]

            if guild:
                async def execute_mod():
                    try:
                        t_id = int(target_id) if target_id.isdigit() else None
                        if action == 'kick' and t_id:
                            member = guild.get_member(t_id) or await guild.fetch_member(t_id)
                            if member: await member.kick(reason=reason)
                        elif action == 'ban' and t_id:
                            await guild.ban(discord.Object(id=t_id), reason=reason)
                        elif action == 'timeout' and t_id:
                            member = guild.get_member(t_id) or await guild.fetch_member(t_id)
                            if member: await member.timeout(datetime.timedelta(minutes=30), reason=reason)
                        elif action == 'warn' and t_id:
                            db.add_warning(str(guild.id), str(t_id), reason, "Web Dashboard")
                        elif action == 'purge':
                            ch = (guild.get_channel(t_id) if t_id else None) or (guild.text_channels[0] if guild.text_channels else None)
                            if ch: await ch.purge(limit=50, reason=reason)
                        elif action == 'lock':
                            ch = (guild.get_channel(t_id) if t_id else None) or (guild.text_channels[0] if guild.text_channels else None)
                            if ch: await ch.set_permissions(guild.default_role, send_messages=False, reason=reason)
                        elif action == 'unlock':
                            ch = (guild.get_channel(t_id) if t_id else None) or (guild.text_channels[0] if guild.text_channels else None)
                            if ch: await ch.set_permissions(guild.default_role, send_messages=True, reason=reason)

                        db.add_audit_log(str(guild.id), f"MOD_{action.upper()}", f"Executed {action} on ID {target_id}. Reason: {reason}", severity="HIGH")
                    except Exception as e:
                        logger.warning(f"Mod action error: {e}")

                bot_instance.loop.create_task(execute_mod())
                return jsonify({"success": True, "message": f"{action.capitalize()} action dispatched to Discord."})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # Fallback to recording audit log & dispatching via Real-Time IPC Bridge even if bot is on a separate server
    db.push_ipc_command(guild_id, action, target_id)
    db.add_audit_log(guild_id, f"MOD_{action.upper()}", f"[Queued] Executed {action} on ID {target_id}. Reason: {reason}", severity="MEDIUM")
    return jsonify({"success": True, "message": f"Action '{action}' dispatched via Real-Time IPC Bridge."})

@app.route("/api/giveaways/create", methods=["POST"])
def api_giveaways_create():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    prize = data.get("prize", "Discord Nitro")
    description = data.get("description")
    duration_mins = int(data.get("duration_mins", 60))
    winners = int(data.get("winners", 1))
    channel_id = data.get("channel_id") or str(config.AI_CHAT_CHANNEL_ID)
    color_hex = data.get("color", "#ec4899")
    banner_url = data.get("banner_url")
    thumbnail_url = data.get("thumbnail_url")
    required_role_id = data.get("required_role_id")

    if not prize:
        return jsonify({"success": False, "error": "Missing prize parameter"}), 400

    if not channel_id or not str(channel_id).isdigit():
        channel_id = str(config.AI_CHAT_CHANNEL_ID)

    end_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + (duration_mins * 60)

    if bot_instance and bot_instance.is_ready():
        try:
            async def dispatch_giveaway():
                ch = bot_instance.get_channel(int(channel_id))
                if not ch:
                    ch = await bot_instance.fetch_channel(int(channel_id))

                c_val = 0xec4899
                if color_hex and color_hex.startswith("#"):
                    try: c_val = int(color_hex.lstrip("#"), 16)
                    except Exception: pass

                giveaway_desc = description or f"Click **Enter Giveaway** below to join!\n\n🎁 **Prize:** `{prize}`\n🏆 **Winners:** `{winners}`\n⏳ **Ends:** <t:{end_time}:R>"
                if required_role_id:
                    giveaway_desc += f"\n🔒 **Required Role:** <@&{required_role_id}>"

                embed = discord.Embed(
                    title=f"🎉 **GIVEAWAY: {prize}** 🎉",
                    description=giveaway_desc,
                    color=discord.Color(c_val),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                if thumbnail_url and thumbnail_url.startswith("http"):
                    embed.set_thumbnail(url=thumbnail_url)
                if banner_url and banner_url.startswith("http"):
                    embed.set_image(url=banner_url)

                embed.set_footer(text=f"{config.SERVER_NAME} Giveaways • React to Enter")

                from cogs.giveaway import GiveawayEntryView
                temp_msg = await ch.send(embed=embed)
                msg_id = str(temp_msg.id)

                view = GiveawayEntryView(msg_id)
                await temp_msg.edit(view=view)

                db.add_giveaway_db(guild_id, str(ch.id), msg_id, prize, winners, end_time, "Web Studio")
                db.add_audit_log(guild_id, "GIVEAWAY_CREATE", f"Launched giveaway '{prize}' (Msg ID {msg_id}) in #{ch.name}.", severity="MEDIUM")
                return {"success": True, "message": f"Giveaway for '{prize}' posted live to #{ch.name}!"}

            future = asyncio.run_coroutine_threadsafe(dispatch_giveaway(), bot_instance.loop)
            res = future.result(timeout=15)
            return jsonify(res)
        except Exception as e:
            logger.error(f"Giveaway creation error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    fake_msg_id = f"web_{int(datetime.datetime.now().timestamp())}"
    db.add_giveaway_db(guild_id, channel_id, fake_msg_id, prize, winners, end_time, "Web Studio")
    db.add_audit_log(guild_id, "GIVEAWAY_CREATE", f"Recorded giveaway '{prize}' in database.", severity="MEDIUM")
    return jsonify({"success": True, "message": "Giveaway recorded in database."})

@app.route("/api/giveaways/end", methods=["POST"])
def api_giveaways_end():
    data = request.json or {}
    message_id = data.get("message_id")
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not message_id:
        return jsonify({"success": False, "error": "Missing message_id"}), 400

    db.end_giveaway_db(message_id)
    db.add_audit_log(guild_id, "GIVEAWAY_END", f"Ended giveaway ID {message_id} early.", severity="MEDIUM")
    return jsonify({"success": True, "message": "Giveaway ended."})

def parse_discord_emoji_object(emoji_input):
    if not emoji_input:
        return "🎫"
    if isinstance(emoji_input, discord.PartialEmoji):
        return emoji_input
    
    emoji_str = str(emoji_input).strip().lstrip('\\')

    if (emoji_str.startswith("<:") or emoji_str.startswith("<a:")) and emoji_str.endswith(">"):
        try:
            return discord.PartialEmoji.from_str(emoji_str)
        except Exception:
            pass

    cdn_match = re.search(r'emojis/(\d+)\.(gif|png|webp)', emoji_str)
    if cdn_match:
        emoji_id = int(cdn_match.group(1))
        animated = (cdn_match.group(2) == "gif")
        return discord.PartialEmoji(name="emoji", id=emoji_id, animated=animated)

    if emoji_str.isdigit():
        return discord.PartialEmoji(name="emoji", id=int(emoji_str), animated=True)

    return emoji_str

def format_discord_embed_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\\(<a?:\w+:\d+>)', r'\1', text)
    def cdn_repl(m):
        e_id = m.group(1)
        ext = m.group(2)
        anim = "a" if ext == "gif" else ""
        return f"<{anim}:emoji:{e_id}>"
    text = re.sub(r'https?://cdn\.discordapp\.com/emojis/(\d+)\.(gif|png|webp)(\?\S+)?', cdn_repl, text)
    return text

@app.route("/api/tickets/create_panel", methods=["POST"])
def api_tickets_create_panel():
    data = request.json or {}
    guild_id = resolve_guild_id(data.get("guild_id"))
    channel_id = data.get("channel_id") or str(config.AI_CHAT_CHANNEL_ID)
    
    title = format_discord_embed_text(data.get("title", "🎫 Joyst Corporation Support"))
    description = format_discord_embed_text(data.get("description", "Select an option from the menu below to open a private support ticket."))
    color_hex = data.get("color", "#008080")
    thumbnail_url = data.get("thumbnail_url")
    banner_url = data.get("banner_url")
    footer_text = format_discord_embed_text(data.get("footer_text", "© Joyst Corporation , All Rights Reserved."))
    options_list = data.get("options", [])

    if not channel_id or not str(channel_id).isdigit():
        channel_id = str(config.AI_CHAT_CHANNEL_ID)

    if bot_instance and bot_instance.is_ready():
        try:
            async def dispatch_ticket_panel():
                ch = bot_instance.get_channel(int(channel_id))
                if not ch:
                    ch = await bot_instance.fetch_channel(int(channel_id))

                c_val = 0x008080
                if color_hex and color_hex.startswith("#"):
                    try: c_val = int(color_hex.lstrip("#"), 16)
                    except Exception: pass

                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=discord.Color(c_val),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                if thumbnail_url and thumbnail_url.startswith("http"):
                    embed.set_thumbnail(url=thumbnail_url)
                if banner_url and banner_url.startswith("http"):
                    embed.set_image(url=banner_url)
                if footer_text:
                    embed.set_footer(text=footer_text)

                # Use official Ticket Verse View if standard panel or default options
                if not options_list:
                    from cogs.tickets import TicketView
                    panel_msg = await ch.send(embed=embed, view=TicketView(bot_instance=bot_instance))
                    cfg = db.load_config() if hasattr(db, "load_config") else {}
                    cfg['panel_message_id'] = panel_msg.id
                    cfg['panel_channel_id'] = panel_msg.channel.id
                    db.save_config(cfg) if hasattr(db, "save_config") else None
                    db.add_audit_log(guild_id, "TICKET_PANEL", f"Deployed official Joyst Ticket Verse panel to #{ch.name}.", severity="MEDIUM")
                    return {"success": True, "message": f"Official Joyst Ticket Panel deployed to #{ch.name}!"}

                # Dynamically construct Select Dropdown Options if custom options provided
                select_options = []
                for opt in options_list[:25]:
                    raw_emoji = opt.get("emoji", "🎫") or "🎫"
                    parsed_emoji = parse_discord_emoji_object(raw_emoji)
                    select_options.append(
                        discord.SelectOption(
                            label=opt.get("label", "Support")[:100],
                            value=opt.get("value", opt.get("label", "support")).lower().replace(" ", "_")[:90],
                            description=opt.get("description", "Click to open ticket")[:100],
                            emoji=parsed_emoji
                        )
                    )

                class CustomTicketDropdownSelect(discord.ui.Select):
                    def __init__(self, opts):
                        super().__init__(placeholder="Click here to Buy Panel / Projects & For Support", min_values=1, max_values=1, options=opts, custom_id="custom_ticket_select")

                    async def callback(self, interaction: discord.Interaction):
                        cat_choice = self.values[0]
                        user = interaction.user
                        guild = interaction.guild

                        clean_username = user.name.lower().replace(" ", "-")
                        target_name = f"ticket-{cat_choice}-{clean_username}"

                        for existing_ch in guild.text_channels:
                            if existing_ch.name == target_name:
                                await interaction.response.send_message(f"⚠️ You already have an open ticket in {existing_ch.mention}!", ephemeral=True)
                                return

                        category = discord.utils.get(guild.categories, name="🎫 TICKETS")
                        if not category:
                            try: category = await guild.create_category("🎫 TICKETS")
                            except Exception: category = None

                        overwrites = {
                            guild.default_role: discord.PermissionOverwrite(read_messages=False),
                            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
                        }

                        ticket_ch = await guild.create_text_channel(name=target_name, category=category, overwrites=overwrites)
                        db.add_ticket_db(str(guild.id), str(user.id), str(ticket_ch.id))

                        w_embed = discord.Embed(
                            title=f"🎟️ Ticket — {cat_choice.replace('_', ' ').title()}",
                            description=f"Hello {user.mention}, thank you for reaching out to **{guild.name} Staff**!\nPlease describe your issue or request in detail below.",
                            color=discord.Color.teal()
                        )
                        from cogs.tickets import TicketCloseView
                        await ticket_ch.send(content=f"{user.mention} Welcome!", embed=w_embed, view=TicketCloseView())
                        await interaction.response.send_message(f"✅ Ticket created: {ticket_ch.mention}", ephemeral=True)

                class CustomTicketView(discord.ui.View):
                    def __init__(self, opts):
                        super().__init__(timeout=None)
                        self.add_item(CustomTicketDropdownSelect(opts))

                view = CustomTicketView(select_options)
                await ch.send(embed=embed, view=view)
                db.add_audit_log(guild_id, "TICKET_PANEL", f"Deployed custom Ticket panel to #{ch.name}.", severity="MEDIUM")
                return {"success": True, "message": f"Custom Ticket Panel deployed to #{ch.name}!"}

            future = asyncio.run_coroutine_threadsafe(dispatch_ticket_panel(), bot_instance.loop)
            res = future.result(timeout=15)
            return jsonify(res)
        except Exception as e:
            logger.error(f"Ticket panel creation error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    bot_token = os.getenv("DISCORD_BOT_TOKEN", getattr(config, "DISCORD_BOT_TOKEN", ""))
    if bot_token:
        try:
            c_val = 0x008080
            if color_hex and color_hex.startswith("#"):
                try: c_val = int(color_hex.lstrip("#"), 16)
                except Exception: pass

            embed_obj = {
                "title": title,
                "description": description,
                "color": c_val,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            if thumbnail_url and thumbnail_url.startswith("http"):
                embed_obj["thumbnail"] = {"url": thumbnail_url}
            if banner_url and banner_url.startswith("http"):
                embed_obj["image"] = {"url": banner_url}
            if footer_text:
                embed_obj["footer"] = {"text": footer_text}

            select_opts = []
            if options_list:
                for opt in options_list[:25]:
                    select_opts.append({
                        "label": opt.get("label", "Support")[:100],
                        "value": opt.get("value", opt.get("label", "support")).lower().replace(" ", "_")[:90],
                        "description": opt.get("description", "Click to open ticket")[:100],
                        "emoji": {"name": "🎫"}
                    })
            else:
                select_opts = [
                    {"label": "General Support", "value": "support", "description": "Open a general support ticket", "emoji": {"name": "🎫"}},
                    {"label": "Billing & Purchases", "value": "billing", "description": "Payment & Store inquiries", "emoji": {"name": "💳"}},
                    {"label": "Report Issue", "value": "report", "description": "Report a user or bug", "emoji": {"name": "⚠️"}}
                ]

            components_obj = [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3,
                            "custom_id": "custom_ticket_select",
                            "placeholder": "Click here to Buy Panel / Projects & For Support",
                            "options": select_opts
                        }
                    ]
                }
            ]

            payload = {
                "embeds": [embed_obj],
                "components": components_obj
            }

            headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
            post_res = requests.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", json=payload, headers=headers, timeout=10)
            
            if post_res.status_code in [200, 201]:
                db.add_audit_log(guild_id, "TICKET_PANEL", f"Deployed Ticket panel to channel {channel_id} via Dashboard.", severity="MEDIUM")
                sync_to_vps("ticket_panel", {"guild_id": guild_id, "channel_id": channel_id})
                return jsonify({"success": True, "message": f"Joyst Ticket Panel deployed live to channel {channel_id}!"})
            else:
                logger.error(f"Discord API Ticket Panel error ({post_res.status_code}): {post_res.text}")
                return jsonify({"success": False, "error": f"Discord API returned HTTP {post_res.status_code}"}), 500
        except Exception as e:
            logger.error(f"Ticket Panel API Error: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": False, "error": "Missing DISCORD_BOT_TOKEN"}), 500

@app.route("/api/tickets/close", methods=["POST"])
def api_tickets_close():
    data = request.json or {}
    channel_id = data.get("channel_id")
    guild_id = resolve_guild_id(data.get("guild_id"))
    if not channel_id:
        return jsonify({"success": False, "error": "Missing channel_id"}), 400

    db.close_ticket_db(channel_id)
    
    if bot_instance and bot_instance.is_ready():
        try:
            async def close_ch():
                ch = bot_instance.get_channel(int(channel_id))
                if ch: await ch.delete(reason="[Web Dashboard] Ticket closed.")
            bot_instance.loop.create_task(close_ch())
        except Exception as e:
            logger.warning(f"Ticket close error: {e}")

    db.add_audit_log(guild_id, "TICKET_CLOSE", f"Closed support ticket channel ID {channel_id}.", severity="MEDIUM")
    return jsonify({"success": True, "message": "Ticket closed."})

@app.route("/api/voice/join_and_play", methods=["POST"])
def api_voice_join_and_play():
    data = request.json or {}
    channel_id = data.get("channel_id")
    query = data.get("query", "").strip() or "JHOL"

    if not channel_id:
        return jsonify({"success": False, "error": "Missing Voice Channel ID"}), 400

    if not bot_instance or not bot_instance.is_ready():
        import json
        payload = json.dumps({"vc_id": channel_id, "query": query})
        db.push_ipc_command(resolve_guild_id(), "voice_play", payload)
        return jsonify({"success": True, "message": "Voice audio stream queued via Real-Time IPC Bridge!"})

    try:
        ch_id = int(channel_id)
        channel = bot_instance.get_channel(ch_id)
        
        async def fetch_and_join():
            nonlocal channel
            try:
                if not channel:
                    channel = await bot_instance.fetch_channel(ch_id)

                if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    return {"success": False, "error": f"ID {channel_id} is a {type(channel).__name__}, not a Voice/Stage channel."}

                guild = channel.guild
                vc = guild.voice_client
                if vc and vc.is_connected():
                    if vc.channel.id != channel.id:
                        await vc.move_to(channel)
                else:
                    vc = await channel.connect(reconnect=True, timeout=15.0)

                music_cog = bot_instance.get_cog("Music")
                if music_cog:
                    from cogs.music import YTDLSource
                    source = await YTDLSource.create_source(query, requester=bot_instance.user, loop=bot_instance.loop)
                    if vc.is_playing() or vc.is_paused():
                        vc.stop()
                    vc.play(source)
                    db.add_audit_log(str(guild.id), "MUSIC_PLAY", f"Streaming '{source.title}' in Voice Channel '{channel.name}' via Web Dashboard.", severity="INFO")
                    return {"success": True, "message": f"Connected to #{channel.name}! Now streaming: '{source.title}'"}
                else:
                    return {"success": False, "error": "Music engine cog not loaded."}
            except Exception as e:
                logger.error(f"Voice join error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

        future = asyncio.run_coroutine_threadsafe(fetch_and_join(), bot_instance.loop)
        res = future.result(timeout=25)
        return jsonify(res)

    except Exception as e:
        logger.error(f"Join & Play API Exception: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/control", methods=["POST"])
def api_voice_control():
    data = request.json or {}
    command = data.get("command", "").lower()
    volume = data.get("volume")

    if not bot_instance or not bot_instance.is_ready():
        sync_to_vps("voice_control", data)
        return jsonify({"success": True, "message": f"Voice command '{command}' dispatched to bot!"})

    async def run_vc_control():
        try:
            guild_id = resolve_guild_id()
            guild = None
            try:
                guild = bot_instance.get_guild(int(guild_id))
            except Exception:
                pass
            if not guild and bot_instance.guilds:
                guild = bot_instance.guilds[0]

            if not guild or not guild.voice_client:
                return {"success": False, "error": "Bot is not connected to any Voice Channel."}

            vc = guild.voice_client
            if command == "pause":
                if vc.is_playing(): vc.pause()
                return {"success": True, "message": "Playback paused."}
            elif command == "resume":
                if vc.is_paused(): vc.resume()
                return {"success": True, "message": "Playback resumed."}
            elif command in ["stop", "skip", "leave"]:
                if vc.is_playing() or vc.is_paused(): vc.stop()
                if command == "leave": await vc.disconnect(force=True)
                return {"success": True, "message": f"Voice action '{command}' executed."}
            elif command == "volume" and volume is not None:
                vol_val = max(0, min(100, int(volume))) / 100.0
                if vc.source and hasattr(vc.source, "volume"):
                    vc.source.volume = vol_val
                return {"success": True, "message": f"Volume adjusted to {volume}%"}

            return {"success": False, "error": f"Unknown command '{command}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    try:
        future = asyncio.run_coroutine_threadsafe(run_vc_control(), bot_instance.loop)
        res = future.result(timeout=10)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/tts/speak", methods=["POST"])
def api_tts_speak():
    data = request.json or {}
    channel_id = data.get("channel_id") or "1409233869995118602"
    text = data.get("text", "").strip()
    lang = data.get("lang", "en")

    if not text:
        return jsonify({"success": False, "error": "Missing text parameter"}), 400

    if not bot_instance or not bot_instance.is_ready():
        import json
        payload = json.dumps({"vc_id": channel_id, "text": text, "lang": lang})
        db.push_ipc_command(resolve_guild_id(), "tts_speak", payload)
        return jsonify({"success": True, "message": "Voice command dispatched via Real-Time IPC Bridge!"})

    try:
        async def do_tts():
            ch = bot_instance.get_channel(int(channel_id))
            if not ch:
                ch = await bot_instance.fetch_channel(int(channel_id))
            if not isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                return {"success": False, "error": "Target ID is not a Voice Channel."}

            tts_cog = bot_instance.get_cog("TTS")
            if tts_cog:
                success, msg = await tts_cog.speak_text_in_vc(ch.guild, ch, text, lang)
                return {"success": success, "message": msg}
            return {"success": False, "error": "TTS Cog not loaded."}

        future = asyncio.run_coroutine_threadsafe(do_tts(), bot_instance.loop)
        res = future.result(timeout=15)
        return jsonify(res)
    except Exception as e:
        logger.error(f"TTS API Error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/sentiment/stats", methods=["GET"])
def api_sentiment_stats():
    if bot_instance and bot_instance.is_ready():
        cog = bot_instance.get_cog("SentimentTracker")
        if cog:
            return jsonify(cog.get_server_mood_stats())
    return jsonify({"health_percent": 100.0, "drama_percent": 0.0, "server_mood": "PEACEFUL 🟢", "recent_spikes": []})

@app.route("/api/socials/broadcast", methods=["POST"])
def api_socials_broadcast():
    data = request.json or {}
    channel_id = data.get("channel_id") or str(config.AI_CHAT_CHANNEL_ID)
    platform = data.get("platform", "youtube")
    title = data.get("title", "Live Stream")
    url = data.get("url", "https://youtube.com")
    thumbnail_url = data.get("thumbnail_url")
    ping_role_id = data.get("ping_role_id")

    if not channel_id or not str(channel_id).isdigit():
        channel_id = str(config.AI_CHAT_CHANNEL_ID)

    if bot_instance and bot_instance.is_ready():
        try:
            async def do_broadcast():
                ch = bot_instance.get_channel(int(channel_id))
                if not ch:
                    ch = await bot_instance.fetch_channel(int(channel_id))

                social_cog = bot_instance.get_cog("Socials")
                if social_cog:
                    success, msg = await social_cog.broadcast_social_stream(ch.guild, ch, platform, title, url, thumbnail_url, ping_role_id)
                    return {"success": success, "message": msg}
                return {"success": False, "error": "Socials Cog not loaded."}

            future = asyncio.run_coroutine_threadsafe(do_broadcast(), bot_instance.loop)
            res = future.result(timeout=15)
            return jsonify(res)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    bot_token = os.getenv("DISCORD_BOT_TOKEN", getattr(config, "DISCORD_BOT_TOKEN", ""))
    if bot_token:
        try:
            embed_obj = {
                "title": f"🔴 LIVE BROADCAST: {title}",
                "url": url,
                "description": f"Click [Watch Now]({url}) to join the live stream!",
                "color": 0xFF0000,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            if thumbnail_url:
                embed_obj["thumbnail"] = {"url": thumbnail_url}
            
            content_str = f"<@&{ping_role_id}>" if ping_role_id else "@everyone"
            payload = {"content": content_str, "embeds": [embed_obj]}
            headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
            requests.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", json=payload, headers=headers, timeout=10)
            sync_to_vps("socials_broadcast", data)
            return jsonify({"success": True, "message": f"Broadcast '{title}' posted live!"})
        except Exception as e:
            logger.error(f"Social Broadcast API Error: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": False, "error": "Missing DISCORD_BOT_TOKEN"}), 500

@app.route("/api/status/update", methods=["POST"])
def api_status_update():
    data = request.json or {}
    status_str = data.get("status", "online").lower()
    activity_type = data.get("activity_type", "playing").lower()
    activity_name = data.get("name", f"{config.SERVER_NAME} Services").strip()

    if not bot_instance or not bot_instance.is_ready():
        sync_to_vps("status_update", data)
        return jsonify({"success": True, "message": f"Bot status update '{activity_name}' dispatched to bot!"})

    try:
        async def do_update():
            status_map = {
                "online": discord.Status.online,
                "idle": discord.Status.idle,
                "dnd": discord.Status.dnd,
                "invisible": discord.Status.invisible
            }
            target_status = status_map.get(status_str, discord.Status.online)

            act = None
            if activity_type == "streaming":
                act = discord.Streaming(name=activity_name, url="https://twitch.tv/joystcorp")
            elif activity_type == "listening":
                act = discord.Activity(type=discord.ActivityType.listening, name=activity_name)
            elif activity_type == "watching":
                act = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
            elif activity_type == "competing":
                act = discord.Activity(type=discord.ActivityType.competing, name=activity_name)
            else:
                act = discord.Game(name=activity_name)

            await bot_instance.change_presence(status=target_status, activity=act)
            return {"success": True, "message": f"Bot status updated to {status_str.upper()} — {activity_type.title()} '{activity_name}'"}

        future = asyncio.run_coroutine_threadsafe(do_update(), bot_instance.loop)
        res = future.result(timeout=10)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Status Update Error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/weather", methods=["GET"])
def api_weather():
    city = request.args.get("city", "Kanpur").strip()
    if not bot_instance or not bot_instance.is_ready():
        try:
            r = requests.get(f"https://wttr.in/{urllib.parse.quote(city)}?format=j1", timeout=5)
            if r.status_code == 200:
                wd = r.json()
                curr = wd.get("current_condition", [{}])[0]
                temp = curr.get("temp_C", "28")
                desc = curr.get("weatherDesc", [{}])[0].get("value", "Clear")
                return jsonify({"success": True, "data": {"city": city, "temp": f"{temp}°C", "condition": desc}})
        except Exception:
            pass
        return jsonify({"success": True, "data": {"city": city, "temp": "28°C", "condition": "Clear ☀️"}})

    try:
        async def fetch():
            weather_cog = bot_instance.get_cog("Weather")
            if weather_cog:
                res = await weather_cog.fetch_weather_data(city)
                if res:
                    return {"success": True, "data": res}
        future = asyncio.run_coroutine_threadsafe(fetch(), bot_instance.loop)
        res = future.result(timeout=10)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/members", methods=["GET"])
def api_members():
    gid = resolve_guild_id(request.args.get("guild_id"))
    search_q = request.args.get("q", "").strip().lower()

    if not bot_instance or not bot_instance.is_ready():
        bot_token = os.getenv("DISCORD_BOT_TOKEN", getattr(config, "DISCORD_BOT_TOKEN", ""))
        if bot_token:
            try:
                headers = {"Authorization": f"Bot {bot_token}"}
                mr = requests.get(f"https://discord.com/api/v10/guilds/{gid}/members?limit=100", headers=headers, timeout=5)
                gr = requests.get(f"https://discord.com/api/v10/guilds/{gid}?with_counts=true", headers=headers, timeout=5)
                
                total_cnt = 0
                if gr.status_code == 200:
                    total_cnt = gr.json().get("approximate_member_count", 0)

                if mr.status_code == 200:
                    m_data = mr.json()
                    member_list = []
                    for m in m_data:
                        u = m.get("user", {})
                        uname = u.get("username", "User")
                        uid = u.get("id", "")
                        disp_name = m.get("nick") or uname
                        
                        if search_q and search_q not in uname.lower() and search_q not in uid and search_q not in disp_name.lower():
                            continue

                        avatar_hash = u.get("avatar")
                        avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
                        is_bot = u.get("bot", False)

                        member_list.append({
                            "id": str(uid),
                            "name": disp_name,
                            "username": uname,
                            "avatar": avatar_url,
                            "role": "Bot" if is_bot else "Member",
                            "status": "ONLINE",
                            "is_bot": is_bot,
                            "is_owner": False,
                            "is_whitelisted": db.is_whitelisted(str(gid), str(uid), "all")
                        })
                    return jsonify({
                        "success": True,
                        "total_members": max(total_cnt, len(member_list)),
                        "members": member_list
                    })
            except Exception as e:
                logger.warning(f"Error fetching members via API: {e}")
        return jsonify({"success": False, "members": [], "total_members": 0})

    guild = bot_instance.get_guild(int(gid))
    if not guild:
        return jsonify({"success": False, "members": [], "total_members": 0})

    member_list = []
    for m in guild.members:
        if search_q and search_q not in m.name.lower() and search_q not in str(m.id) and search_q not in m.display_name.lower():
            continue

        avatar_url = m.display_avatar.url if hasattr(m, "display_avatar") else m.default_avatar.url
        roles_str = "Owner" if m.id == guild.owner_id else ("Bot" if m.bot else (m.top_role.name if m.top_role and m.top_role.name != "@everyone" else "Member"))
        status_str = str(m.status).upper() if hasattr(m, "status") else "OFFLINE"

        member_list.append({
            "id": str(m.id),
            "name": m.display_name,
            "username": str(m),
            "avatar": avatar_url,
            "role": roles_str,
            "status": status_str,
            "is_bot": m.bot,
            "is_owner": m.id == guild.owner_id,
            "is_whitelisted": db.is_whitelisted(str(guild.id), str(m.id), "all")
        })

        if len(member_list) >= 100:
            break

    return jsonify({
        "success": True,
        "total_members": guild.member_count or len(member_list),
        "members": member_list
    })

def run_web_dashboard():
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None
    print(f" * Running on http://localhost:{config.WEB_PORT} (Press CTRL+C to quit)")
    app.run(host="0.0.0.0", port=config.WEB_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    db.init_db()
    run_web_dashboard()

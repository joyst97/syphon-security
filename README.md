# 🛡️ AEGIS Advanced Discord Security Bot & Web Control Dashboard

AEGIS is a state-of-the-art **Discord Advanced Security & Protection System** written in Python using `discord.py` v2 and `Flask`. It combines real-time Anti-Nuke defense, Anti-Raid velocity shielding, Captcha Verification gates, AutoMod content filters, Ban Timeout background managers, and a modern Dark Glassmorphic Web Dashboard.

---

## ✨ Features Overview

### 🔒 1. Anti-Nuke Engine (Real-Time Safeguard)
* **Mass Channel & Role Protection**: Rate-limits channel/role creation and deletion per admin user.
* **Unauthorized Bot Addition Shield**: Detects when a new bot joins. Checks audit logs to identify who invited it. If the inviter is not whitelisted, the bot is instantly kicked and administrative roles are stripped from the inviter.
* **Auto-Quarantine**: Strips all `Administrator`, `Manage Server`, `Manage Roles`, and `Manage Channels` permissions from offenders during an attack.

### ⚡ 2. Anti-Raid Velocity Shield & Captcha Verification
* **Join Velocity Tracking**: Monitors joins per 10-second window. Automatically triggers **Raid Mode** if an influx is detected.
* **Young Account Filtering**: Automatically kicks accounts created <24h ago during active Raid Mode.
* **Interactive Button Captcha**: `/verify-setup` command deploys a persistent Discord Button verification gate granting access to verified members.

### ⏳ 3. Advanced Moderation & Ban Timeouts
* **Ban Timeout / Scheduled Temp-Ban**: `/tempban <member> <duration> [reason]` bans a user and schedules an automatic background unban upon duration expiry (e.g. `10m`, `2h`, `7d`, `30d`).
* **Discord Native Timeouts**: `/timeout <member> <duration> [reason]` applies instant native timeout up to 28 days.
* **Warn Escalation System**: Automated warning counter (3 warns -> 1h timeout, 5 warns -> 7d tempban, 7 warns -> permanent ban).
* **Channel Lockdown**: `/lockdown [channel] [enable/disable]` toggles message sending permissions across channels.

### 📜 4. Security Whitelist Matrix
* Whitelist trusted admins/roles to bypass Anti-Nuke, Anti-Link, or Anti-Spam filters.
* Commands: `/whitelist add`, `/whitelist remove`, `/whitelist list`.

### 🌐 5. Modern Web Control Dashboard (Flask + Glassmorphism UI)
* Accessible locally at `http://localhost:5000`.
* **Shield Health Score**: Dynamic security score calculation based on active rules.
* **Live Rules Toggle**: Interactively switch Anti-Nuke, Anti-Raid, Anti-Invite, Anti-Spam, and Captcha verification on/off.
* **Active Ban Timeouts Live Table**: View live countdowns for scheduled unbans and trigger early manual unbans with one click.
* **Whitelist Manager**: Add or remove whitelisted user/role IDs visually.
* **Incident Vault**: Real-time audit log stream showing severity levels, culprit IDs, and event details.

---

## 🚀 Quick Setup & Run Instructions

### 1. Requirements
* Python 3.10+
* `discord.py` 2.0+
* `Flask` & `flask-cors`
* `python-dotenv`

*(All dependencies are already installed in your Python environment).*

### 2. Configure Credentials
Open the `.env` file in the project folder and insert your Discord Bot Token and Client ID:
```env
DISCORD_BOT_TOKEN=your_actual_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here
PORT=5000
```

> ⚠️ **Important Discord Developer Portal Settings**:
> Go to [Discord Developer Portal](https://discord.com/developers/applications) -> Select your bot -> **Bot** tab -> Enable **Privileged Gateway Intents**:
> - ✅ **Server Members Intent**
> - ✅ **Message Content Intent**
> - ✅ **Presence Intent**

### 3. Launch the Bot & Dashboard
Run the main script:
```bash
python bot.py
```

Visit the Web Control Dashboard at:
👉 **[http://localhost:5000](http://localhost:5000)**

---

## 💻 Command Reference

| Command | Description | Required Permission |
| :--- | :--- | :--- |
| `/security status` | Displays full security shield status and stats embed | Everyone |
| `/security setup` | Sets security alert log channel | Administrator |
| `/verify-setup` | Deploys interactive member captcha verification panel | Administrator |
| `/tempban <member> <duration> [reason]` | Ban member with duration timeout (e.g. `7d`) | Ban Members |
| `/unban <user_id> [reason]` | Unban user and cancel active tempban entry | Ban Members |
| `/timeout <member> <duration> [reason]` | Native Discord timeout (e.g. `1h`) | Moderate Members |
| `/untimeout <member>` | Clear timeout from member | Moderate Members |
| `/warn <member> <reason>` | Issue a warning and trigger escalation checks | Moderate Members |
| `/warnings <member>` | View warning history for a user | Moderate Members |
| `/kick <member> [reason]` | Kick member from server | Kick Members |
| `/lockdown [channel] [state]` | Lock or unlock channel message permissions | Manage Channels |
| `/whitelist add <target> [feature]` | Add user or role to security whitelist | Administrator |
| `/whitelist remove <target_id> [feature]` | Remove entity from whitelist | Administrator |
| `/whitelist list` | View all whitelisted entities | Administrator |

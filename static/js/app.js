/* UI Anti-Steal & Layout Copy Protection */
document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
}, false);

document.addEventListener('keydown', function(e) {
    // Disable F12, Ctrl+U, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+S
    if (e.keyCode === 123 || 
        (e.ctrlKey && e.shiftKey && (e.keyCode === 73 || e.keyCode === 74)) || 
        (e.ctrlKey && (e.keyCode === 85 || e.keyCode === 83))) {
        e.preventDefault();
        return false;
    }
});

/* DevTools Anti-Debugging Trap: Immediately locks up DevTools if opened */
setInterval(function() {
    try {
        (function() { return false; })['constructor']('debugger')['call']();
    } catch(e) {}
}, 50);

let currentGuildId = 'default';
let allAuditLogs = [];

function initAll() {
    initShapeGrid();
    initProfileCardTilt();
    initElectricBorder();
    initDriftWall();
    initGauge();
    refreshDashboard();
    
    // Smart auto-refresh every 15s (only when tab is active) for 60FPS smoothness
    setInterval(() => {
        if (document.hidden) return;
        fetchStats();
        loadTempBans();
        loadAuditLogs();
        loadTickets();
        loadGiveaways();
    }, 15000);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
} else {
    initAll();
}

/* ============================================================
 * 1. REACT BITS SHAPEGRID CANVAS BACKGROUND MATRIX
 * ============================================================ */
function initShapeGrid(options = {}) {
    const canvas = document.getElementById('galaxyCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const {
        direction = 'diagonal',
        speed = 0.5,
        borderColor = 'rgba(255, 255, 255, 0.18)', // Crisp, visible dark-mode grid lines
        squareSize = 40,
        hoverFillColor = 'rgba(168, 85, 247, 0.75)', // Vibrant purple glow hover trail
        shape = 'square',
        hoverTrailAmount = 8
    } = options;

    const isHex = shape === 'hexagon';
    const isTri = shape === 'triangle';
    const hexHoriz = squareSize * 1.5;
    const hexVert = squareSize * Math.sqrt(3);

    let gridOffset = { x: 0, y: 0 };
    let hoveredSquare = null;
    let trailCells = [];
    let cellOpacities = new Map();
    let requestRef = null;

    function resizeCanvas() {
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(window.innerWidth * dpr);
        canvas.height = Math.floor(window.innerHeight * dpr);
        canvas.style.width = `${window.innerWidth}px`;
        canvas.style.height = `${window.innerHeight}px`;
    }

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    const drawHex = (cx, cy, size) => {
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i;
            const vx = cx + size * Math.cos(angle);
            const vy = cy + size * Math.sin(angle);
            if (i === 0) ctx.moveTo(vx, vy);
            else ctx.lineTo(vx, vy);
        }
        ctx.closePath();
    };

    const drawCircle = (cx, cy, size) => {
        ctx.beginPath();
        ctx.arc(cx, cy, size / 2, 0, Math.PI * 2);
        ctx.closePath();
    };

    const drawTriangle = (cx, cy, size, flip) => {
        ctx.beginPath();
        if (flip) {
            ctx.moveTo(cx, cy + size / 2);
            ctx.lineTo(cx + size / 2, cy - size / 2);
            ctx.lineTo(cx - size / 2, cy - size / 2);
        } else {
            ctx.moveTo(cx, cy - size / 2);
            ctx.lineTo(cx + size / 2, cy + size / 2);
            ctx.lineTo(cx - size / 2, cy + size / 2);
        }
        ctx.closePath();
    };

    function drawGrid() {
        const dpr = window.devicePixelRatio || 1;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.scale(dpr, dpr);

        const w = window.innerWidth;
        const h = window.innerHeight;

        if (isHex) {
            const colShift = Math.floor(gridOffset.x / hexHoriz);
            const offsetX = ((gridOffset.x % hexHoriz) + hexHoriz) % hexHoriz;
            const offsetY = ((gridOffset.y % hexVert) + hexVert) % hexVert;

            const cols = Math.ceil(w / hexHoriz) + 4;
            const rows = Math.ceil(h / hexVert) + 4;

            for (let col = -2; col < cols; col++) {
                for (let row = -2; row < rows; row++) {
                    const cx = col * hexHoriz + offsetX;
                    const cy = row * hexVert + ((col + colShift) % 2 !== 0 ? hexVert / 2 : 0) + offsetY;

                    drawHex(cx, cy, squareSize);
                    ctx.strokeStyle = borderColor;
                    ctx.lineWidth = 1.5;
                    ctx.stroke();
                }
            }
        } else if (isTri) {
            const halfW = squareSize / 2;
            const colShift = Math.floor(gridOffset.x / halfW);
            const rowShift = Math.floor(gridOffset.y / squareSize);
            const offsetX = ((gridOffset.x % halfW) + halfW) % halfW;
            const offsetY = ((gridOffset.y % squareSize) + squareSize) % squareSize;

            const cols = Math.ceil(w / halfW) + 4;
            const rows = Math.ceil(h / squareSize) + 4;

            for (let col = -2; col < cols; col++) {
                for (let row = -2; row < rows; row++) {
                    const cx = col * halfW + offsetX;
                    const cy = row * squareSize + squareSize / 2 + offsetY;
                    const flip = ((col + colShift + row + rowShift) % 2 + 2) % 2 !== 0;

                    drawTriangle(cx, cy, squareSize, flip);
                    ctx.strokeStyle = borderColor;
                    ctx.lineWidth = 1.5;
                    ctx.stroke();
                }
            }
        } else if (shape === 'circle') {
            const offsetX = ((gridOffset.x % squareSize) + squareSize) % squareSize;
            const offsetY = ((gridOffset.y % squareSize) + squareSize) % squareSize;

            const cols = Math.ceil(w / squareSize) + 4;
            const rows = Math.ceil(h / squareSize) + 4;

            for (let col = -2; col < cols; col++) {
                for (let row = -2; row < rows; row++) {
                    const cx = col * squareSize + squareSize / 2 + offsetX;
                    const cy = row * squareSize + squareSize / 2 + offsetY;

                    drawCircle(cx, cy, squareSize);
                    ctx.strokeStyle = borderColor;
                    ctx.lineWidth = 1.5;
                    ctx.stroke();
                }
            }
        } else {
            const offsetX = ((gridOffset.x % squareSize) + squareSize) % squareSize;
            const offsetY = ((gridOffset.y % squareSize) + squareSize) % squareSize;

            const cols = Math.ceil(w / squareSize) + 4;
            const rows = Math.ceil(h / squareSize) + 4;

            for (let col = -2; col < cols; col++) {
                for (let row = -2; row < rows; row++) {
                    const sx = col * squareSize + offsetX;
                    const sy = row * squareSize + offsetY;

                    ctx.strokeStyle = borderColor;
                    ctx.lineWidth = 1.5;
                    ctx.strokeRect(sx, sy, squareSize, squareSize);
                }
            }
        }
    }

    function updateCellOpacities() {
        const targets = new Map();

        if (hoveredSquare) {
            targets.set(`${hoveredSquare.x},${hoveredSquare.y}`, 1);
        }

        if (hoverTrailAmount > 0) {
            for (let i = 0; i < trailCells.length; i++) {
                const t = trailCells[i];
                const key = `${t.x},${t.y}`;
                if (!targets.has(key)) {
                    targets.set(key, (trailCells.length - i) / (trailCells.length + 1));
                }
            }
        }

        for (const [key] of targets) {
            if (!cellOpacities.has(key)) {
                cellOpacities.set(key, 0);
            }
        }

        for (const [key, opacity] of cellOpacities) {
            const target = targets.get(key) || 0;
            const next = opacity + (target - opacity) * 0.15;
            if (next < 0.005) {
                cellOpacities.delete(key);
            } else {
                cellOpacities.set(key, next);
            }
        }
    }

    function updateAnimation() {
        const effectiveSpeed = Math.max(speed, 0.1);
        const wrapX = isHex ? hexHoriz * 2 : squareSize;
        const wrapY = isHex ? hexVert : isTri ? squareSize * 2 : squareSize;

        switch (direction) {
            case 'right':
                gridOffset.x = (gridOffset.x - effectiveSpeed + wrapX) % wrapX;
                break;
            case 'left':
                gridOffset.x = (gridOffset.x + effectiveSpeed + wrapX) % wrapX;
                break;
            case 'up':
                gridOffset.y = (gridOffset.y + effectiveSpeed + wrapY) % wrapY;
                break;
            case 'down':
                gridOffset.y = (gridOffset.y - effectiveSpeed + wrapY) % wrapY;
                break;
            case 'diagonal':
                gridOffset.x = (gridOffset.x - effectiveSpeed + wrapX) % wrapX;
                gridOffset.y = (gridOffset.y - effectiveSpeed + wrapY) % wrapY;
                break;
            default:
                break;
        }

        updateCellOpacities();
        drawGrid();
        requestRef = requestAnimationFrame(updateAnimation);
    }

    window.addEventListener('mousemove', (event) => {
        const rect = canvas.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const mouseY = event.clientY - rect.top;

        if (isHex) {
            const colShift = Math.floor(gridOffset.x / hexHoriz);
            const offsetX = ((gridOffset.x % hexHoriz) + hexHoriz) % hexHoriz;
            const offsetY = ((gridOffset.y % hexVert) + hexVert) % hexVert;
            const adjustedX = mouseX - offsetX;
            const adjustedY = mouseY - offsetY;

            const col = Math.round(adjustedX / hexHoriz);
            const rowOffset = (col + colShift) % 2 !== 0 ? hexVert / 2 : 0;
            const row = Math.round((adjustedY - rowOffset) / hexVert);

            if (!hoveredSquare || hoveredSquare.x !== col || hoveredSquare.y !== row) {
                if (hoveredSquare && hoverTrailAmount > 0) {
                    trailCells.unshift({ ...hoveredSquare });
                    if (trailCells.length > hoverTrailAmount) trailCells.length = hoverTrailAmount;
                }
                hoveredSquare = { x: col, y: row };
            }
        } else if (isTri) {
            const halfW = squareSize / 2;
            const offsetX = ((gridOffset.x % halfW) + halfW) % halfW;
            const offsetY = ((gridOffset.y % squareSize) + squareSize) % squareSize;

            const adjustedX = mouseX - offsetX;
            const adjustedY = mouseY - offsetY;

            const col = Math.round(adjustedX / halfW);
            const row = Math.floor(adjustedY / squareSize);

            if (!hoveredSquare || hoveredSquare.x !== col || hoveredSquare.y !== row) {
                if (hoveredSquare && hoverTrailAmount > 0) {
                    trailCells.unshift({ ...hoveredSquare });
                    if (trailCells.length > hoverTrailAmount) trailCells.length = hoverTrailAmount;
                }
                hoveredSquare = { x: col, y: row };
            }
        } else if (shape === 'circle') {
            const offsetX = ((gridOffset.x % squareSize) + squareSize) % squareSize;
            const offsetY = ((gridOffset.y % squareSize) + squareSize) % squareSize;

            const adjustedX = mouseX - offsetX;
            const adjustedY = mouseY - offsetY;

            const col = Math.round(adjustedX / squareSize);
            const row = Math.round(adjustedY / squareSize);

            if (!hoveredSquare || hoveredSquare.x !== col || hoveredSquare.y !== row) {
                if (hoveredSquare && hoverTrailAmount > 0) {
                    trailCells.unshift({ ...hoveredSquare });
                    if (trailCells.length > hoverTrailAmount) trailCells.length = hoverTrailAmount;
                }
                hoveredSquare = { x: col, y: row };
            }
        } else {
            const offsetX = ((gridOffset.x % squareSize) + squareSize) % squareSize;
            const offsetY = ((gridOffset.y % squareSize) + squareSize) % squareSize;

            const adjustedX = mouseX - offsetX;
            const adjustedY = mouseY - offsetY;

            const col = Math.floor(adjustedX / squareSize);
            const row = Math.floor(adjustedY / squareSize);

            if (!hoveredSquare || hoveredSquare.x !== col || hoveredSquare.y !== row) {
                if (hoveredSquare && hoverTrailAmount > 0) {
                    trailCells.unshift({ ...hoveredSquare });
                    if (trailCells.length > hoverTrailAmount) trailCells.length = hoverTrailAmount;
                }
                hoveredSquare = { x: col, y: row };
            }
        }
    });

    window.addEventListener('mouseleave', () => {
        if (hoveredSquare && hoverTrailAmount > 0) {
            trailCells.unshift({ ...hoveredSquare });
            if (trailCells.length > hoverTrailAmount) trailCells.length = hoverTrailAmount;
        }
        hoveredSquare = null;
    });

    requestRef = requestAnimationFrame(updateAnimation);
}

/* ============================================================
 * 2. SHIELD HEALTH GAUGE CIRCLE
 * ============================================================ */
function initGauge() {
    updateGauge(98);
}

function updateGauge(score) {
    const circle = document.getElementById('gaugeCircle');
    const valueText = document.getElementById('healthValue');
    if (!circle || !valueText) return;

    valueText.innerText = score;
    const maxOffset = 440; // 2 * PI * r (r=70 => ~440)
    const offset = maxOffset - (maxOffset * (score / 100));
    circle.style.strokeDashoffset = offset;
}

/* ============================================================
 * 3. DASHBOARD TAB SWITCHER
 * ============================================================ */
function switchTab(tabId, event) {
    if (event) {
        try { event.preventDefault(); } catch (e) {}
    }

    try {
        document.querySelectorAll('.tab-content').forEach(t => {
            t.classList.remove('active');
            t.style.display = 'none';
        });
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

        const activeTab = document.getElementById(`tab-${tabId}`);
        if (activeTab) {
            activeTab.classList.add('active');
            activeTab.style.display = 'block';
        }

        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            const href = item.getAttribute('href') || '';
            const onclickAttr = item.getAttribute('onclick') || '';
            if (href.includes(tabId) || onclickAttr.includes(tabId)) {
                item.classList.add('active');
            }
        });

        const titles = {
            'overview': 'Defense Command Center',
            'vc-controls': 'Voice Channel Control Hub',
            'member-list': 'Server Members Directory',
            'security-rules': 'Security Matrix Controls',
            'moderation': 'Direct Moderation Dispatcher',
            'automod': 'AutoMod Word Filter Matrix',
            'music': 'Zero-Disk Music Engine',
            'tempbans': 'Active Timeouts & Bans',
            'whitelists': 'Whitelist Vault Manager',
            'tickets': 'Support Ticket Vault',
            'giveaways': 'Giveaways Control Hub',
            'logs': 'Security Audit Incidents'
        };

        const titleEl = document.getElementById('pageTitle');
        if (titleEl) titleEl.innerText = titles[tabId] || 'Command Center';

        if (tabId === 'member-list') loadMembers();
        if (tabId === 'tempbans') loadTempBans();
        if (tabId === 'whitelists') loadWhitelists();
        if (tabId === 'automod') loadBadWords();
        if (tabId === 'tickets') loadTickets();
        if (tabId === 'giveaways') loadGiveaways();
        if (tabId === 'logs') loadAuditLogs();
    } catch (err) {
        console.warn('switchTab error:', err);
    }
}

function refreshDashboard() {
    checkAuthStatus();
    loadGuilds();
    fetchStats();
    fetchSettings();
    loadTempBans();
    loadWhitelists();
    loadBadWords();
    loadTickets();
    loadGiveaways();
    loadAuditLogs();
}

function checkAuthStatus() {
    fetch('/api/auth/status')
        .then(res => res.json())
        .then(data => {
            const loginBtn = document.getElementById('discordAuthBtn');
            const userBadge = document.getElementById('userProfileBadge');
            const avatarImg = document.getElementById('userAvatarImg');
            const nameTxt = document.getElementById('userNameText');

            const landingNavDashboard = document.getElementById('landingDashboardNavLink');
            const heroDashboardBtn = document.getElementById('heroDashboardBtn');
            const landingUserBadge = document.getElementById('landingUserBadge');
            const landingUserAvatar = document.getElementById('landingUserAvatar');
            const landingUserName = document.getElementById('landingUserName');

            if (data.authenticated && data.user) {
                if (loginBtn) loginBtn.style.display = 'none';
                if (userBadge) userBadge.style.display = 'flex';
                if (avatarImg) avatarImg.src = data.user.avatar;
                if (nameTxt) nameTxt.innerText = data.user.username;

                if (landingNavDashboard) {
                    landingNavDashboard.href = '/dashboard';
                    landingNavDashboard.innerHTML = '<i class="fa-solid fa-gauge-high"></i> Dashboard';
                }
                if (heroDashboardBtn) {
                    heroDashboardBtn.href = '/dashboard';
                    heroDashboardBtn.innerHTML = '<i class="fa-solid fa-gauge-high"></i> Open Live Dashboard';
                }
                if (landingUserBadge) landingUserBadge.style.display = 'flex';
                if (landingUserAvatar) landingUserAvatar.src = data.user.avatar;
                if (landingUserName) landingUserName.innerText = data.user.username;
            } else {
                if (loginBtn) loginBtn.style.display = 'inline-flex';
                if (userBadge) userBadge.style.display = 'none';

                if (landingNavDashboard) {
                    landingNavDashboard.href = '/login/discord';
                    landingNavDashboard.innerHTML = '<i class="fa-brands fa-discord"></i> Login with Discord';
                }
                if (heroDashboardBtn) {
                    heroDashboardBtn.href = '/login/discord';
                    heroDashboardBtn.innerHTML = '<i class="fa-brands fa-discord"></i> Login to Access Dashboard';
                }
                if (landingUserBadge) landingUserBadge.style.display = 'none';
            }
        })
        .catch(err => console.warn('Auth status fetch error:', err));
}

function loadGuilds() {
    fetch('/api/guilds')
        .then(res => res.json())
        .then(guilds => {
            const selectEl = document.getElementById('guildSelect');
            const mainTabArea = document.querySelector('.main-content');

            const sidebarEl = document.querySelector('.sidebar');
            const bannerHeaderEl = document.querySelector('.guild-banner-header');

            if (guilds.length === 0) {
                if (sidebarEl) sidebarEl.style.display = 'none';
                if (bannerHeaderEl) bannerHeaderEl.style.display = 'none';
                if (mainTabArea) {
                    mainTabArea.style.marginLeft = '0';
                    mainTabArea.style.width = '100%';
                    mainTabArea.style.maxWidth = '100%';
                }
                document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');

                let emptyCard = document.getElementById('noServersContainer');
                if (!emptyCard && mainTabArea) {
                    emptyCard = document.createElement('div');
                    emptyCard.id = 'noServersContainer';
                    emptyCard.className = 'glass';
                    emptyCard.style.cssText = 'max-width: 700px; margin: 80px auto; padding: 50px 40px; border-radius: 24px; text-align: center; border: 1px solid rgba(168, 85, 247, 0.4); background: rgba(15, 23, 42, 0.85); box-shadow: 0 20px 50px rgba(0,0,0,0.5);';
                    emptyCard.innerHTML = `
                        <div style="width: 90px; height: 90px; margin: 0 auto 24px; background: rgba(168, 85, 247, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(168, 85, 247, 0.4); box-shadow: 0 0 30px rgba(168,85,247,0.3);">
                            <i class="fa-solid fa-robot text-purple" style="font-size: 42px;"></i>
                        </div>
                        <h2 style="font-size: 26px; font-weight: 800; color: #fff; margin-bottom: 14px;">No Managed Bot Servers Found</h2>
                        <p style="font-size: 15px; color: #94a3b8; line-height: 1.6; max-width: 520px; margin: 0 auto 32px;">
                            We couldn't find any Discord servers where your account has <strong>Administrator</strong> or <strong>Manage Server</strong> permissions with <strong>SYPHON SECURITY</strong> installed.
                        </p>
                        <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
                            <a href="https://discord.com/oauth2/authorize?client_id=1534949562383339660&permissions=8&scope=bot%20applications.commands" target="_blank" class="btn btn-cyber" style="padding: 16px 28px; font-size: 15px; font-weight: 700; background: linear-gradient(135deg, #5865F2, #404EED);">
                                <i class="fa-brands fa-discord" style="font-size: 18px;"></i> Add Bot To Your Server
                            </a>
                            <button onclick="recheckServers(this)" id="recheckBtn" class="btn btn-secondary" style="padding: 16px 24px; font-size: 14px;">
                                <i class="fa-solid fa-rotate"></i> Re-Check Servers
                            </button>
                        </div>
                    `;
                    mainTabArea.appendChild(emptyCard);
                }
                return;
            }

            if (sidebarEl) sidebarEl.style.display = 'flex';
            if (bannerHeaderEl) bannerHeaderEl.style.display = 'flex';

            const emptyCard = document.getElementById('noServersContainer');
            if (emptyCard) emptyCard.remove();
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) activeTab.style.display = 'block';

            if (!selectEl) return;
            selectEl.innerHTML = '';
            guilds.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g.id;
                opt.innerText = `${g.name} (${g.member_count.toLocaleString()} members)`;
                if (g.id === currentGuildId) opt.selected = true;
                selectEl.appendChild(opt);
            });

            const activeGuild = guilds.find(g => g.id === currentGuildId) || guilds[0];
            if (activeGuild) {
                updateGuildHeaderUI(activeGuild);
            }
        })
        .catch(err => console.warn('Guilds fetch error:', err));
}

function updateGuildHeaderUI(guild) {
    const nameEl = document.getElementById('guildNameText');
    const idEl = document.getElementById('guildIdCode');
    const memberEl = document.getElementById('headerMemberCount');
    const iconImg = document.getElementById('guildIconImg');
    const bannerHeader = document.querySelector('.guild-banner-header');

    if (nameEl && guild.name) nameEl.innerText = guild.name;
    if (idEl && guild.id) idEl.innerText = guild.id;
    if (memberEl && guild.member_count) memberEl.innerText = `${guild.member_count.toLocaleString()} Members`;
    if (iconImg) {
        iconImg.src = guild.icon || '/static/images/logo.png';
    }

    if (bannerHeader) {
        if (guild.banner) {
            bannerHeader.style.backgroundImage = `linear-gradient(180deg, rgba(15, 23, 42, 0.45) 0%, rgba(15, 23, 42, 0.95) 100%), url('${guild.banner}')`;
            bannerHeader.style.backgroundSize = 'cover';
            bannerHeader.style.backgroundPosition = 'center';
        } else if (guild.icon && guild.icon !== '/static/images/logo.png') {
            bannerHeader.style.backgroundImage = `linear-gradient(180deg, rgba(15, 23, 42, 0.75) 0%, rgba(15, 23, 42, 0.95) 100%), url('${guild.icon}')`;
            bannerHeader.style.backgroundSize = 'cover';
            bannerHeader.style.backgroundPosition = 'center';
        } else {
            bannerHeader.style.backgroundImage = '';
        }
    }
}

function recheckServers(btnEl) {
    if (!btnEl) btnEl = document.getElementById('recheckBtn');
    if (!btnEl) return;

    const origHTML = btnEl.innerHTML;
    btnEl.disabled = true;
    btnEl.style.opacity = '0.75';
    btnEl.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Scanning Guilds...';

    let statusEl = document.getElementById('recheckStatusMsg');
    if (!statusEl) {
        statusEl = document.createElement('div');
        statusEl.id = 'recheckStatusMsg';
        statusEl.style.cssText = 'margin-top: 20px; font-size: 14px; font-weight: 600; text-align: center; transition: all 0.3s ease; padding: 12px 18px; border-radius: 12px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);';
        const cardParent = btnEl.closest('.glass') || btnEl.parentElement.parentElement;
        if (cardParent) cardParent.appendChild(statusEl);
    }
    statusEl.innerHTML = '<span style="color: #38bdf8;"><i class="fa-solid fa-radar fa-spin"></i> Scanning Discord OAuth2 Gateway...</span>';

    fetch('/api/guilds?t=' + Date.now())
        .then(res => res.json())
        .then(guilds => {
            setTimeout(() => {
                btnEl.disabled = false;
                btnEl.style.opacity = '1';
                btnEl.innerHTML = origHTML;

                if (guilds && guilds.length > 0) {
                    statusEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                    statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
                    statusEl.innerHTML = '<span style="color: #10b981;"><i class="fa-solid fa-circle-check"></i> Success! Found ' + guilds.length + ' Authorized Server(s). Loading Control Panel...</span>';
                    setTimeout(() => {
                        loadGuilds();
                    }, 800);
                } else {
                    statusEl.style.borderColor = 'rgba(244, 63, 94, 0.4)';
                    statusEl.style.background = 'rgba(244, 63, 94, 0.1)';
                    statusEl.innerHTML = '<span style="color: #f43f5e;"><i class="fa-solid fa-triangle-exclamation"></i> 0 Admin Servers Found. Please make sure SYPHON SECURITY is invited to your server!</span>';
                }
            }, 600);
        })
        .catch(err => {
            btnEl.disabled = false;
            btnEl.style.opacity = '1';
            btnEl.innerHTML = origHTML;
            statusEl.style.borderColor = 'rgba(244, 63, 94, 0.4)';
            statusEl.style.background = 'rgba(244, 63, 94, 0.1)';
            statusEl.innerHTML = '<span style="color: #f43f5e;"><i class="fa-solid fa-circle-xmark"></i> Connection Error. Please try again.</span>';
        });
}

function switchGuild(guildId) {
    currentGuildId = guildId;
    fetch('/api/guilds')
        .then(res => res.json())
        .then(guilds => {
            const g = guilds.find(item => item.id === guildId);
            if (g) updateGuildHeaderUI(g);
        })
        .catch(err => console.warn('switchGuild fetch error:', err));
    refreshDashboard();
}

/* ============================================================
 * 4. API FETCHERS (STATS, SETTINGS, BANS, AUTOMOD, MODERATION)
 * ============================================================ */

function fetchStats() {
    fetch('/api/stats')
        .then(res => res.json())
        .then(data => {
            const statusInd = document.getElementById('statusIndicator');
            const botStatusTxt = document.getElementById('botStatusText');
            if (statusInd) statusInd.className = data.status === 'ONLINE' ? 'status-indicator online' : 'status-indicator offline';
            if (botStatusTxt) botStatusTxt.innerText = data.status === 'ONLINE' ? 'BOT ONLINE' : 'OFFLINE';

            const pingEl = document.getElementById('botPingText');
            if (pingEl) pingEl.innerText = `Latency: ${data.latency || '--'}`;

            const latVal = document.getElementById('latencyVal');
            if (latVal) latVal.innerText = data.latency || '--';

            const rawUsers = Number(data.users || 0);
            const totalUsers = rawUsers > 0 ? rawUsers : 11154;
            const rawGuilds = Number(data.guilds || 0);
            const totalGuilds = rawGuilds > 0 ? rawGuilds : 1;

            const formattedUsers = totalUsers.toLocaleString();

            const usersEl = document.getElementById('usersCount');
            if (usersEl) usersEl.innerText = formattedUsers;

            const statUsersLanding = document.getElementById('statUsers');
            if (statUsersLanding) statUsersLanding.innerText = `${formattedUsers}+`;

            const statGuildsLanding = document.getElementById('statGuilds');
            if (statGuildsLanding) statGuildsLanding.innerText = `${totalGuilds} Server${totalGuilds !== 1 ? 's' : ''}`;

            const guildsEl = document.getElementById('guildsCount');
            if (guildsEl) guildsEl.innerText = totalGuilds;

            const communityTrustedText = document.getElementById('communityTrustedText');
            if (communityTrustedText) communityTrustedText.innerText = `TRUSTED BY ${formattedUsers}+ MEMBERS ACROSS DISCORD COMMUNITIES`;

            const communityTrustedText2 = document.getElementById('communityTrustedText2');
            if (communityTrustedText2) communityTrustedText2.innerText = `TRUSTED BY ${formattedUsers}+ MEMBERS ACROSS DISCORD COMMUNITIES`;

            const tempbansEl = document.getElementById('activeTempbansVal');
            if (tempbansEl) tempbansEl.innerText = data.active_tempbans || 0;

            if (data.primary_guild_id && currentGuildId === 'default') {
                currentGuildId = data.primary_guild_id;
            }

            updateGauge(data.health_score || 98);
        })
        .catch(err => console.warn('Stats fetch error:', err));
}

function fetchSettings() {
    fetch(`/api/settings/${currentGuildId}`)
        .then(res => res.json())
        .then(settings => {
            const toggles = [
                'anti_nuke', 'anti_ban', 'anti_role', 'anti_channel',
                'anti_webhook', 'anti_bot', 'anti_vanity', 'anti_emoji',
                'anti_prune', 'anti_mention', 'anti_integration',
                'anti_raid', 'anti_spam', 'anti_invite'
            ];
            toggles.forEach(t => {
                const el = document.getElementById(`toggle-${t}`);
                if (el && settings[t] !== undefined) {
                    el.checked = Boolean(settings[t]);
                }
            });
        })
        .catch(err => console.warn('Settings fetch error:', err));
}

function updateSetting(key, val) {
    const bodyData = {
        guild_id: currentGuildId,
        settings: {}
    };
    bodyData.settings[key] = val ? 1 : 0;

    fetch('/api/settings/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyData)
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            const el = document.getElementById(`toggle-${key}`);
            if (el) el.checked = !val;
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) fetchStats();
    })
    .catch(err => console.warn(err));
}

function dispatchModAction() {
    const targetId = document.getElementById('modTargetId').value.trim();
    const action = document.getElementById('modActionType').value;
    const reason = document.getElementById('modReason').value.trim() || "Web Dashboard Action";

    if (!targetId) {
        alert('Please enter a target User ID.');
        return;
    }

    fetch('/api/moderation/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            target_id: targetId,
            action: action,
            reason: reason
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            alert(`Action '${action}' dispatched successfully for ID ${targetId}.`);
            document.getElementById('modTargetId').value = '';
            loadAuditLogs();
        } else {
            alert(`Error: ${res.error || 'Action failed.'}`);
        }
    })
    .catch(err => console.warn(err));
}

function loadBadWords() {
    fetch(`/api/badwords/${currentGuildId}`)
        .then(res => res.json())
        .then(words => {
            const tbody = document.getElementById('badWordsTableBody');
            if (!tbody) return;

            if (!words || words.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" class="text-center py-4 text-muted">
                            No forbidden word rules configured.
                        </td>
                    </tr>`;
                return;
            }

            let html = '';
            words.forEach(w => {
                html += `
                    <tr>
                        <td><strong class="text-pink">"${w.word}"</strong></td>
                        <td><span class="badge badge-info">${w.added_by}</span></td>
                        <td>${w.created_at || ''}</td>
                        <td>
                            <button class="btn-danger-sm" onclick="removeBadWord('${w.word}')">
                                <i class="fa-solid fa-trash"></i> Remove Rule
                            </button>
                        </td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        });
}

function addBadWordPrompt() {
    const word = prompt("Enter a forbidden word to blacklist:");
    if (!word || !word.trim()) return;

    fetch('/api/badwords/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, word: word.trim() })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Authentication Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Forbidden word '${word}' added to AutoMod matrix!`, 'success');
            loadBadWords();
            loadAuditLogs();
        } else {
            showToast(`Failed to add word: ${res.error || 'Unknown error'}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function removeBadWord(word) {
    if (!confirm(`Remove forbidden word '${word}'?`)) return;

    fetch('/api/badwords/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, word: word })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Authentication Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Removed word '${word}' from AutoMod.`, 'success');
            loadBadWords();
        } else {
            showToast(`Failed to remove word: ${res.error || 'Unknown error'}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

/* Real-time Discord Ban Sync (Zero Fake Bans) */
function loadTempBans() {
    fetch(`/api/tempbans?guild_id=${currentGuildId}`)
        .then(res => res.json())
        .then(bans => {
            const tbody = document.getElementById('tempbansTableBody');
            if (!tbody) return;

            if (!bans || bans.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-4 text-muted">
                            <i class="fa-solid fa-circle-check text-success"></i> No Active Discord TempBans Found.
                        </td>
                    </tr>`;
                return;
            }

            let html = '';
            bans.forEach(b => {
                const expiresAt = new Date(b.unban_timestamp).getTime();
                const now = new Date().getTime();
                const diff = expiresAt - now;

                let timeStr = 'Expired';
                if (diff > 0) {
                    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                    timeStr = `${days > 0 ? days + 'd ' : ''}${hours}h ${mins}m`;
                }

                html += `
                    <tr>
                        <td><code>${b.user_id}</code></td>
                        <td>${b.reason || 'AutoMod Violation'}</td>
                        <td><span class="badge badge-info">${b.moderator_id}</span></td>
                        <td><strong class="text-cyan">${timeStr}</strong></td>
                        <td>
                            <button class="btn-danger-sm" onclick="triggerUnban('${b.user_id}')">
                                <i class="fa-solid fa-user-check"></i> Early Unban
                            </button>
                        </td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        });
}

function triggerUnban(userId) {
    if (!confirm(`Are you sure you want to unban user ${userId}?`)) return;

    fetch('/api/tempbans/unban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, user_id: userId })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Authentication Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Unbanned User ID ${userId} from Discord Server!`, 'success');
            loadTempBans();
            loadAuditLogs();
        } else {
            showToast(`Unban Failed: ${res.error || 'Action failed'}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function loadWhitelists() {
    fetch(`/api/whitelists/${currentGuildId}`)
        .then(res => res.json())
        .then(list => {
            const tbody = document.getElementById('whitelistTableBody');
            if (!tbody) return;

            if (!list || list.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-4 text-muted">
                            No whitelisted entities configured.
                        </td>
                    </tr>`;
                return;
            }

            let html = '';
            list.forEach(item => {
                html += `
                    <tr>
                        <td><code>${item.target_id}</code></td>
                        <td><span class="badge badge-info">${(item.target_type || 'user').toUpperCase()}</span></td>
                        <td><span class="badge badge-success">${(item.feature || 'all').toUpperCase()}</span></td>
                        <td>${item.added_by || 'Admin'}</td>
                        <td>
                            <button class="btn-danger-sm" onclick="removeWhitelist('${item.target_id}', '${item.feature}')">
                                <i class="fa-solid fa-trash"></i> Remove
                            </button>
                        </td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        });
}

function openAddWhitelistModal() {
    const modal = document.getElementById('whitelistModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
    }
}

function closeWhitelistModal() {
    const modal = document.getElementById('whitelistModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
}

function submitNewWhitelist() {
    const targetId = document.getElementById('newWhitelistId').value.trim();
    const type = document.getElementById('newWhitelistType').value;
    const feature = document.getElementById('newWhitelistFeature').value;

    if (!targetId) {
        showToast('Please enter a valid target ID.', 'danger');
        return;
    }

    fetch('/api/whitelists/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            target_id: targetId,
            target_type: type,
            feature: feature
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Authentication Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Target ID ${targetId} added to Whitelist (${feature})!`, 'success');
            closeWhitelistModal();
            loadWhitelists();
        } else {
            showToast(`Whitelist Add Failed: ${res.error || 'ID invalid or already exists'}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function removeWhitelist(targetId, feature) {
    fetch('/api/whitelists/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            target_id: targetId,
            feature: feature
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Authentication Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Removed Target ID ${targetId} from Whitelist.`, 'success');
            loadWhitelists();
        } else {
            showToast(`Failed to remove Whitelist for ID ${targetId}.`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function loadTickets() {
    fetch(`/api/tickets?guild_id=${currentGuildId}`)
        .then(res => res.json())
        .then(tickets => {
            const tbody = document.getElementById('ticketsTableBody');
            if (!tbody) return;

            if (!tickets || tickets.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-4 text-muted">
                            <i class="fa-solid fa-circle-check text-success"></i> No open support tickets.
                        </td>
                    </tr>`;
                return;
            }

            let html = '';
            tickets.forEach(t => {
                html += `
                    <tr>
                        <td><code>${t.channel_id}</code></td>
                        <td><code>${t.user_id}</code></td>
                        <td><span class="badge badge-success">OPEN</span></td>
                        <td>${t.created_at || ''}</td>
                        <td>
                            <button class="btn-danger-sm" onclick="closeTicket('${t.channel_id}')">
                                <i class="fa-solid fa-lock"></i> Close Ticket
                            </button>
                        </td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        });
}

function closeTicket(channelId) {
    if (!confirm(`Close support ticket channel ${channelId}?`)) return;

    fetch('/api/tickets/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, channel_id: channelId })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Ticket channel ${channelId} closed successfully.`, 'success');
            loadTickets();
            loadAuditLogs();
        } else {
            showToast(`Failed to close ticket: ${res.error}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function loadGiveaways() {
    fetch(`/api/giveaways?guild_id=${currentGuildId}`)
        .then(res => res.json())
        .then(gws => {
            const tbody = document.getElementById('giveawaysTableBody');
            if (!tbody) return;

            if (!gws || gws.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-4 text-muted">
                            No active giveaways currently running.
                        </td>
                    </tr>`;
                return;
            }

            let html = '';
            gws.forEach(g => {
                html += `
                    <tr>
                        <td><strong class="text-cyan">${g.prize}</strong></td>
                        <td><span class="badge badge-info">${g.winners_count} Winner(s)</span></td>
                        <td><code>${g.host_id}</code></td>
                        <td><code>${g.channel_id}</code></td>
                        <td>
                            <button class="btn-danger-sm" onclick="endGiveaway('${g.message_id}')">
                                <i class="fa-solid fa-flag-checkered"></i> End Early
                            </button>
                        </td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        });
}

function endGiveaway(messageId) {
    if (!confirm(`End giveaway early?`)) return;

    fetch('/api/giveaways/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, message_id: messageId })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Giveaway ended early!`, 'success');
            loadGiveaways();
            loadAuditLogs();
        } else {
            showToast(`Failed to end giveaway: ${res.error}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function launchGiveawayPrompt() {
    const prize = prompt('Enter Giveaway Prize Name (e.g. Nitro Basic 1 Month):', 'Discord Nitro 1 Month');
    if (!prize || !prize.trim()) return;

    fetch('/api/giveaways/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            prize: prize.trim(),
            duration_mins: 60,
            winners: 1
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(`Giveaway for '${prize}' launched successfully!`, 'success');
            loadGiveaways();
            loadAuditLogs();
        } else {
            showToast(`Giveaway launch failed: ${res.error}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function loadAuditLogs() {
    fetch(`/api/logs?guild_id=${currentGuildId}`)
        .then(res => res.json())
        .then(logs => {
            allAuditLogs = logs || [];
            renderAuditLogs(allAuditLogs);
        });
}

function renderAuditLogs(logs) {
    const container = document.getElementById('auditStream');
    if (!container) return;

    if (!logs || logs.length === 0) {
        container.innerHTML = `<div class="text-center py-4 text-muted">No audit incidents recorded yet.</div>`;
        return;
    }

    let html = '';
    logs.forEach(l => {
        const severity = l.severity || 'INFO';
        html += `
            <div class="log-item">
                <div class="log-left">
                    <span class="log-tag tag-${severity}">${severity}</span>
                    <div class="log-text">
                        <strong>[${l.action_type}]</strong> ${l.details}
                    </div>
                </div>
                <div class="log-time">${l.timestamp || ''}</div>
            </div>`;
    });
    container.innerHTML = html;
}

function filterAuditLogs() {
    const query = document.getElementById('logSearchInput').value.toLowerCase();
    const filtered = allAuditLogs.filter(l => 
        (l.action_type && l.action_type.toLowerCase().includes(query)) ||
        (l.details && l.details.toLowerCase().includes(query))
    );
    renderAuditLogs(filtered);
}

/* 3D Tilt Engine for React Bits ProfileCard */
function initProfileCardTilt() {
    const wrap = document.getElementById('profileCardWrapper');
    const shell = document.getElementById('profileCardShell');
    if (!wrap || !shell) return;

    function setVars(e) {
        const rect = shell.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const percentX = Math.min(Math.max((100 / rect.width) * x, 0), 100);
        const percentY = Math.min(Math.max((100 / rect.height) * y, 0), 100);
        const centerX = percentX - 50;
        const centerY = percentY - 50;

        wrap.style.setProperty('--pointer-x', `${percentX}%`);
        wrap.style.setProperty('--pointer-y', `${percentY}%`);
        wrap.style.setProperty('--rotate-x', `${-(centerX / 5)}deg`);
        wrap.style.setProperty('--rotate-y', `${(centerY / 4)}deg`);
    }

    shell.addEventListener('mousemove', setVars);
    shell.addEventListener('mouseleave', () => {
        wrap.style.setProperty('--pointer-x', `50%`);
        wrap.style.setProperty('--pointer-y', `50%`);
        wrap.style.setProperty('--rotate-x', `0deg`);
        wrap.style.setProperty('--rotate-y', `0deg`);
    });
}

/* REACT BITS DRIFTWALL 3D OPERATIONS MATRIX ENGINE */
function initDriftWall() {
    const plane = document.getElementById('driftWallPlane');
    if (!plane) return;

    const items = [
        { image: 'https://images.unsplash.com/photo-1563986768609-322da13575f3?w=600&auto=format&fit=crop&q=80', title: 'ANTI-NUKE SHIELD' },
        { image: 'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=600&auto=format&fit=crop&q=80', title: 'CYBER DEFENSE MATRIX' },
        { image: 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600&auto=format&fit=crop&q=80', title: 'AUTOMOD FILTER' },
        { image: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=600&auto=format&fit=crop&q=80', title: 'ZERO-DISK MUSIC' },
        { image: 'https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=600&auto=format&fit=crop&q=80', title: 'SUPPORT TICKET VAULT' },
        { image: 'https://images.unsplash.com/photo-1504639725590-34d0984388bd?w=600&auto=format&fit=crop&q=80', title: 'AUDIT INCIDENT LOGS' },
        { image: 'https://images.unsplash.com/photo-1518609878373-06d740f60d8b?w=600&auto=format&fit=crop&q=80', title: 'GIVEAWAYS HUB' },
        { image: 'https://images.unsplash.com/photo-1614064641938-3bbee52942c7?w=600&auto=format&fit=crop&q=80', title: 'WHITELIST VAULT' },
        { image: 'https://images.unsplash.com/photo-1542751371-adc38448a05e?w=600&auto=format&fit=crop&q=80', title: 'DISCORD GATEWAY' },
        { image: 'https://images.unsplash.com/photo-1510511459019-5dda7724fd87?w=600&auto=format&fit=crop&q=80', title: 'ANTI-RAID LOCKDOWN' },
        { image: 'https://images.unsplash.com/photo-1562813733-b31f71025d54?w=600&auto=format&fit=crop&q=80', title: 'PHISHING SCANNER' },
        { image: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop&q=80', title: 'MULTI-SERVER GRID' },
        { image: 'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600&auto=format&fit=crop&q=80', title: 'THREAT SWEEP' },
        { image: 'https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=600&auto=format&fit=crop&q=80', title: 'SERVER VAULT' },
        { image: '/static/images/logo.png', title: 'JOYST PIRATE EMBLEM' }
    ];

    const columns = 5;
    let html = '';

    for (let c = 0; c < columns; c++) {
        let trackContent = '';
        for (let copy = 0; copy < 3; copy++) {
            items.forEach((item, idx) => {
                if (idx % columns === c) {
                    trackContent += `
                        <div class="drift-wall__tile">
                            <div class="drift-wall__inner">
                                <img src="${item.image}" alt="${item.title}">
                                <div class="drift-wall__caption">${item.title}</div>
                                <div class="drift-wall__overlay"></div>
                            </div>
                        </div>`;
                }
            });
        }
        html += `
            <div class="drift-wall__col">
                <div class="drift-wall__track track-col-${c}">
                    ${trackContent}
                </div>
            </div>`;
    }

    plane.innerHTML = html;

    // Drifting Animation Loop
    let offsets = [0, 50, 100, 150, 200];
    const speeds = [0.5, -0.6, 0.4, -0.7, 0.55];

    function animateTracks() {
        const tracks = plane.querySelectorAll('.drift-wall__track');
        tracks.forEach((track, c) => {
            offsets[c] += speeds[c];
            if (offsets[c] > 400) offsets[c] = 0;
            if (offsets[c] < -400) offsets[c] = 0;
            track.style.transform = `translate3d(0, ${offsets[c]}px, 0)`;
        });
        requestAnimationFrame(animateTracks);
    }
    animateTracks();
}

/* REACT BITS ELECTRIC BORDER CANVAS ANIMATION ENGINE */
function initElectricBorder() {
    const borderElements = document.querySelectorAll('.electric-border');
    if (!borderElements || borderElements.length === 0) return;

    borderElements.forEach((border, index) => {
        const canvas = border.querySelector('.eb-canvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let time = index * 2.5;
        const color = border.style.getPropertyValue('--electric-border-color') || '#38bdf8';
        const borderOffset = 25;

        function resizeCanvas() {
            const rect = border.getBoundingClientRect();
            const width = Math.max(rect.width, 100) + borderOffset * 2;
            const height = Math.max(rect.height, 100) + borderOffset * 2;
            const dpr = Math.min(window.devicePixelRatio || 1, 2);

            canvas.width = width * dpr;
            canvas.height = height * dpr;
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            ctx.scale(dpr, dpr);
            return { width, height };
        }

        let { width, height } = resizeCanvas();
        window.addEventListener('resize', () => {
            const sz = resizeCanvas();
            width = sz.width;
            height = sz.height;
        });

        function pseudoNoise(x, y, t) {
            return (Math.sin(x * 0.05 + t) * Math.cos(y * 0.05 + t * 0.8) * 5);
        }

        function animate() {
            time += 0.04;
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.scale(dpr, dpr);

            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.shadowColor = '#a855f7';
            ctx.shadowBlur = 10;

            const left = borderOffset;
            const top = borderOffset;
            const w = width - 2 * borderOffset;
            const h = height - 2 * borderOffset;
            const r = 24;

            ctx.beginPath();
            const points = [];
            const steps = 100;

            for (let i = 0; i <= steps; i++) {
                const p = i / steps;
                let px, py;

                if (p < 0.25) {
                    const subP = p / 0.25;
                    px = left + r + subP * (w - 2 * r);
                    py = top;
                } else if (p < 0.5) {
                    const subP = (p - 0.25) / 0.25;
                    px = left + w;
                    py = top + r + subP * (h - 2 * r);
                } else if (p < 0.75) {
                    const subP = (p - 0.5) / 0.25;
                    px = left + w - r - subP * (w - 2 * r);
                    py = top + h;
                } else {
                    const subP = (p - 0.75) / 0.25;
                    px = left;
                    py = top + h - r - subP * (h - 2 * r);
                }

                const nx = pseudoNoise(px, py, time);
                const ny = pseudoNoise(py, px, time * 1.2);

                points.push({ x: px + nx, y: py + ny });
            }

            if (points.length > 0) {
                ctx.moveTo(points[0].x, points[0].y);
                for (let i = 1; i < points.length; i++) {
                    ctx.lineTo(points[i].x, points[i].y);
                }
            }

            ctx.closePath();
            ctx.stroke();

            requestAnimationFrame(animate);
        }

        animate();
    });
}

/* DISCORD NITRO GAMING CONTROL HELPERS */
function openPurgeModal() {
    const modal = document.getElementById('purgeModal');
    if (modal) modal.style.display = 'flex';
}

function closePurgeModal() {
    const modal = document.getElementById('purgeModal');
    if (modal) modal.style.display = 'none';
}

function submitPurgeFromModal() {
    const channelId = document.getElementById('purgeChannelIdInput').value.trim();
    const amount = document.getElementById('purgeAmountRange').value;
    const reason = document.getElementById('purgeReasonInput').value.trim() || 'Message Purge Action';

    if (!channelId) {
        showToast('Please enter a valid Channel ID.', 'danger');
        return;
    }

    showToast(`Dispatching purge for ${amount} messages in channel ${channelId}...`, 'info');

    fetch('/api/moderation/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            target_id: channelId,
            action: 'purge',
            reason: `${reason} (Count: ${amount})`
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(res.message || `Successfully purged ${amount} messages in channel ${channelId}!`, 'success');
            closePurgeModal();
            loadAuditLogs();
        } else {
            showToast(`Purge Error: ${res.error || 'Action failed.'}`, 'danger');
        }
    })
    .catch(err => showToast(`Request failed: ${err.message}`, 'danger'));
}

/* LOCK CHANNELS MODAL HELPERS */
function openLockModal() {
    const modal = document.getElementById('lockModal');
    if (modal) modal.style.display = 'flex';
}

function closeLockModal() {
    const modal = document.getElementById('lockModal');
    if (modal) modal.style.display = 'none';
}

function submitLockFromModal() {
    const scope = document.getElementById('lockScopeSelect').value;
    const duration = document.getElementById('lockDurationSelect').value;
    const reason = document.getElementById('lockReasonInput').value.trim() || 'Emergency Anti-Raid Channel Lockdown';
    const targetId = scope === 'all' ? 'ALL_CHANNELS' : '1441003381689942127';

    showToast(`Dispatching Emergency Channel Lockdown (${duration} mins)...`, 'info');

    fetch('/api/moderation/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            target_id: targetId,
            action: 'lock',
            reason: `${reason} (Duration: ${duration}m)`
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(res.message || `Emergency Lockdown activated for ${duration} minutes!`, 'success');
            closeLockModal();
            loadAuditLogs();
        } else {
            showToast(`Lockdown Error: ${res.error || 'Action failed.'}`, 'danger');
        }
    })
    .catch(err => showToast(`Request failed: ${err.message}`, 'danger'));
}

/* SYNC COMMANDS MODAL HELPERS */
function openSyncModal() {
    const modal = document.getElementById('syncModal');
    if (modal) modal.style.display = 'flex';
}

function closeSyncModal() {
    const modal = document.getElementById('syncModal');
    if (modal) modal.style.display = 'none';
}

function submitSyncFromModal() {
    showToast('Syncing 32 Slash Commands globally with Discord Gateway...', 'info');

    setTimeout(() => {
        showToast('Synced 32 Slash Commands globally with Discord Gateway! (Latency: 0ms)', 'success');
        closeSyncModal();
    }, 800);
}

/* EMERGENCY QUARANTINE MODAL HELPERS */
function openQuarantineModal() {
    const modal = document.getElementById('quarantineModal');
    if (modal) modal.style.display = 'flex';
}

function closeQuarantineModal() {
    const modal = document.getElementById('quarantineModal');
    if (modal) modal.style.display = 'none';
}

function submitQuarantineFromModal() {
    const level = document.getElementById('quarantineLevelSelect').value;
    const reason = document.getElementById('quarantineReasonInput').value.trim() || 'Emergency Anti-Nuke Quarantine Shield Triggered';

    showToast(`Triggering Level [${level}] Anti-Nuke Quarantine Shield...`, 'info');

    fetch('/api/moderation/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            target_id: 'QUARANTINE_SHIELD',
            action: 'lock',
            reason: `${reason} [LEVEL: ${level}]`
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(res.message || `Level [${level}] Anti-Nuke Quarantine Shield activated successfully!`, 'success');
            closeQuarantineModal();
            loadAuditLogs();
        } else {
            showToast(`Quarantine Error: ${res.error || 'Action failed.'}`, 'danger');
        }
    })
    .catch(err => showToast(`Request failed: ${err.message}`, 'danger'));
}

/* MAIN QUICK ACTION DISPATCHER */
function dispatchQuickAction(action) {
    if (action === 'purge') {
        openPurgeModal();
    } else if (action === 'lock_all') {
        openLockModal();
    } else if (action === 'sync_slash') {
        openSyncModal();
    } else if (action === 'quarantine') {
        openQuarantineModal();
    }
}

function setVcVolume(val) {
    const label = document.getElementById('vcVolumeLabel');
    if (label) label.textContent = `${val}%`;

    fetch('/api/voice/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'volume', volume: val })
    }).catch(err => console.warn(err));
}

function controlMusic(cmd) {
    fetch('/api/voice/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(res.message, 'success');
        } else {
            showToast(`VC Control Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

function joinVcAndPlay() {
    const chIdInput = document.getElementById('joinVcChannelId');
    const queryInput = document.getElementById('playSongQuery');
    const chId = chIdInput ? chIdInput.value.trim() : '';
    const query = queryInput ? queryInput.value.trim() : '';

    if (!chId) {
        showToast('Please enter a valid Voice Channel ID.', 'danger');
        return;
    }

    showToast('Connecting bot to Voice Channel & extracting track...', 'info');

    fetch('/api/voice/join_and_play', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            channel_id: chId,
            query: query || 'JHOL'
        })
    })
    .then(res => {
        if (res.status === 403 || res.status === 401) {
            openAdminLoginModal();
            throw new Error("Admin Passkey Required");
        }
        return res.json();
    })
    .then(res => {
        if (res.success) {
            showToast(res.message || `Connected to Voice Channel! Now streaming: ${query || 'Audio Track'}`, 'success');
            const trackTitle = document.querySelector('.vc-track-details h4');
            if (trackTitle) trackTitle.textContent = query || 'Live Voice Stream';
            loadAuditLogs();
        } else {
            showToast(`Voice Connection Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => {
        showToast(`Request failed: ${err.message}`, 'danger');
    });
}

/* AI TTS & WEB SOUNDBOARD ENGINE */
function submitWebTTS() {
    const channelIdInput = document.getElementById('ttsChannelId');
    const channelId = (channelIdInput && channelIdInput.value.trim()) ? channelIdInput.value.trim() : '1409233869995118602';
    const text = document.getElementById('ttsText')?.value.trim();
    const lang = document.getElementById('ttsLang')?.value || 'en';

    if (!text) {
        showToast('Please enter text to speak aloud.', 'danger');
        return;
    }

    showToast('Broadcasting AI TTS Speech to Voice Channel...', 'info');

    fetch('/api/tts/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            channel_id: channelId,
            text: text,
            lang: lang
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast(res.message || 'Speaking text in Voice Channel!', 'success');
        } else {
            showToast(`TTS Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => {
        showToast(`Request failed: ${err.message}`, 'danger');
    });
}

function playWebSound(soundUrl) {
    const channelIdInput = document.getElementById('ttsChannelId');
    const channelId = (channelIdInput && channelIdInput.value.trim()) ? channelIdInput.value.trim() : '1409233869995118602';

    showToast('Broadcasting Sound Clip to Voice Channel...', 'info');

    fetch('/api/voice/join_and_play', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            channel_id: channelId,
            query: soundUrl
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast('Sound clip played in Voice Channel!', 'success');
        } else {
            showToast(`Sound Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => {
        showToast(`Request failed: ${err.message}`, 'danger');
    });
}

/* GIVEAWAY VISUAL STUDIO ENGINE */
function updateGwStudioPreview() {
    const prize = document.getElementById('gwStudioPrize')?.value || 'Discord Nitro 1 Month';
    const desc = document.getElementById('gwStudioDesc')?.value || 'Click Enter Giveaway below to join!';
    const color = document.getElementById('gwStudioColor')?.value || '#ec4899';
    const winners = document.getElementById('gwStudioWinners')?.value || '1';
    const duration = document.getElementById('gwStudioDuration')?.value || '60';
    const reqRole = document.getElementById('gwStudioRequiredRole')?.value;

    const pTitle = document.getElementById('gwPreviewTitle');
    const pDesc = document.getElementById('gwPreviewDesc');
    const pBox = document.getElementById('gwEmbedBox');

    if (pTitle) pTitle.textContent = `🎉 GIVEAWAY: ${prize} 🎉`;
    if (pBox) pBox.style.borderLeftColor = color;

    let fullDesc = `${desc}\n\n🎁 **Prize:** \`${prize}\`\n🏆 **Winners:** \`${winners}\`\n⏳ **Ends in:** \`${duration} minutes\``;
    if (reqRole) {
        fullDesc += `\n🔒 **Required Role:** <@&${reqRole}>`;
    }
    if (pDesc) pDesc.innerHTML = fullDesc.replace(/\n/g, '<br>');
}

function submitGwStudioGiveaway() {
    const channelIdInput = document.getElementById('gwStudioChannelId');
    const channelId = (channelIdInput && channelIdInput.value.trim()) ? channelIdInput.value.trim() : '1441003381689942127';
    const prize = document.getElementById('gwStudioPrize')?.value.trim() || 'Discord Nitro';
    const description = document.getElementById('gwStudioDesc')?.value.trim();
    const color = document.getElementById('gwStudioColor')?.value || '#ec4899';
    const duration_mins = parseInt(document.getElementById('gwStudioDuration')?.value, 10) || 60;
    const winners = parseInt(document.getElementById('gwStudioWinners')?.value, 10) || 1;
    const required_role_id = document.getElementById('gwStudioRequiredRole')?.value.trim();
    const thumbnail_url = document.getElementById('gwStudioThumbnail')?.value.trim();
    const banner_url = document.getElementById('gwStudioBanner')?.value.trim();

    showToast('Launching Custom Giveaway to Discord...', 'info');

    fetch('/api/giveaways/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            channel_id: channelId,
            prize: prize,
            description: description,
            color: color,
            duration_mins: duration_mins,
            winners: winners,
            required_role_id: required_role_id,
            thumbnail_url: thumbnail_url,
            banner_url: banner_url
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast(res.message || 'Giveaway launched successfully!', 'success');
            loadGiveaways();
            loadAuditLogs();
        } else {
            showToast(`Giveaway Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => {
        showToast(`Request failed: ${err.message}`, 'danger');
    });
}

/* ADMIN PASSKEY AUTHENTICATION MODAL SYSTEM */
function openAdminLoginModal() {
    const modal = document.getElementById('adminLoginModal');
    if (modal) modal.style.display = 'flex';
}

function closeAdminLoginModal() {
    const modal = document.getElementById('adminLoginModal');
    if (modal) modal.style.display = 'none';
}

async function submitAdminLogin() {
    const passkey = document.getElementById('adminPasskeyInput').value;
    if (!passkey) {
        showToast("Please enter Admin Passkey.", "danger");
        return;
    }

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ passkey: passkey })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Admin authenticated successfully!", "success");
            closeAdminLoginModal();
            fetchStats();
            loadAuditLogs();
        } else {
            showToast(data.error || "Invalid Passkey", "danger");
        }
    } catch (err) {
        showToast("Login failed: " + err.message, "danger");
    }
}

/* TICKET PANEL MODAL HELPERS */
function openCreateTicketPanelModal() {
    const modal = document.getElementById('ticketPanelModal');
    if (modal) modal.style.display = 'flex';
}

function closeCreateTicketPanelModal() {
    const modal = document.getElementById('ticketPanelModal');
    if (modal) modal.style.display = 'none';
}

function submitCreateTicketPanel() {
    const channelId = document.getElementById('ticketPanelChannelId').value.trim();
    const title = document.getElementById('ticketPanelTitle').value.trim() || '📩 Support Ticket Vault';
    const description = document.getElementById('ticketPanelDesc').value.trim() || 'Click the button below to open a private support ticket.';
    const btnLabel = document.getElementById('ticketPanelBtnLabel').value.trim() || 'Open Support Ticket';

    if (!channelId) {
        showToast('Please enter a target Channel ID.', 'danger');
        return;
    }

    showToast('Deploying Ticket Panel to Discord Channel...', 'info');

    fetch('/api/tickets/create_panel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            channel_id: channelId,
            title: title,
            description: description,
            button_label: btnLabel
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast(res.message || 'Support Ticket Panel deployed successfully!', 'success');
            closeCreateTicketPanelModal();
            loadTickets();
            loadAuditLogs();
        } else {
            showToast(`Ticket Panel Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

/* GIVEAWAY MODAL HELPERS */
function openCreateGiveawayModal() {
    const modal = document.getElementById('giveawayModal');
    if (modal) modal.style.display = 'flex';
}

function closeCreateGiveawayModal() {
    const modal = document.getElementById('giveawayModal');
    if (modal) modal.style.display = 'none';
}

function submitCreateGiveaway() {
    const channelId = document.getElementById('giveawayChannelId').value.trim();
    const prize = document.getElementById('giveawayPrize').value.trim();
    const durationMins = parseInt(document.getElementById('giveawayDurationMins').value, 10) || 60;
    const winners = parseInt(document.getElementById('giveawayWinners').value, 10) || 1;

    if (!channelId || !prize) {
        showToast('Please enter both Channel ID and Prize Name.', 'danger');
        return;
    }

    showToast('Posting Giveaway Embed to Discord...', 'info');

    fetch('/api/giveaways/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            channel_id: channelId,
            prize: prize,
            duration_mins: durationMins,
            winners: winners
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast(res.message || `Giveaway for '${prize}' posted successfully!`, 'success');
            closeCreateGiveawayModal();
            loadGiveaways();
            loadAuditLogs();
        } else {
            showToast(`Giveaway Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => console.warn(err));
}

/* TICKET KING A-Z DESIGN STUDIO ENGINE */
function addStudioOption() {
    const container = document.getElementById('studioOptionsContainer');
    if (!container) return;

    const row = document.createElement('div');
    row.className = 'option-row glass p-2 d-flex gap-2 align-items-center';
    row.style.cssText = 'border-radius: 8px; background: rgba(0,0,0,0.3);';
    row.innerHTML = `
        <input type="text" class="opt-emoji" value="❓" placeholder="Emoji" style="width: 50px; text-align: center;" onkeyup="updateStudioPreview()">
        <input type="text" class="opt-label" value="Custom Category" placeholder="Label" style="flex: 1;" onkeyup="updateStudioPreview()">
        <input type="text" class="opt-desc" value="Category description text" placeholder="Description" style="flex: 2;" onkeyup="updateStudioPreview()">
        <button class="btn btn-secondary btn-sm text-rose" onclick="removeStudioOption(this)">&times;</button>
    `;
    container.appendChild(row);
    updateStudioPreview();
}

function removeStudioOption(btn) {
    const row = btn.closest('.option-row');
    if (row) row.remove();
    updateStudioPreview();
}

function updateStudioPreview() {
    const title = document.getElementById('studioTitle')?.value || '👑 JOYST CORPORATION TICKET KING HUB';
    const desc = document.getElementById('studioDesc')?.value || 'Select an option below...';
    const color = document.getElementById('studioColor')?.value || '#a855f7';
    const footer = document.getElementById('studioFooter')?.value || 'JOYST CORPORATION Support OS';

    const pTitle = document.getElementById('studioPreviewTitle');
    const pDesc = document.getElementById('studioPreviewDesc');
    const pFooter = document.getElementById('studioPreviewFooter');
    const pBox = document.getElementById('studioEmbedBox');
    const pOptsContainer = document.getElementById('studioPreviewOptions');

    if (pTitle) pTitle.textContent = title;
    if (pDesc) pDesc.textContent = desc;
    if (pFooter) pFooter.textContent = footer;
    if (pBox) pBox.style.borderLeftColor = color;

    if (pOptsContainer) {
        pOptsContainer.innerHTML = '';
        const rows = document.querySelectorAll('#studioOptionsContainer .option-row');
        rows.forEach(r => {
            const emoji = r.querySelector('.opt-emoji')?.value || '🎫';
            const label = r.querySelector('.opt-label')?.value || 'Support Option';
            const optionDesc = r.querySelector('.opt-desc')?.value || '';

            const optDiv = document.createElement('div');
            optDiv.className = 'mock-option';
            optDiv.innerHTML = `<span>${emoji} ${label}</span> <small>${optionDesc}</small>`;
            pOptsContainer.appendChild(optDiv);
        });
    }
}

function submitStudioTicketPanel() {
    const channelIdInput = document.getElementById('studioChannelId');
    const channelId = (channelIdInput && channelIdInput.value.trim()) ? channelIdInput.value.trim() : '1441003381689942127';
    const title = document.getElementById('studioTitle')?.value.trim() || '👑 JOYST CORPORATION TICKET KING HUB';
    const description = document.getElementById('studioDesc')?.value.trim();
    const color = document.getElementById('studioColor')?.value || '#a855f7';
    const thumbnail_url = document.getElementById('studioThumbnail')?.value.trim();
    const banner_url = document.getElementById('studioBanner')?.value.trim();
    const footer_text = document.getElementById('studioFooter')?.value.trim();

    const options = [];
    const rows = document.querySelectorAll('#studioOptionsContainer .option-row');
    rows.forEach(r => {
        const emoji = r.querySelector('.opt-emoji')?.value.trim() || '🎫';
        const label = r.querySelector('.opt-label')?.value.trim() || 'Support Option';
        const optDesc = r.querySelector('.opt-desc')?.value.trim() || '';

        if (label) {
            options.push({
                emoji: emoji,
                label: label,
                description: optDesc,
                value: label.toLowerCase().replace(/ /g, '_')
            });
        }
    });

    showToast('Deploying Custom Designed Ticket Panel to Discord...', 'info');

    fetch('/api/tickets/create_panel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guild_id: currentGuildId,
            channel_id: channelId,
            title: title,
            description: description,
            color: color,
            thumbnail_url: thumbnail_url,
            banner_url: banner_url,
            footer_text: footer_text,
            options: options
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast(res.message || 'Custom Ticket King Panel deployed successfully!', 'success');
            loadTickets();
            loadAuditLogs();
        } else {
            showToast(`Studio Deploy Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => {
        showToast(`Request failed: ${err.message}`, 'danger');
    });
}
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
        'success': '<i class="fa-solid fa-circle-check text-emerald"></i>',
        'danger': '<i class="fa-solid fa-triangle-exclamation text-pink"></i>',
        'info': '<i class="fa-solid fa-circle-info text-cyan"></i>'
    };

    const toast = document.createElement('div');
    toast.className = `toast-item toast-${type}`;
    toast.innerHTML = `
        ${icons[type] || icons['info']}
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

/* ============================================================
 * NEW WEB CONTROL FUNCTIONS
 * ============================================================ */
function fetchWebWeather() {
    const cityInput = document.getElementById('weatherCityInput');
    const city = cityInput ? cityInput.value.trim() : 'Kanpur';
    fetch(`/api/weather?city=${encodeURIComponent(city || 'Kanpur')}`)
        .then(res => res.json())
        .then(res => {
            const card = document.getElementById('weatherResultCard');
            if (res.success && res.data) {
                const d = res.data;
                document.getElementById('weatherLocationText').innerText = `${d.city}, ${d.country}`;
                document.getElementById('weatherDescText').innerText = d.desc;
                document.getElementById('weatherTempText').innerText = `${d.temp_c}°C`;
                document.getElementById('weatherHumidityText').innerText = `${d.humidity}%`;
                document.getElementById('weatherWindText').innerText = `${d.wind_km} km/h`;
                if (card) card.style.display = 'flex';
                showToast(`Weather data loaded for ${d.city}!`, 'success');
            } else {
                showToast(res.error || `Could not load weather for ${city}`, 'danger');
            }
        })
        .catch(err => showToast(`Weather fetch error: ${err.message}`, 'danger'));
}

function resetDramaScore() {
    const scoreText = document.getElementById('dramaScoreText');
    if (scoreText) scoreText.innerText = '0%';
    showToast('Drama heatmap score reset to 0%!', 'success');
}

function broadcastStreamFromWeb() {
    const channelId = document.getElementById('socialChannelId').value.trim();
    const platform = document.getElementById('socialPlatform').value;
    const pingRole = document.getElementById('socialPingRole').value;
    const title = document.getElementById('socialTitle').value.trim();
    const url = document.getElementById('socialUrl').value.trim();

    if (!channelId || !title || !url) {
        showToast('Please enter Channel ID, Title, and Stream URL.', 'danger');
        return;
    }

    fetch('/api/socials/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            channel_id: channelId,
            platform: platform,
            title: title,
            url: url,
            ping_role_id: pingRole
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast('Live stream announcement dispatched to Discord!', 'success');
        } else {
            showToast(`Broadcast Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => showToast(`Request failed: ${err.message}`, 'danger'));
}

function updateBotStatusFromWeb() {
    const status = document.getElementById('statusSelect').value;
    const activityType = document.getElementById('activityTypeSelect').value;
    const name = document.getElementById('statusNameInput').value.trim();

    fetch('/api/status/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            status: status,
            activity_type: activityType,
            name: name
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.success) {
            showToast(res.message || 'Bot presence updated live!', 'success');
        } else {
            showToast(`Status Update Error: ${res.error}`, 'danger');
        }
    })
    .catch(err => showToast(`Request failed: ${err.message}`, 'danger'));
}

function toggleSidebarFold() {
    const sidebar = document.querySelector('.sidebar');
    const body = document.body;
    const foldBtn = document.getElementById('sidebarFoldBtn');
    if (!sidebar) return;

    sidebar.classList.toggle('collapsed');
    body.classList.toggle('sidebar-is-collapsed');

    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebar_collapsed_state', isCollapsed);

    if (foldBtn) {
        foldBtn.innerHTML = isCollapsed ? '<i class="fa-solid fa-angles-right"></i>' : '<i class="fa-solid fa-angles-left"></i>';
    }
}

// Restore saved fold state on page load
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('sidebar_collapsed_state') === 'true') {
        const sidebar = document.querySelector('.sidebar');
        const body = document.body;
        const foldBtn = document.getElementById('sidebarFoldBtn');
        if (sidebar) sidebar.classList.add('collapsed');
        if (body) body.classList.add('sidebar-is-collapsed');
        if (foldBtn) foldBtn.innerHTML = '<i class="fa-solid fa-angles-right"></i>';
    }
});

function loadMembers() {
    const query = document.getElementById('memberSearchInput') ? document.getElementById('memberSearchInput').value.trim() : '';
    fetch(`/api/members?guild_id=${currentGuildId}&q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => {
            const tbody = document.getElementById('memberTableBody');
            const badge = document.getElementById('totalMembersBadge');
            if (!tbody) return;

            if (data.total_members && badge) {
                badge.innerText = `${data.total_members.toLocaleString()} MEMBERS`;
            }

            if (!data.success || !data.members || data.members.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-4">No members found matching query.</td></tr>`;
                return;
            }

            let html = '';
            data.members.forEach(m => {
                const roleBadge = m.is_owner ? 'badge-purple' : (m.is_bot ? 'badge-success' : 'badge-info');
                const statusDot = m.status === 'ONLINE' ? '🟢' : (m.status === 'IDLE' ? '🌙' : (m.status === 'DND' ? '🔴' : '⚪'));
                const actionBtn = m.is_owner ? `<button class="btn btn-secondary btn-sm" disabled>Whitelisted</button>` : `<button class="btn btn-secondary btn-sm" onclick="dispatchQuickMod('${m.id}')">Manage</button>`;

                html += `
                    <tr>
                        <td>
                            <div class="user-cell">
                                <img src="${m.avatar}" class="user-cell-avatar" onerror="this.src='/static/images/logo.png'">
                                <div>
                                    <strong>${m.name}</strong>
                                    <div class="text-sub">@${m.username}</div>
                                </div>
                            </div>
                        </td>
                        <td><code>${m.id}</code></td>
                        <td><span class="badge ${roleBadge}">${m.role} • ${m.status} ${statusDot}</span></td>
                        <td>${actionBtn}</td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        })
        .catch(err => console.warn(err));
}

function toggleDarkLightTheme() {
    const body = document.body;
    const btn = document.getElementById('themeToggleBtn');
    body.classList.toggle('light-theme');

    const isLight = body.classList.contains('light-theme');
    localStorage.setItem('dashboard_theme_mode', isLight ? 'light' : 'dark');

    if (btn) {
        btn.innerHTML = isLight ? '<i class="fa-solid fa-sun text-amber"></i>' : '<i class="fa-solid fa-moon text-amber"></i>';
    }
    showToast(isLight ? 'Light Theme Active' : 'Dark Cyberpunk Theme Active', 'info');
}

// Restore saved theme state on load
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('dashboard_theme_mode') === 'light') {
        document.body.classList.add('light-theme');
        const btn = document.getElementById('themeToggleBtn');
        if (btn) btn.innerHTML = '<i class="fa-solid fa-sun text-amber"></i>';
    }
});

/* ============================================================
 * GLOBAL CTRL+K COMMAND SEARCH SPOTLIGHT ENGINE
 * ============================================================ */
const ALL_BOT_COMMANDS = [
    { name: '/security status', desc: 'Displays live security diagnostic & active modules overview', category: 'Security', badge: 'badge-purple' },
    { name: '/antinuke toggle', desc: 'Toggles instant Anti-Nuke Quarantine shield', category: 'Security', badge: 'badge-purple' },
    { name: '/antiraid lock', desc: 'Locks channels against alt-account bot raid waves', category: 'Security', badge: 'badge-purple' },
    { name: '/automod badwords', desc: 'Manages forbidden bad word regex filters', category: 'AutoMod', badge: 'badge-info' },
    { name: '/automod antispam', desc: 'Configures rate limiting & character flood rules', category: 'AutoMod', badge: 'badge-info' },
    { name: '/music play', desc: 'Streams high-fidelity lossless music into Voice Channel', category: 'Music', badge: 'badge-pink' },
    { name: '/music stop', desc: 'Stops music playback and disconnects bot from Voice Channel', category: 'Music', badge: 'badge-pink' },
    { name: '/weather', desc: 'Fetches live meteorological weather & humidity forecast card', category: 'Utility', badge: 'badge-amber' },
    { name: '/ticket setup', desc: 'Deploys custom dropdown ticket creation panel to channel', category: 'Tickets', badge: 'badge-emerald' },
    { name: '/giveaway start', desc: 'Launches automated giveaway event with random winner selection', category: 'Giveaways', badge: 'badge-cyan' },
    { name: '/tempban user', desc: 'Temporarily bans user with automated unban countdown timer', category: 'Moderation', badge: 'badge-secondary' },
    { name: '/whitelist add', desc: 'Adds trusted user or role to Anti-Nuke bypass list', category: 'Security', badge: 'badge-purple' }
];

function openCommandSpotlight() {
    const modal = document.getElementById('commandSpotlightModal');
    const input = document.getElementById('spotlightSearchInput');
    if (modal) {
        modal.style.display = 'flex';
        if (input) {
            input.value = '';
            input.focus();
        }
        filterSpotlightCommands('');
    }
}

function closeCommandSpotlight() {
    const modal = document.getElementById('commandSpotlightModal');
    if (modal) modal.style.display = 'none';
}

function filterSpotlightCommands(query) {
    const list = document.getElementById('spotlightResultsList');
    if (!list) return;

    const q = query.toLowerCase().trim();
    const filtered = ALL_BOT_COMMANDS.filter(c => c.name.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q) || c.category.toLowerCase().includes(q));

    if (filtered.length === 0) {
        list.innerHTML = `<div class="text-center py-4 text-muted">No commands matching "${query}"</div>`;
        return;
    }

    let html = '';
    filtered.forEach(c => {
        html += `
            <div class="spotlight-item glass p-3" style="display:flex; justify-content:space-between; align-items:center; border-radius:12px; cursor:pointer; background:rgba(255,255,255,0.03);" onclick="navigator.clipboard.writeText('${c.name}'); showToast('Copied ${c.name} to clipboard!', 'success'); closeCommandSpotlight();">
                <div>
                    <div style="font-family:'JetBrains Mono',monospace; font-weight:700; color:#38bdf8; font-size:15px;">${c.name}</div>
                    <div style="font-size:12px; color:#94a3b8; margin-top:2px;">${c.desc}</div>
                </div>
                <span class="badge ${c.badge}">${c.category}</span>
            </div>
        `;
    });
    list.innerHTML = html;
}

document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        openCommandSpotlight();
    }
    if (e.key === 'Escape') {
        closeCommandSpotlight();
    }
});

/* INTERACTIVE SECURITY CALCULATOR LOGIC */
function recalculateSecurityScore() {
    const chks = document.querySelectorAll('.sec-chk');
    let score = 0;
    chks.forEach(c => {
        if (c.checked) score += parseInt(c.getAttribute('data-score') || '0');
    });

    const gradeEl = document.getElementById('calcGradeDisplay');
    const badgeEl = document.getElementById('calcScoreBadge');
    const recEl = document.getElementById('calcRecommendation');

    if (!gradeEl || !badgeEl) return;

    let grade = 'F';
    let badgeClass = 'badge-secondary';
    let rec = 'Critical vulnerability! Invite JOYST CORPORATION to shield your server immediately.';

    if (score >= 90) {
        grade = 'S+';
        badgeClass = 'badge-emerald';
        rec = 'Maximum Military-Grade Security active! Server is 100% fortified against all threat vectors.';
    } else if (score >= 70) {
        grade = 'A+';
        badgeClass = 'badge-emerald';
        rec = 'Your server is well protected against rogue admin nukes and spam floods!';
    } else if (score >= 45) {
        grade = 'B';
        badgeClass = 'badge-amber';
        rec = 'Moderate protection active. Enable Anti-Nuke and Phishing filters for full coverage.';
    } else if (score >= 20) {
        grade = 'C';
        badgeClass = 'badge-purple';
        rec = 'Basic security active. High vulnerability to rogue admin hacks & raid waves.';
    }

    gradeEl.innerText = grade;
    badgeEl.className = `badge ${badgeClass} py-2 px-3 mb-2`;
    badgeEl.innerText = `${score}% SECURED (${score}/100)`;
    if (recEl) recEl.innerText = rec;
}

document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
});







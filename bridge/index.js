const crypto = require('crypto');
if (!global.crypto) global.crypto = crypto;
if (!globalThis.crypto) globalThis.crypto = crypto;

const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    DisconnectReason, 
    fetchLatestBaileysVersion, 
    Browsers,
    jidNormalizedUser
} = require('@whiskeysockets/baileys');
const axios = require('axios');
const qrcodeTerminal = require('qrcode-terminal');
const qrcode = require('qrcode');
const express = require('express');
const pino = require('pino');

const app = express();
const QR_PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8080/webhook/whatsapp';

let latestQR = null;
let isConnected = false;
let sock = null;

function extractMessageText(message) {
    if (!message) return null;
    const m = message.ephemeralMessage?.message || 
              message.viewOnceMessage?.message || 
              message.documentWithCaptionMessage?.message || 
              message;
    return m.conversation || 
           m.extendedTextMessage?.text || 
           m.imageMessage?.caption || 
           m.videoMessage?.caption || 
           null;
}

app.get('/qr', async (req, res) => {
    if (isConnected) {
        return res.send(`
            <div style="font-family:Segoe UI, sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;background:#071426;color:#57df9b;">
                <h2 style="font-size:28px;">✅ WhatsApp Bridge is Connected 24/7!</h2>
                <p style="color:#a9bdd3;margin-top:10px;">Your cloud agent is actively listening for cohort messages.</p>
            </div>
        `);
    }
    if (!latestQR) {
        return res.send(`
            <head><meta http-equiv="refresh" content="3"></head>
            <div style="font-family:Segoe UI, sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;background:#071426;color:#eef6ff;">
                <h2>⏳ Generating WhatsApp QR Code...</h2>
                <p style="color:#a9bdd3;margin-top:8px;">Auto-refreshing in 3 seconds...</p>
            </div>
        `);
    }
    const qrImage = await qrcode.toDataURL(latestQR);
    res.send(`
        <head><meta http-equiv="refresh" content="20"></head>
        <div style="font-family:Segoe UI, sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;background:#071426;color:#eef6ff;">
            <h2 style="color:#5ee7f7;margin-bottom:15px;">Scan with WhatsApp to Link Cloud Bridge</h2>
            <img src="${qrImage}" style="width:280px;height:280px;background:#fff;border-radius:14px;padding:12px;box-shadow:0 10px 25px rgba(0,0,0,0.5);"/>
            <p style="color:#a9bdd3;margin-top:15px;">Open WhatsApp &gt; Linked Devices &gt; Link a Device</p>
        </div>
    `);
});

app.get('/groups', async (req, res) => {
    if (!sock || !isConnected) {
        return res.status(400).send('<h3>WhatsApp Bridge is not connected yet.</h3>');
    }
    try {
        const groups = await sock.groupFetchAllParticipating();
        const list = Object.values(groups).map(g => ({
            id: g.id,
            name: g.subject,
            members: g.participants ? g.participants.length : 0
        }));

        let html = `
        <div style="font-family:Segoe UI, sans-serif;max-width:800px;margin:30px auto;padding:20px;background:#0d1b2a;color:#eef6ff;border-radius:12px;">
            <h2 style="color:#5ee7f7;">📱 Your WhatsApp Groups (${list.length})</h2>
            <table style="width:100%;border-collapse:collapse;margin-top:15px;">
                <thead>
                    <tr style="border-bottom:2px solid #25425f;text-align:left;color:#57df9b;">
                        <th style="padding:10px;">Group Name</th>
                        <th style="padding:10px;">Group ID</th>
                        <th style="padding:10px;">Members</th>
                    </tr>
                </thead>
                <tbody>
        `;
        for (const g of list) {
            html += `
                <tr style="border-bottom:1px solid #25425f;">
                    <td style="padding:10px;font-weight:600;">${g.name}</td>
                    <td style="padding:10px;"><code style="background:#1b2d45;padding:4px 8px;border-radius:6px;color:#ffbd66;user-select:all;">${g.id}</code></td>
                    <td style="padding:10px;color:#a9bdd3;">${g.members}</td>
                </tr>
            `;
        }
        html += `</tbody></table></div>`;
        res.send(html);
    } catch (err) {
        res.status(500).send(`Error fetching groups: ${err.message}`);
    }
});

app.listen(QR_PORT, () => {
    console.log(`🌐 QR Web Page: http://localhost:${QR_PORT}/qr`);
});

let isConnecting = false;

async function startBridge() {
    if (isConnecting) return;
    isConnecting = true;

    try {
        const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
        const { version } = await fetchLatestBaileysVersion();
        
        sock = makeWASocket({
            version,
            auth: state,
            logger: pino({ level: 'silent' }),
            printQRInTerminal: true,
            browser: Browsers.macOS('Desktop'),
            connectTimeoutMs: 60000,
            defaultQueryTimeoutMs: 0,
            keepAliveIntervalMs: 10000,
            syncFullHistory: false
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                latestQR = qr;
                console.log('📱 Fresh QR code generated!');
                qrcodeTerminal.generate(qr, { small: true });
            }
            
            if (connection === 'close') {
                isConnected = false;
                isConnecting = false;
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                console.log(`Connection closed (status: ${statusCode}, reason: ${lastDisconnect?.error?.message || 'unknown'}). Reconnecting: ${shouldReconnect}`);
                
                if (shouldReconnect) {
                    setTimeout(() => {
                        startBridge();
                    }, 5000);
                }
            } else if (connection === 'open') {
                isConnected = true;
                isConnecting = false;
                latestQR = null;
                console.log('✅ WhatsApp Bridge Connected Successfully!');
                if (sock.user) {
                    console.log(`👤 Logged in as: ${sock.user.name || sock.user.id}`);
                }
            }
        });

        let lastBotReplyText = null;

        sock.ev.on('messages.upsert', async (m) => {
            for (const msg of m.messages) {
                if (!msg.message) continue;

                const text = extractMessageText(msg.message);
                if (!text) continue;

                const rawJid = msg.key.remoteJid;
                if (!rawJid || rawJid === 'status@broadcast') continue;

                const remoteJid = jidNormalizedUser(rawJid);
                const isGroup = remoteJid.endsWith('@g.us');
                const isPrivate = !isGroup;
                const sender = msg.pushName || (msg.key.fromMe ? "Prefect (You)" : "User");

                if (msg.key.fromMe && text === lastBotReplyText) {
                    continue;
                }

                console.log(`📨 [${isPrivate ? 'PRIVATE' : 'GROUP'}: ${remoteJid}] ${sender}: ${text}`);

                try {
                    const response = await axios.post(BACKEND_URL, {
                        group_id: remoteJid,
                        sender: sender,
                        message: text,
                        timestamp: msg.messageTimestamp,
                        is_private: isPrivate
                    });

                    if (response.data && response.data.should_reply && response.data.reply_text) {
                        lastBotReplyText = response.data.reply_text;
                        const replyTarget = remoteJid;
                        console.log(`🤖 [Sending Reply to ${replyTarget}]:\n${response.data.reply_text}\n`);
                        await sock.sendMessage(replyTarget, { text: response.data.reply_text });
                    }

                    if (isGroup && response.data.should_alert_prefect && response.data.prefect_alert_text) {
                        const prefectJid = sock.user ? jidNormalizedUser(sock.user.id) : null;
                        if (prefectJid) {
                            console.log(`🚨 [Proactive VIP Alert Dispatched to Prefect: ${prefectJid}]`);
                            await sock.sendMessage(prefectJid, { text: response.data.prefect_alert_text });
                        }
                    }
                } catch (err) {
                    console.error('Failed to process message with backend:', err.message);
                }
            }
        });
    } catch (e) {
        isConnecting = false;
        console.error('Error in startBridge:', e.message);
        setTimeout(startBridge, 5000);
    }
}

startBridge();

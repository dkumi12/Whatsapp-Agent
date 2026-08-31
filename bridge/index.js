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
const PHONE_NUMBER = process.env.PHONE_NUMBER || '';

let latestQR = null;
let pairingCode = null;
let isConnected = false;
let sockInstance = null;

// Helper to extract text from any WhatsApp message type/wrapper
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
        return res.send('<h2 style="font-family:sans-serif;color:green;text-align:center;margin-top:20%;">✅ WhatsApp Bridge is Connected!</h2>');
    }
    if (pairingCode) {
        return res.send(`
            <div style="font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;">
                <h2>WhatsApp 8-Digit Pairing Code</h2>
                <div style="font-size:32px;letter-spacing:6px;font-weight:bold;background:#10243d;color:#5ee7f7;padding:16px 24px;border-radius:10px;border:1px solid #25425f;">
                    ${pairingCode}
                </div>
                <p style="color:#666;margin-top:15px;">Open WhatsApp &gt; Linked Devices &gt; Link with phone number instead</p>
            </div>
        `);
    }
    if (!latestQR) {
        return res.send('<h2 style="font-family:sans-serif;text-align:center;margin-top:20%;">⏳ Generating QR Code, refresh in 3 seconds...</h2>');
    }
    const qrImage = await qrcode.toDataURL(latestQR);
    res.send(`
        <div style="font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;">
            <h2>Scan with WhatsApp (Linked Devices)</h2>
            <img src="${qrImage}" style="width:280px;height:280px;border:1px solid #ccc;border-radius:12px;padding:10px;"/>
            <p style="color:#666;">Open WhatsApp &gt; Linked Devices &gt; Link a Device</p>
        </div>
    `);
});

app.get('/groups', async (req, res) => {
    if (!sockInstance || !isConnected) {
        return res.status(400).send('<h3>WhatsApp Bridge is not connected yet.</h3>');
    }
    try {
        const groups = await sockInstance.groupFetchAllParticipating();
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
    console.log(`📋 Group List Web Page: http://localhost:${QR_PORT}/groups`);
});

async function startBridge() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    const { version, isLatest } = await fetchLatestBaileysVersion();
    console.log(`📱 Using WA Web version v${version.join('.')}, isLatest: ${isLatest}`);

    const sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: !PHONE_NUMBER,
        browser: Browsers.windows('Desktop'),
        syncFullHistory: false,
        generateHighQualityLinkPreview: true
    });

    sockInstance = sock;
    sock.ev.on('creds.update', saveCreds);

    if (PHONE_NUMBER && !sock.authState.creds.registered) {
        setTimeout(async () => {
            try {
                const code = await sock.requestPairingCode(PHONE_NUMBER.replace(/[^0-9]/g, ''));
                pairingCode = code;
                console.log(`\n🔑 WHATSAPP PAIRING CODE: ${code}`);
            } catch (err) {
                console.error('Failed to request pairing code:', err.message);
            }
        }, 3000);
    }

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            latestQR = qr;
            qrcodeTerminal.generate(qr, { small: true });
        }
        if (connection === 'close') {
            isConnected = false;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            console.log(`Connection closed (status: ${statusCode}). Reconnecting: ${shouldReconnect}`);
            if (shouldReconnect) {
                setTimeout(startBridge, 3000);
            }
        } else if (connection === 'open') {
            isConnected = true;
            latestQR = null;
            pairingCode = null;
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

            // Normalized JID
            const remoteJid = jidNormalizedUser(rawJid);
            const isGroup = remoteJid.endsWith('@g.us');
            const isPrivate = !isGroup;
            const sender = msg.pushName || (msg.key.fromMe ? "Prefect (You)" : "User");

            // Ignore our own bot reply loop
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

                // 1. Reply to chat if requested
                if (response.data && response.data.should_reply && response.data.reply_text) {
                    lastBotReplyText = response.data.reply_text;
                    const replyTarget = remoteJid;
                    console.log(`🤖 [Sending Reply to ${replyTarget}]:\n${response.data.reply_text}\n`);
                    await sock.sendMessage(replyTarget, { text: response.data.reply_text });
                }

                // 2. Proactive VIP Alert to Prefect's Private Chat
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
}

startBridge();

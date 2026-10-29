const crypto = require('crypto');
if (!global.crypto) global.crypto = crypto;
if (!globalThis.crypto) globalThis.crypto = crypto;

const fs = require('fs');
const path = require('path');
const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    DisconnectReason, 
    fetchLatestBaileysVersion, 
    Browsers,
    jidNormalizedUser,
    downloadMediaMessage
} = require('@whiskeysockets/baileys');
const axios = require('axios');
const qrcodeTerminal = require('qrcode-terminal');
const qrcode = require('qrcode');
const express = require('express');
const pino = require('pino');

const app = express();
const QR_PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8080/webhook/whatsapp';
const QUEUE_FILE = path.join(__dirname, 'queue.jsonl');

let latestQR = null;
let isConnected = false;
let sock = null;
let lastBotReplyText = null;
let isFlushingQueue = false;

function enqueueOfflineMessage(payload) {
    try {
        const line = JSON.stringify(payload) + '\n';
        fs.appendFileSync(QUEUE_FILE, line, 'utf8');
        console.log(`📦 [Queued offline message from ${payload.sender} to queue.jsonl]`);
    } catch (e) {
        console.error('Failed to write to queue.jsonl:', e.message);
    }
}

async function flushOfflineQueue() {
    if (isFlushingQueue) return;
    if (!fs.existsSync(QUEUE_FILE)) return;

    try {
        const stats = fs.statSync(QUEUE_FILE);
        if (stats.size === 0) return;

        // Verify backend is healthy before attempting flush
        try {
            await axios.get('http://127.0.0.1:8080/health', { timeout: 3000 });
        } catch {
            return; // Backend still offline; keep waiting
        }

        isFlushingQueue = true;
        const processingFile = `${QUEUE_FILE}.processing`;

        try {
            fs.renameSync(QUEUE_FILE, processingFile);
        } catch {
            isFlushingQueue = false;
            return;
        }

        const content = fs.readFileSync(processingFile, 'utf8');
        const lines = content.split('\n').map(l => l.trim()).filter(Boolean);
        console.log(`🔄 [Flushing ${lines.length} offline queued message(s) to backend...]`);

        const failedLines = [];

        for (const line of lines) {
            try {
                const payload = JSON.parse(line);
                const response = await axios.post(BACKEND_URL, payload, { timeout: 60000 });

                if (response.data && response.data.should_reply && response.data.reply_text) {
                    const ageSeconds = payload.timestamp ? (Date.now() / 1000 - payload.timestamp) : 0;
                    if (payload.is_private || ageSeconds < 600) {
                        lastBotReplyText = response.data.reply_text;
                        if (sock && isConnected) {
                            let targetJid = payload.group_id;
                            if (payload.is_private && (targetJid.endsWith('@lid') || targetJid.includes('@lid'))) {
                                targetJid = sock.user ? jidNormalizedUser(sock.user.id) : targetJid;
                            }
                            await sock.sendMessage(targetJid, { text: response.data.reply_text });
                        }
                    }
                }

                if (response.data && response.data.should_alert_prefect && response.data.prefect_alert_text) {
                    if (sock && isConnected) {
                        const prefectJid = process.env.PREFECT_JID || jidNormalizedUser(sock.user.id);
                        await sock.sendMessage(prefectJid, { text: response.data.prefect_alert_text });
                    }
                }
            } catch (err) {
                console.error('Failed to replay queued message, keeping for next flush:', err.message);
                failedLines.push(line);
            }
        }

        try {
            fs.unlinkSync(processingFile);
        } catch {}

        if (failedLines.length > 0) {
            fs.appendFileSync(QUEUE_FILE, failedLines.join('\n') + '\n', 'utf8');
        } else {
            console.log(`✅ [All ${lines.length} queued messages successfully processed by backend]`);
        }
    } catch (err) {
        console.error('Error in flushOfflineQueue:', err.message);
    } finally {
        isFlushingQueue = false;
    }
}

// Background poll to replay queued messages every 15 seconds
setInterval(flushOfflineQueue, 15000);

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
           m.documentMessage?.caption ||
           m.documentWithCaptionMessage?.message?.documentMessage?.caption ||
           null;
}

app.get('/qr', async (req, res) => {
    if (isConnected) {
        return res.send(`
            <div style="font-family:Segoe UI, sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;background:#071426;color:#57df9b;">
                <h2 style="font-size:28px;">✅ WhatsApp Bridge is Connected 24/7!</h2>
                <p style="color:#a9bdd3;margin-top:10px;">Your cloud agent is actively listening for cohort messages.</p>
                <p style="margin-top:20px;"><a href="/groups" style="color:#5ee7f7;text-decoration:none;font-weight:600;background:#1b2d45;padding:10px 18px;border-radius:8px;">View All Cohort Group IDs ➔</a></p>
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
        return res.status(400).send('<h3>WhatsApp Bridge is not connected yet. Please wait 5 seconds and refresh.</h3>');
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

app.get('/status', async (req, res) => {
    let authCount = 0;
    try {
        const files = fs.readdirSync(path.join(__dirname, 'auth_info_baileys'));
        authCount = files.length;
    } catch {}

    res.json({
        connected: isConnected,
        user: sock?.user || null,
        uptimeSeconds: Math.floor(process.uptime()),
        authFilesCount: authCount,
        prefectJid: process.env.PREFECT_JID || 'not set',
        timestamp: new Date().toISOString()
    });
});

app.get('/test-send', async (req, res) => {
    if (!sock || !isConnected) {
        return res.status(503).json({ error: 'WhatsApp Bridge is not connected.' });
    }
    const target = req.query.jid || process.env.PREFECT_JID || (sock.user ? jidNormalizedUser(sock.user.id) : null);
    if (!target) {
        return res.status(400).json({ error: 'No target JID available.' });
    }

    const testText = `🧪 [Bridge Diagnostic Ping]\n` +
                     `Time: ${new Date().toUTCString()}\n` +
                     `Bridge JID: ${sock.user?.id}\n` +
                     `Status: Active & Connected 24/7\n` +
                     `If you can read this cleanly, your device E2EE session ratchet is working!`;

    try {
        console.log(`📤 [Sending Diagnostic Test Message to ${target}]...`);
        const result = await sock.sendMessage(target, { text: testText });
        console.log(`✅ [Diagnostic Test Message Sent! ID: ${result?.key?.id}]`);
        res.json({
            status: 'sent',
            targetJid: target,
            messageId: result?.key?.id,
            timestamp: result?.messageTimestamp
        });
    } catch (err) {
        console.error('❌ Failed to send diagnostic test message:', err.message);
        res.status(500).json({ error: err.message });
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

        sock.ev.on('messages.upsert', async (m) => {
            for (const msg of m.messages) {
                const rawJid = msg.key?.remoteJid;
                if (!rawJid || rawJid === 'status@broadcast') continue;

                if (!msg.message) {
                    if (!msg.messageStubType) {
                        console.log(`⚠️ [Undecryptable / Waiting Message from ${rawJid} (ID: ${msg.key?.id})]`);
                    }
                    continue;
                }

                const text = extractMessageText(msg.message) || "";

                const remoteJid = jidNormalizedUser(rawJid);
                const isGroup = remoteJid.endsWith('@g.us');
                const isPrivate = !isGroup;

                // Strict Whitelist: Only process official cohort groups for group events
                const allowedGroups = [
                    process.env.COHORT_1_GROUP_ID || '120363428812662381@g.us', // Cohort 1
                    process.env.COHORT_2_GROUP_ID || '120363406407748018@g.us', // Cohort 2
                    '120363427542055326@g.us', // AWS PRACTITIONER Cohort 2
                    '120363430746173915@g.us', // Python with AI Cohort 2
                    '120363411584074404@g.us', // A.I with Python for Everybody
                    '120363415570593617@g.us', // Data Science And Analytics Free-Training
                    '120363433400665333@g.us', // CloudWithShad Cohort 2
                    '120363408183500853@g.us', // Cloud Practitioner - Q n A
                    '120363426897508316@g.us'  // CloudWithShad
                ];
                if (isGroup && !allowedGroups.includes(remoteJid)) {
                    continue;
                }

                // Privacy Shield: Ignore regular private DMs unless they explicitly start with a command or upload a document
                if (isPrivate && !text.startsWith('/') && !text.startsWith('!') && !hasDocument) {
                    continue;
                }

                const sender = msg.pushName || (msg.key.fromMe ? "Prefect (You)" : "User");

                if (msg.key.fromMe && text === lastBotReplyText) {
                    continue;
                }

                console.log(`📨 [${isPrivate ? 'PRIVATE' : 'COHORT'}: ${remoteJid}] ${sender}: ${text}`);

                let file_name = null;
                let mime_type = null;
                let file_data = null; // Base64
                
                try {
                    const docMessage = msg.message?.documentMessage || msg.message?.documentWithCaptionMessage?.message?.documentMessage;
                    if (docMessage && docMessage.mimetype === 'application/pdf') {
                        // For safety, only download if it's explicitly meant to be learned or it's a PDF.
                        // We will just let the backend handle the caption logic.
                        console.log(`📥 [Downloading PDF from ${sender}...]`);
                        const buffer = await downloadMediaMessage(
                            msg,
                            'buffer',
                            {},
                            { 
                                logger: pino({ level: 'silent' }),
                                reuploadRequest: sock.updateMediaMessage
                            }
                        );
                        file_name = docMessage.fileName || "document.pdf";
                        mime_type = docMessage.mimetype;
                        file_data = buffer.toString('base64');
                        console.log(`✅ [Downloaded ${file_name} successfully]`);
                    }
                } catch (e) {
                    console.error("Error downloading media:", e.message);
                }

                const payload = {
                    group_id: remoteJid,
                    sender: sender,
                    message: text || "",
                    timestamp: msg.messageTimestamp,
                    is_private: isPrivate,
                    file_name: file_name,
                    mime_type: mime_type,
                    file_data: file_data
                };

                try {
                    const response = await axios.post(BACKEND_URL, payload, { timeout: 60000 });

                    if (response.data && response.data.should_reply && response.data.reply_text) {
                        lastBotReplyText = response.data.reply_text;
                        let replyTarget = remoteJid;
                        if (isPrivate && (remoteJid.endsWith('@lid') || msg.key.fromMe)) {
                            replyTarget = sock.user ? jidNormalizedUser(sock.user.id) : remoteJid;
                        }
                        console.log(`🤖 [Sending Reply to ${replyTarget}]:\n${response.data.reply_text}\n`);
                        await sock.sendMessage(replyTarget, { text: response.data.reply_text });
                    }

                    if (isGroup && response.data.should_alert_prefect && response.data.prefect_alert_text) {
                        const prefectJid = process.env.PREFECT_JID || (sock.user ? jidNormalizedUser(sock.user.id) : null);
                        if (prefectJid) {
                            console.log(`🚨 [Proactive VIP Alert Dispatched to Prefect: ${prefectJid}]`);
                            await sock.sendMessage(prefectJid, { text: response.data.prefect_alert_text });
                        }
                    }
                } catch (err) {
                    console.error('Failed to process message with backend:', err.message);
                    // Buffer message to queue.jsonl for zero-loss recovery
                    enqueueOfflineMessage(payload);
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

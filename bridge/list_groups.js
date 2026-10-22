const crypto = require('crypto');
if (!global.crypto) global.crypto = crypto;
if (!globalThis.crypto) globalThis.crypto = crypto;

const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    DisconnectReason, 
    fetchLatestBaileysVersion, 
    Browsers 
} = require('@whiskeysockets/baileys');
const pino = require('pino');

async function listGroups() {
    const { state, saveCreds } = await useMultiFileAuthState('./auth_info_baileys');
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: false,
        auth: state,
        browser: Browsers.macOS('Desktop')
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'open') {
            console.log('✅ Connected! Fetching all participating groups...\n');
            try {
                const groups = await sock.groupFetchAllParticipating();
                const groupList = Object.values(groups);

                if (groupList.length === 0) {
                    console.log('No groups found.');
                } else {
                    console.log(`Found ${groupList.length} groups:\n`);
                    console.log('------------------------------------------------------------');
                    for (const g of groupList) {
                        console.log(`📌 Subject: "${g.subject}"`);
                        console.log(`   ID:      ${g.id}`);
                        console.log(`   Members: ${g.participants ? g.participants.length : 'unknown'}`);
                        console.log('------------------------------------------------------------');
                    }
                }
            } catch (err) {
                console.error('Error fetching groups:', err.message);
            }
            process.exit(0);
        } else if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            if (statusCode === DisconnectReason.loggedOut) {
                console.log('Session logged out.');
                process.exit(1);
            }
        }
    });
}

listGroups().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});

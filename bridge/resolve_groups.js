const fs = require('fs');

// We tap into the running bridge process by writing a small script that asks Baileys for group metadata
// Or we can write a small script that connects using the existing auth to fetch group metadata with names.
const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    fetchLatestBaileysVersion, 
    Browsers 
} = require('@whiskeysockets/baileys');
const pino = require('pino');

async function resolveNames() {
    const { state } = await useMultiFileAuthState('/home/abami/Whatsapp-Agent/bridge/auth_info_baileys');
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        logger: pino({ level: 'silent' }),
        auth: state,
        browser: Browsers.macOS('Desktop')
    });

    sock.ev.on('connection.update', async (update) => {
        const { connection } = update;
        if (connection === 'open') {
            try {
                const groups = await sock.groupFetchAllParticipating();
                console.log('\n=== ALL YOUR WHATSAPP GROUPS ===');
                for (const [id, meta] of Object.entries(groups)) {
                    console.log(`[NAME] ${meta.subject}  ==>  [ID] ${id}`);
                }
                console.log('================================\n');
            } catch (err) {
                console.error('Error fetching metadata:', err.message);
            }
            process.exit(0);
        }
    });
}

resolveNames().catch(err => {
    console.error(err);
    process.exit(1);
});

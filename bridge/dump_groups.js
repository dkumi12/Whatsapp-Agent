const fs = require('fs');
const path = require('path');

const authDir = '/home/abami/Whatsapp-Agent/bridge/auth_info_baileys';
if (!fs.existsSync(authDir)) {
    console.log('Auth dir not found:', authDir);
    process.exit(1);
}

const files = fs.readdirSync(authDir);
const groupSet = new Set();

files.forEach(file => {
    const match = file.match(/(\d+@g\.us)/);
    if (match) {
        groupSet.add(match[1]);
    }
});

console.log('=== DISCOVERED GROUP JIDs IN SESSION ===');
groupSet.forEach(jid => {
    console.log(jid);
});
console.log('========================================');

const originalLog = console.log;
console.log = function (...args) {
    if (args[0] && typeof args[0] === 'string' && args[0].includes('Closing session:')) {
        return; 
    }
    originalLog.apply(console, args);
};

const { makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const pino = require('pino');
const path = require('path');

process.on('uncaughtException', (err) => {
    console.error('🚨 [CRITICAL ERROR] Uncaught Exception:', err.message);
});
process.on('unhandledRejection', (reason, promise) => {
    console.error('🚨 [CRITICAL ERROR] Unhandled Rejection:', reason);
});

const app = express();
app.use(express.json());
const PORT = 3000;

let sock; 

const sessionDir = path.join(__dirname, '..', '..', '..', '..', 'Data', 'SessionCookies');
if (!fs.existsSync(sessionDir)) {
    fs.mkdirSync(sessionDir, { recursive: true });
}

const store = {
    messages: {},
    readFromFile: (filePath) => {
        if (fs.existsSync(filePath)) {
            try {
                const data = fs.readFileSync(filePath, 'utf-8');
                if (data.trim() === "") throw new Error("Empty file");
                store.messages = JSON.parse(data);
            } catch (err) {
                console.error('⚠️ [STORE] Corrupted or empty store file detected. Starting fresh.');
                store.messages = {};
            }
        }
    },
    writeToFile: (filePath) => {
        try {
            fs.writeFileSync(filePath, JSON.stringify(store.messages), 'utf-8');
        } catch (err) {}
    },
    bind: (ev) => {
        const processMessages = (messages) => {
            if (!messages || !Array.isArray(messages)) return;
            
            try {
                for (const msg of messages) {
                    if (!msg || !msg.key || !msg.key.remoteJid || msg.key.remoteJid === 'status@broadcast') continue;
                    
                    const jid = msg.key.remoteJid;
                    if (!store.messages[jid]) {
                        store.messages[jid] = { array: [] };
                    }
                    
                    const exists = store.messages[jid].array.find(m => m.key && m.key.id === msg.key.id);
                    if (!exists) {
                        store.messages[jid].array.push(msg);
                    }
                }
                
                for (const jid in store.messages) {
                    if (store.messages[jid] && Array.isArray(store.messages[jid].array)) {
                        store.messages[jid].array.sort((a, b) => (Number(a.messageTimestamp) || 0) - (Number(b.messageTimestamp) || 0));
                        if (store.messages[jid].array.length > 1000) { 
                            store.messages[jid].array = store.messages[jid].array.slice(-1000);
                        }
                    }
                }
            } catch (err) {
                console.error("⚠️ [SYNC ERROR] Skipped malformed metadata packet.");
            }
        };

        ev.on('messages.upsert', ({ messages }) => processMessages(messages));
        ev.on('messaging-history.set', ({ messages }) => processMessages(messages));
    }
};

const storePath = path.join(sessionDir, 'baileys_store.json'); 
store.readFromFile(storePath);

setInterval(() => {
    store.writeToFile(storePath);
}, 10000);

async function connectToWhatsApp() {
    try {
        const authPath = path.join(sessionDir, 'auth_info_baileys');
        const { state, saveCreds } = await useMultiFileAuthState(authPath);

        sock = makeWASocket({
            auth: state,
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false 
        });

        store.bind(sock.ev);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                console.log('\n📱 Please scan this QR Code from your WhatsApp device:\n');
                qrcode.generate(qr, { small: true }); 
            }
            
            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                
                if (statusCode === DisconnectReason.loggedOut) {
                    console.log('❌ [LOGGED OUT] Device has been logged out from WhatsApp Web.');
                } else if (statusCode === 440) {
                   
                    console.log('⚠️ [CONFLICT - 440] WhatsApp Web is open elsewhere. Jarvis is waiting 10s to avoid spam...');
                    setTimeout(connectToWhatsApp, 10000); 
                    return; 
                } else if (statusCode === DisconnectReason.timedOut) {
                    console.log('⚠️ [TIMEOUT] Connection is slow, attempting to reconnect...');
                } else {
                    console.log(`⚠️ [DISCONNECTED] Reason Code: ${statusCode}. Reconnecting...`);
                }

                if (shouldReconnect) {
                    setTimeout(connectToWhatsApp, 3000); 
                }
            } else if (connection === 'open') {
                console.log('\n✅ JARVIS WHATSAPP ENGINE IS ONLINE (SEND & FETCH MODE)!\n');
            }
        });

        sock.ev.on('creds.update', saveCreds);

    } catch (err) {
        console.error('❌ [ENGINE START ERROR] Failed to connect to WhatsApp:', err.message);
    }
}

app.post('/send', async (req, res) => {
    try {
        if (!req.body || Object.keys(req.body).length === 0) {
            return res.status(400).json({ error: "Empty request payload" });
        }

        const { number, message, file_path } = req.body;

        if (!number) {
            return res.status(400).json({ error: "Number is required" });
        }

        const cleanNumber = number.toString().replace(/[^0-9]/g, '');
        if (cleanNumber.length < 10) {
            return res.status(400).json({ error: "Invalid phone number format" });
        }
        let targetJid = `${cleanNumber}@s.whatsapp.net`;

        if (!sock || !sock.user) {
            return res.status(503).json({ error: "WhatsApp Engine is currently offline or reconnecting." });
        }

        if (file_path && fs.existsSync(file_path)) {
            console.log(`📤 Preparing to send File: ${file_path} to ${cleanNumber}`);
            
            let buffer;
            try {
                buffer = fs.readFileSync(file_path);
            } catch (fsError) {
                console.error(`❌ [FILE READ ERROR] ${fsError.message}`);
                return res.status(500).json({ error: `Cannot read file at ${file_path}. Permission denied or file locked.` });
            }
            
            let messageContent = {};
            if (file_path.match(/\.(jpeg|jpg|png|webp)$/i)) {
                messageContent = { image: buffer, caption: message || "" };
            } else if (file_path.match(/\.(mp4|mkv)$/i)) {
                messageContent = { video: buffer, caption: message || "" };
            } else if (file_path.match(/\.(mp3|ogg|wav)$/i)) {
                messageContent = { audio: buffer, mimetype: 'audio/mp4' };
            } else {
                messageContent = { document: buffer, mimetype: 'application/octet-stream', fileName: file_path.split(/(\\|\/)/g).pop(), caption: message || "" };
            }

            await sock.sendMessage(targetJid, messageContent);
            console.log(`✅ File Sent Successfully!`);

        } else {
            console.log(`💬 Sending Text to ${cleanNumber}: ${message}`);
            if (message) {
                await sock.sendMessage(targetJid, { text: message });
                console.log(`✅ Text Sent Successfully!`);
            } else {
                return res.status(400).json({ error: "Both message and file_path cannot be empty." });
            }
        }

        res.json({ success: true, status: "Message sent!" });

    } catch (error) {
        console.error("❌ [API SEND ERROR]:", error.message);
        res.status(500).json({ error: error.message });
    }
});

app.post('/fetch-chats', async (req, res) => {
    try {
        const { number, start_timestamp, end_timestamp } = req.body;

        if (!number || !start_timestamp || !end_timestamp) {
            return res.status(400).json({ error: "Missing required parameters: number, start_timestamp, or end_timestamp." });
        }

        const cleanNumber = number.toString().replace(/[^0-9]/g, '');
        const targetJid = `${cleanNumber}@s.whatsapp.net`;

        if (!store.messages[targetJid]) {
            return res.json({ success: true, messages: [] });
        }

        const allMessages = store.messages[targetJid].array;
        
        const filteredMessages = allMessages.filter(msg => {
            const msgTime = Number(msg.messageTimestamp);
            return msgTime >= start_timestamp && msgTime <= end_timestamp;
        });

        const formattedChats = filteredMessages.map(msg => {
            let text = msg.message?.conversation || msg.message?.extendedTextMessage?.text || "[Media/Non-text message]";
            return {
                fromMe: msg.key.fromMe,
                text: text,
                timestamp: Number(msg.messageTimestamp)
            };
        });

        console.log(`📥 Fetched ${formattedChats.length} messages for ${cleanNumber} within the requested timeframe.`);
        res.json({ success: true, messages: formattedChats });

    } catch (error) {
        console.error("❌ [API FETCH ERROR]:", error.message);
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`🔥 Local Bridge listening at http://localhost:${PORT}`);
    connectToWhatsApp();
});
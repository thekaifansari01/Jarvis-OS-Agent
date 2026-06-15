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
const sqlite3 = require('sqlite3').verbose(); 

const sendMessageController = require('./Controllers/sendMessage');
const fetchChatsController = require('./Controllers/fetchChats');

process.on('uncaughtException', (err) => {
    console.error('🚨 [CRITICAL ERROR] Uncaught Exception. Engine is still running:', err.message);
});
process.on('unhandledRejection', (reason, promise) => {
    console.error('🚨 [CRITICAL ERROR] Unhandled Promise Rejection:', reason);
});

const app = express();
app.use(express.json({ limit: '50mb' }));
const PORT = 3000;

let sock; 
let unreadAlerts = [];

const sessionDir = path.join(__dirname, '..', '..', '..', '..', 'Data', 'SessionCookies');
try {
    if (!fs.existsSync(sessionDir)) {
        fs.mkdirSync(sessionDir, { recursive: true });
    }
} catch (fsErr) {
    console.error("🚨 [FS ERROR] Cannot create session directory:", fsErr.message);
}

const dbPath = path.join(sessionDir, 'chats.db');
const db = new sqlite3.Database(dbPath, (err) => {
    if (err) console.error("🚨 [DB INIT ERROR] Failed to connect to SQLite:", err.message);
});

db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS Messages (
        id TEXT PRIMARY KEY,
        phone_number TEXT,
        text TEXT,
        timestamp INTEGER,
        from_me INTEGER
    )`, (err) => {
        if (err) console.error("🚨 [DB TABLE ERROR] Failed to create table:", err.message);
    });
});

function keepTop20ChatsOnly() {
    const cleanupQuery = `
        DELETE FROM Messages
        WHERE phone_number NOT IN (
            SELECT phone_number FROM Messages
            GROUP BY phone_number
            ORDER BY MAX(timestamp) DESC
            LIMIT 20
        )
    `;
    db.run(cleanupQuery, (err) => {
        if (err) console.error("❌ [DB CLEANUP ERROR]:", err.message);
    });
}

const store = {
    bind: (ev) => {
        const processMessages = (messages, isBulkSync = false) => {
            try {
                if (!messages || !Array.isArray(messages) || messages.length === 0) return;
                
                let validMessageCount = 0;
                let uniqueChats = new Set();

                messages.forEach(msg => {
                    try {
                        if (!msg || !msg.key || !msg.key.remoteJid) return;
                        
                        const jid = msg.key.remoteJid;

                        if (jid.endsWith('@g.us') || jid === 'status@broadcast') {
                            return; 
                        }
                        
                        const id = msg.key.id;
                        const timestamp = Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000);
                        const fromMe = msg.key.fromMe ? 1 : 0;
                        let text = msg.message?.conversation || msg.message?.extendedTextMessage?.text || "[Media/Non-text message]";

                        if (!fromMe && !isBulkSync) {
                            let senderName = msg.pushName || `Unknown ${jid.split('@')[0]}`;
                            unreadAlerts.push(`${senderName}: ${text}`);
                        }

                        validMessageCount++;
                        uniqueChats.add(jid.split('@')[0]); 

                        const insertQuery = `INSERT OR IGNORE INTO Messages (id, phone_number, text, timestamp, from_me) VALUES (?, ?, ?, ?, ?)`;
                        
                        db.run(insertQuery, [id, jid, text, timestamp, fromMe], (err) => {
                            if (!err) {
                                keepTop20ChatsOnly();
                            } else {
                                console.error("❌ [DB INSERT ERROR]:", err.message);
                            }
                        });
                    } catch (msgErr) {
                        console.error("⚠️ [MESSAGE PARSING ERROR] Skipped a malformed message:", msgErr.message);
                    }
                });

                if (validMessageCount > 0) {
                    if (isBulkSync) {
                        console.log(`🔄 [OFFLINE/INITIAL SYNC] Loaded ${validMessageCount} personal messages across ${uniqueChats.size} chats (Groups Ignored).`);
                    } else {
                        if (validMessageCount === 1) {
                            console.log(`💬 [LIVE MESSAGE] Received a new personal message from ${Array.from(uniqueChats)[0]}`);
                        } else {
                            console.log(`⚡ [QUICK SYNC] Processed ${validMessageCount} recent personal messages from ${uniqueChats.size} chats.`);
                        }
                    }
                }
            } catch (mainErr) {
                console.error("🚨 [PROCESS MESSAGES FATAL ERROR]:", mainErr.message);
            }
        };

        ev.on('messages.upsert', ({ messages }) => processMessages(messages, false));
        
        ev.on('messaging-history.set', ({ messages }) => {
            console.log(`\n⏳ [SYSTEM WAKING UP] Fetching pending history from WhatsApp servers...`);
            processMessages(messages, true);
        });
    }
};

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
            try {
                const { connection, lastDisconnect, qr } = update;
                
                if (qr) {
                    console.log('\n📱 Please scan this QR Code from your WhatsApp device:\n');
                    qrcode.generate(qr, { small: true }); 
                }
                
                if (connection === 'close') {
                    const statusCode = lastDisconnect?.error?.output?.statusCode;
                    const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                    
                    if (statusCode === DisconnectReason.loggedOut) {
                        console.log('❌ [LOGGED OUT] Device has been logged out from WhatsApp Web. Please delete session folder and rescan.');
                    } else if (statusCode === 440) {
                        console.log('⚠️ [CONFLICT - 440] WhatsApp Web is open elsewhere. Jarvis is waiting 10s to avoid spam...');
                        setTimeout(connectToWhatsApp, 10000); 
                        return; 
                    } else if (statusCode === DisconnectReason.timedOut) {
                        console.log('⚠️ [TIMEOUT] Connection is slow, attempting to reconnect in 5s...');
                        setTimeout(connectToWhatsApp, 5000);
                        return;
                    } else {
                        console.log(`⚠️ [DISCONNECTED] Reason Code: ${statusCode || 'Unknown'}. Reconnecting...`);
                    }

                    if (shouldReconnect) {
                        setTimeout(connectToWhatsApp, 3000); 
                    }
                } else if (connection === 'open') {
                    console.log('\n✅ JARVIS WHATSAPP ENGINE IS ONLINE (MODULAR & SQLITE MODE)!\n');
                }
            } catch (connErr) {
                console.error("🚨 [CONNECTION EVENT ERROR]:", connErr.message);
            }
        });

        sock.ev.on('creds.update', saveCreds);

    } catch (err) {
        console.error('❌ [ENGINE START ERROR] Failed to connect to WhatsApp:', err.message);
        setTimeout(connectToWhatsApp, 10000);
    }
}

app.post('/send', (req, res) => {
    try {
        sendMessageController(req, res, () => sock); 
    } catch (err) {
        console.error("🚨 [ROUTE ERROR - /send]:", err.message);
        if (!res.headersSent) res.status(500).json({ error: "Internal Server Error in /send route" });
    }
});

app.post('/fetch-chats', (req, res) => {
    try {
        fetchChatsController(req, res, db); 
    } catch (err) {
        console.error("🚨 [ROUTE ERROR - /fetch-chats]:", err.message);
        if (!res.headersSent) res.status(500).json({ error: "Internal Server Error in /fetch-chats route" });
    }
});

app.get('/get-alerts', (req, res) => {
    if (unreadAlerts.length > 0) {
        const alertsToSend = [...unreadAlerts];
        unreadAlerts = []; 
        res.json({ success: true, alerts: alertsToSend });
    } else {
        res.json({ success: true, alerts: [] });
    }
});

app.use((req, res) => {
    res.status(404).json({ error: "Route not found" });
});

app.listen(PORT, () => {
    console.log(`🔥 Local Bridge listening at http://localhost:${PORT}`);
    connectToWhatsApp();
});
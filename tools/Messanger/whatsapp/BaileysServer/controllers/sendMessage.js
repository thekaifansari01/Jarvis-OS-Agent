const fs = require('fs');

module.exports = async (req, res, getSock) => {
    try {
        const sock = getSock(); 
        
        if (!req.body || Object.keys(req.body).length === 0) {
            return res.status(400).json({ error: "Empty request payload" });
        }

        const { number, message, file_path } = req.body;

        if (!number) return res.status(400).json({ error: "Number is required" });

        const cleanNumber = number.toString().replace(/[^0-9]/g, '');
        if (cleanNumber.length < 10) return res.status(400).json({ error: "Invalid phone number format" });
        
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
                return res.status(500).json({ error: "Cannot read file" });
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
            if (message) {
                console.log(`💬 Sending Text to ${cleanNumber}: ${message}`);
                await sock.sendMessage(targetJid, { text: message });
                console.log(`✅ Text Sent Successfully!`);
            } else {
                return res.status(400).json({ error: "Empty message" });
            }
        }

        res.json({ success: true, status: "Message sent!" });

    } catch (error) {
        console.error("❌ [API SEND ERROR]:", error.message);
        if (!res.headersSent) res.status(500).json({ error: error.message });
    }
};
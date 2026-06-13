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

        if (!sock || !sock.user) return res.status(503).json({ error: "Engine offline" });

        if (file_path && fs.existsSync(file_path)) {
            let buffer;
            try {
                buffer = fs.readFileSync(file_path);
            } catch (fsError) {
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
        } else {
            if (message) {
                await sock.sendMessage(targetJid, { text: message });
            } else {
                return res.status(400).json({ error: "Empty message" });
            }
        }

        res.json({ success: true, status: "Message sent!" });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
};
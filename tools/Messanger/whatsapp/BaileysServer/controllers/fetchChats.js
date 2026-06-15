module.exports = async (req, res, db) => {
    try {
        const { number, start_timestamp, end_timestamp } = req.body;

        if (!number || !start_timestamp || !end_timestamp) {
            return res.status(400).json({ error: "Missing required parameters" });
        }

        const cleanNumber = number.toString().replace(/[^0-9]/g, '');
        const targetJid = `${cleanNumber}@s.whatsapp.net`;

        const query = `
            SELECT * FROM Messages 
            WHERE phone_number = ? 
            AND timestamp BETWEEN ? AND ? 
            ORDER BY timestamp ASC
        `;

        db.all(query, [targetJid, start_timestamp, end_timestamp], (err, rows) => {
            if (err) {
                console.error("❌ [DB FETCH ERROR]:", err.message);
                return res.status(500).json({ error: "Database error" });
            }

            if (!rows || rows.length === 0) return res.json({ success: true, messages: [] });

            const formattedChats = rows.map(row => {
                return {
                    fromMe: row.from_me === 1,
                    text: row.text,
                    timestamp: row.timestamp
                };
            });

            console.log(`📥 Fetched ${formattedChats.length} messages for ${cleanNumber} from database.`);
            res.json({ success: true, messages: formattedChats });
        });

    } catch (error) {
        console.error("❌ [API FETCH ERROR]:", error.message);
        if (!res.headersSent) res.status(500).json({ error: error.message });
    }
};
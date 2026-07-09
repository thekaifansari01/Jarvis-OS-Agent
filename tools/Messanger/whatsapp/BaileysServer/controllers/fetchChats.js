module.exports = async (req, res, db) => {
    try {
        const { number, start_timestamp, end_timestamp } = req.body;

        if (!number || !start_timestamp || !end_timestamp) {
            return res.status(400).json({ error: "Missing required parameters" });
        }

        const cleanNumber = number.toString().replace(/[^0-9]/g, '');
        const targetJidExact = `${cleanNumber}@s.whatsapp.net`;

        console.log(`🔍 Fetching chats for: ${targetJidExact} (Clean: ${cleanNumber})`);

        const baseQuery = `
            SELECT * FROM Messages
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        `;

        const queryExact = baseQuery.replace("WHERE", "WHERE phone_number = ? AND");
        const queryLike = baseQuery.replace("WHERE", "WHERE phone_number LIKE ? AND");

        db.all(queryExact, [targetJidExact, start_timestamp, end_timestamp], (err, rows) => {
            if (err) {
                console.error("❌ [DB FETCH ERROR]:", err.message);
                return res.status(500).json({ error: "Database error" });
            }

            if (rows && rows.length > 0) {
                console.log(`📥 Exact match found: ${rows.length} messages.`);
                const formattedChats = rows.map(row => ({
                    fromMe: row.from_me === 1,
                    text: row.text,
                    timestamp: row.timestamp
                }));
                return res.json({ success: true, messages: formattedChats });
            }

            console.log(`⚠️ Exact match failed. Trying fallback LIKE pattern for: %${cleanNumber}%`);
            const likePattern = `%${cleanNumber}%`;

            db.all(queryLike, [likePattern, start_timestamp, end_timestamp], (err2, rows2) => {
                if (err2) {
                    console.error("❌ [DB FETCH FALLBACK ERROR]:", err2.message);
                    return res.status(500).json({ error: "Database error" });
                }

                if (rows2 && rows2.length > 0) {
                    console.log(`📥 Fallback LIKE match found: ${rows2.length} messages.`);
                    const formattedChats = rows2.map(row => ({
                        fromMe: row.from_me === 1,
                        text: row.text,
                        timestamp: row.timestamp
                    }));
                    return res.json({ success: true, messages: formattedChats });
                }

                console.log(`❌ No messages found for ${cleanNumber} in the given timeframe.`);
                res.json({ success: true, messages: [] });
            });
        });

    } catch (error) {
        console.error("❌ [API FETCH ERROR]:", error.message);
        if (!res.headersSent) res.status(500).json({ error: error.message });
    }
};
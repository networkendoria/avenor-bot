// Deneme botu: sunucuya girer, TAB listesini ve rutbe oneklerini yazdirir, cikar.
const mineflayer = require("mineflayer");

const host = process.env.MC_SERVER;
const username = process.env.MC_USER || "AvenorLog";
if (!host) {
  console.error("MC_SERVER yok");
  process.exit(1);
}

const bot = mineflayer.createBot({
  host,
  username,
  auth: "offline", // cracked sunucu icin. Premium ise giris hatasi alirsin.
  hideErrors: false,
});

const limit = setTimeout(() => {
  console.log("ZAMAN ASIMI: sunucuya girilemedi veya spawn olmadi.");
  process.exit(2);
}, 90000);

bot.once("login", () => console.log("Giris yapildi, spawn bekleniyor..."));

bot.once("spawn", () => {
  console.log("Spawn oldu. Liste icin 15 saniye bekleniyor...");
  setTimeout(() => {
    console.log("\n=== TAB LISTESI ===");
    for (const p of Object.values(bot.players)) {
      let shown = "";
      try {
        shown = p.displayName ? p.displayName.toString() : "";
      } catch (e) {}
      console.log(`isim=${p.username} | gorunen=${shown} | ping=${p.ping}`);
    }
    console.log("\n=== TAKIMLAR (rutbe oneki burada olabilir) ===");
    for (const [name, t] of Object.entries(bot.teams || {})) {
      let pre = "", suf = "";
      try {
        pre = t.prefix ? t.prefix.toString() : "";
        suf = t.suffix ? t.suffix.toString() : "";
      } catch (e) {}
      console.log(`takim=${name} | onek=${pre} | sonek=${suf} | uyeler=${(t.members || []).join(",")}`);
    }
    console.log("\nBitti.");
    clearTimeout(limit);
    bot.quit();
    setTimeout(() => process.exit(0), 1500);
  }, 15000);
});

bot.on("kicked", (r) => {
  let text = "";
  try {
    text = typeof r === "string" ? r : JSON.stringify(r);
    const m = require("prismarine-chat")(bot.registry);
    text += " || DUZ METIN: " + new m(typeof r === "string" ? JSON.parse(r) : r).toString();
  } catch (e) {}
  console.log("ATILDI: " + text);
});
bot.on("error", (e) => console.log("HATA: " + e.message));
bot.on("end", (r) => {
  console.log("Baglanti bitti: " + r);
  setTimeout(() => process.exit(3), 500);
});

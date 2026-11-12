import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "30"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"  # 1 ise Discord'a gondermez, ekrana yazar
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
if not WEBHOOK and not DRY_RUN:
    raise SystemExit("DISCORD_WEBHOOK secret'i yok")
# Sunucunun herkese acik canli haritasi (squaremap) online oyuncu listesini verir.
PLAYERS_URL = os.environ.get(
    "PLAYERS_URL", "https://map.avenormc.com/tiles/players.json"
)

CFG = json.load(open("staff.json", encoding="utf-8"))
STAFF = {k.lower(): (k, v) for k, v in CFG["staff"].items()}
RANK_ORDER = CFG["rank_order"]  # en ustteki rutbe en uste yazilir


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "avenor-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get_online_players():
    try:
        data = http_json(PLAYERS_URL)
    except Exception as e:
        print(f"Oyuncu listesi alinamadi: {e}")
        return None  # harita/sunucu kapali: bu tur sayim yapma
    return [p["name"].lstrip(".") for p in data.get("players", []) if p.get("name")]


def send(content):
    if DRY_RUN:
        print("----- DISCORD MESAJI -----")
        print(content)
        print("--------------------------")
        return
    body = json.dumps(
        {"content": content, "allowed_mentions": {"parse": []}}
    ).encode()
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "avenor-bot/1.0"},
    )
    urllib.request.urlopen(req, timeout=20).read()


def fmt_time(minutes):
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h} saat {m} dakika"
    if h:
        return f"{h} saat"
    return f"{m} dakika"


def load_state():
    try:
        return json.load(open("state.json", encoding="utf-8"))
    except Exception:
        return {"date": "", "minutes": {}}


def main():
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    state = load_state()

    # Gun degistiyse dunun birincisini tebrik et ve sifirla
    if state.get("date") != today:
        totals = state.get("minutes", {})
        if totals:
            top = max(totals, key=totals.get)
            send(
                f"🏆 **GÜNÜN EN AKTİF YETKİLİSİ**\n\n"
                f"Tebrikler **{top}**! Dün toplam **{fmt_time(totals[top])}** "
                f"aktif oldun. Emeğin için teşekkürler! 🎉"
            )
        state = {"date": today, "minutes": {}}

    players = get_online_players()
    if players is None:
        print("Liste alinamadi, sayim yapilmadi.")
        json.dump(state, open("state.json", "w", encoding="utf-8"), ensure_ascii=False)
        return

    online_staff = []
    for p in players:
        if p.lower() in STAFF:
            name, rank = STAFF[p.lower()]
            state["minutes"][name] = state["minutes"].get(name, 0) + INTERVAL_MIN
            online_staff.append((name, rank))

    online_staff.sort(
        key=lambda x: RANK_ORDER.index(x[1]) if x[1] in RANK_ORDER else 999
    )

    lines = ["**AVENOR MC AKTİF YETKİLİLER**", ""]
    if online_staff:
        lines.append(f"{len(online_staff)} Yetkili çevrimiçi.")
        lines.append("")
        for name, rank in online_staff:
            lines.append(f"- **{name}** × {rank}")
            lines.append(f"{{ Bugün {fmt_time(state['minutes'][name])} toplam aktiflik }}")
            lines.append("")
    else:
        lines.append("Şu an çevrimiçi yetkili yok.")
        lines.append("")
    lines.append(
        "**Not: Her 30 dakikada bir yetkililer mesaj olarak loglanır. "
        "Gün sonunda en çok aktif olan yetkili için tebrik mesajı gönderilir.**"
    )

    send("\n".join(lines))
    json.dump(state, open("state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

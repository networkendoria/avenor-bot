import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "30"))
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
SERVER_IP = os.environ["MC_SERVER"]  # ornek: oyna.avenor.com

CFG = json.load(open("staff.json", encoding="utf-8"))
STAFF = {k.lower(): (k, v) for k, v in CFG["staff"].items()}
RANK_ORDER = CFG["rank_order"]  # en ustteki rutbe en uste yazilir


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "avenor-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get_online_players():
    data = http_json(f"https://api.mcsrvstat.us/3/{SERVER_IP}")
    if not data.get("online"):
        return None  # sunucu kapali
    players = data.get("players", {}).get("list", []) or []
    return [p["name"] for p in players]


def send(content):
    body = json.dumps(
        {"content": content, "allowed_mentions": {"parse": ["everyone"]}}
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
        print("Sunucu kapali, sayim yapilmadi.")
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
    lines.append("")
    lines.append("@here")

    send("\n".join(lines))
    json.dump(state, open("state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

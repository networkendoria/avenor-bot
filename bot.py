import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
MAX_GAP_MIN = 40  # iki kontrol arasi bundan uzunsa (GitHub gecikmesi) en fazla bu kadar sayilir
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
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
    total = int(round(minutes))
    if total < 1:
        return "1 dakikadan az"
    h, m = divmod(total, 60)
    if h and m:
        return f"{h} saat {m} dakika"
    if h:
        return f"{h} saat"
    return f"{m} dakika"


def load_state():
    try:
        st = json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        st = {}
    st.setdefault("date", "")
    st.setdefault("minutes", {})
    st.setdefault("last_run", None)  # son basarili kontrolun zamani (epoch saniye)
    st.setdefault("prev_online", [])  # son kontrolde online olan yetkililer
    return st


def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main():
    now = datetime.now(TZ)
    now_ts = float(os.environ.get("FAKE_NOW", now.timestamp()))  # FAKE_NOW sadece test icin
    today = now.strftime("%Y-%m-%d")
    state = load_state()

    # Gun degistiyse dunun birincisini tebrik et ve sifirla
    if state["date"] != today:
        totals = state["minutes"]
        if totals:
            top = max(totals, key=totals.get)
            send(
                f"🏆 **GÜNÜN EN AKTİF YETKİLİSİ**\n\n"
                f"Tebrikler **{top}**! Dün toplam **{fmt_time(totals[top])}** "
                f"aktif oldun. Emeğin için teşekkürler! 🎉"
            )
        state["date"] = today
        state["minutes"] = {}

    players = get_online_players()
    if players is None:
        print("Liste alinamadi, sayim yapilmadi.")
        save_state(state)
        return

    online_staff = []
    for p in players:
        if p.lower() in STAFF:
            online_staff.append(STAFF[p.lower()])
    now_names = {name for name, _ in online_staff}
    prev_names = set(state["prev_online"])

    # Iki kontrol arasinda gercekte gecen sure
    if state["last_run"] is None:
        elapsed = 0.0
    else:
        elapsed = max(0.0, min((now_ts - state["last_run"]) / 60.0, MAX_GAP_MIN))

    # Iki kontrolde de online -> tam sure. Sadece birinde online (girdi/cikti) -> yarisi.
    for name in now_names | prev_names:
        credit = elapsed if (name in now_names and name in prev_names) else elapsed / 2
        state["minutes"][name] = round(state["minutes"].get(name, 0) + credit, 2)

    state["last_run"] = now_ts
    state["prev_online"] = sorted(now_names)

    online_staff.sort(
        key=lambda x: RANK_ORDER.index(x[1]) if x[1] in RANK_ORDER else 999
    )

    lines = ["**AVENOR MC AKTİF YETKİLİLER**", ""]
    if online_staff:
        lines.append(f"{len(online_staff)} Yetkili çevrimiçi.")
        lines.append("")
        for name, rank in online_staff:
            lines.append(f"- **{name}** × {rank}")
            lines.append(f"{{ Bugün {fmt_time(state['minutes'].get(name, 0))} toplam aktiflik }}")
            lines.append("")
    else:
        lines.append("Şu an çevrimiçi yetkili yok.")
        lines.append("")
    lines.append(
        "**Not: Her 30 dakikada bir yetkililer mesaj olarak loglanır. "
        "Gün sonunda en çok aktif olan yetkili için tebrik mesajı gönderilir.**"
    )

    send("\n".join(lines))
    save_state(state)


if __name__ == "__main__":
    main()

import json
import os
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
DRY_RUN = os.environ.get("DRY_RUN") == "1"  # 1 ise Discord'a gondermez, ekrana yazar
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
if not WEBHOOK and not DRY_RUN:
    raise SystemExit("DISCORD_WEBHOOK secret'i yok")

# Tek veri kaynagi: sunucunun herkese acik canli haritasi (squaremap)
PLAYERS_URL = os.environ.get(
    "PLAYERS_URL", "https://map.avenormc.com/tiles/players.json"
)
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "60"))  # kac saniyede bir siteye bakilir
RUN_MINUTES = float(os.environ.get("RUN_MINUTES", "0"))  # bir calismanin suresi (0 = tek bakis)
MAX_GAP_MIN = 5.0  # iki bakis arasi bundan uzunsa en fazla bu kadar sayilir

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
        return None  # site kapali: bu bakista sayim yapma
    return [p["name"].lstrip(".") for p in data.get("players", []) if p.get("name")]


def send(content):
    if DRY_RUN:
        print("----- DISCORD MESAJI -----")
        print(content)
        print("--------------------------")
        return
    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode()
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
    st.setdefault("last_poll", None)  # son basarili bakisin zamani (epoch saniye)
    st.setdefault("prev_online", [])  # son bakista online olan yetkililer
    return st


def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def check_new_day(state, now_dt):
    """Gun degistiyse dunun birincisini tebrik et ve sayaci sifirla."""
    today = now_dt.strftime("%Y-%m-%d")
    if state["date"] == today:
        return
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


def poll_once(state, players, now_ts):
    """Bir bakisin sonucunu isler, online yetkilileri dondurur."""
    online_staff = [STAFF[p.lower()] for p in players if p.lower() in STAFF]
    now_names = {name for name, _ in online_staff}
    prev_names = set(state["prev_online"])

    if state["last_poll"] is None:
        elapsed = 0.0
    else:
        elapsed = max(0.0, min((now_ts - state["last_poll"]) / 60.0, MAX_GAP_MIN))

    # Iki bakista da online -> tam sure. Sadece birinde (girdi/cikti) -> yarisi.
    for name in now_names | prev_names:
        credit = elapsed if (name in now_names and name in prev_names) else elapsed / 2
        state["minutes"][name] = round(state["minutes"].get(name, 0) + credit, 3)

    state["last_poll"] = now_ts
    state["prev_online"] = sorted(now_names)
    return online_staff


def build_message(state, online_staff, seen=None):
    """online_staff: su an online olanlar. seen: bu calisma boyunca gorulen tum yetkililer."""
    now_names = {name for name, _ in online_staff}
    entries = dict(seen or {})
    for name, rank in online_staff:
        entries[name] = rank
    rows = sorted(
        entries.items(),
        key=lambda x: RANK_ORDER.index(x[1]) if x[1] in RANK_ORDER else 999,
    )
    lines = ["**AVENOR MC AKTİF YETKİLİLER**", ""]
    if rows:
        if len(now_names) == len(rows):
            lines.append(f"{len(rows)} Yetkili çevrimiçi.")
        else:
            lines.append(
                f"Son 30 dakikada {len(rows)} yetkili aktifti, {len(now_names)} yetkili şu an çevrimiçi."
            )
        lines.append("")
        for name, rank in rows:
            left = "" if name in now_names else " *(çıkış yaptı)*"
            lines.append(f"- **{name}** × {rank}{left}")
            lines.append(f"{{ Bugün {fmt_time(state['minutes'].get(name, 0))} toplam aktiflik }}")
            lines.append("")
    else:
        lines.append("Şu an çevrimiçi yetkili yok.")
        lines.append("")
    # Bugun girip cikmis (yukarida listelenmeyen) yetkililerin gunluk aktifligi
    listed = {name for name, _ in rows}
    earlier = [
        (STAFF[n.lower()][0], STAFF[n.lower()][1])
        for n in state["minutes"]
        if n not in listed and n.lower() in STAFF
    ]
    earlier.sort(key=lambda x: RANK_ORDER.index(x[1]) if x[1] in RANK_ORDER else 999)
    if earlier:
        lines.append("**Bugün daha önce aktif olanlar:**")
        lines.append("")
        for name, rank in earlier:
            lines.append(f"- **{name}** × {rank}")
            lines.append(f"{{ Bugün {fmt_time(state['minutes'].get(name, 0))} toplam aktiflik }}")
            lines.append("")
    lines.append(
        "**Not: Her 30 dakikada bir yetkililer mesaj olarak loglanır. "
        "Gün sonunda en çok aktif olan yetkili için tebrik mesajı gönderilir.**"
    )
    return "\n".join(lines)


def main():
    start = time.time()
    state = load_state()
    online_staff = None  # hic basarili bakis olmazsa mesaj atilmaz
    seen = {}  # bu calisma boyunca gorulen tum yetkililer

    while True:
        now_ts = time.time()
        players = get_online_players()
        if players is not None:
            check_new_day(state, datetime.fromtimestamp(now_ts, TZ))
            online_staff = poll_once(state, players, now_ts)
            seen.update({name: rank for name, rank in online_staff})
            save_state(state)
            print(f"Bakis: {len(players)} oyuncu, {len(online_staff)} yetkili online.")
        # Sonraki bakis calisma suresini asacaksa dongu biter
        if time.time() + POLL_SECONDS - start > RUN_MINUTES * 60:
            break
        time.sleep(POLL_SECONDS)

    if online_staff is None:
        print("Hic basarili bakis olmadi, mesaj atilmadi.")
        return
    send(build_message(state, online_staff, seen))
    save_state(state)


if __name__ == "__main__":
    main()

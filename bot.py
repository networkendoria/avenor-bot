import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
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
POST_MINUTES = float(os.environ.get("POST_MINUTES", "10"))  # kac dakikada bir Discord'a mesaj atilir
MAX_GAP_MIN = 5.0  # iki bakis arasi bundan uzunsa en fazla bu kadar sayilir

CFG = json.load(open("staff.json", encoding="utf-8"))
STAFF = {k.lower(): (k, v) for k, v in CFG["staff"].items()}
RANK_ORDER = CFG["rank_order"]  # en ustteki rutbe en uste yazilir
START_DATE = CFG.get("start_date", "")  # bu tarihe (00:00) kadar hicbir sey sayilmaz/atilmaz
REPORT_DAY = 13  # aylik donem: her ayin 13'unden sonraki ayin 13'une
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "avenor-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get_online_players():
    try:
        data = http_json(PLAYERS_URL)
        if not isinstance(data, dict) or not isinstance(data.get("players"), list):
            print("Oyuncu listesi beklenen Squaremap formatinda degil; sayim atlandi.")
            return None
        names = []
        for player in data["players"]:
            if not isinstance(player, dict):
                continue
            name = player.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip().lstrip("."))
        return names
    except Exception as e:
        print(f"Oyuncu listesi alinamadi: {e}")
        return None  # site kapali/hatali: bu bakista sayim yapma


EMBED_COLOR = 0xF1C40F  # sari serit
MEDALS = ["🥇", "🥈", "🥉"]
DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def date_tr(date_str):
    """'2026-11-13' -> '13 Kasım 2026 Cuma'"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{d.day} {MONTHS[d.month - 1]} {d.year} {DAYS[d.weekday()]}"


def chunk_fields(name, entries, limit=1000):
    """Kayitlari Discord'un alan sinirini (1024 karakter) asmadan parcalara boler.
    Her kayit arasinda bir bos satir birakir."""
    chunks, cur, size = [], [], 0
    for entry in entries:
        add = len(entry) + 2
        if cur and size + add > limit:
            chunks.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(entry)
        size += add
    if cur:
        chunks.append("\n\n".join(cur))
    return [
        {"name": name if i == 0 else "\u200b", "value": text, "inline": False}
        for i, text in enumerate(chunks)
    ]


def send(embed):
    """Discord'a kenari renkli kutu (embed) olarak mesaj atar. Hata olursa botu cokertmez."""
    embed = dict(embed)
    embed["color"] = EMBED_COLOR
    embed["timestamp"] = datetime.now(TZ).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if DRY_RUN:
        print("----- DISCORD EMBED (sari serit) -----")
        print("BASLIK:", embed.get("title"))
        print("ACIKLAMA:", embed.get("description", ""))
        for f in embed.get("fields", []):
            print("[ALAN]", f["name"])
            print(f["value"])
        if embed.get("footer"):
            print("ALT YAZI:", embed["footer"]["text"])
        print("--------------------------------------")
        return True
    body = json.dumps({"embeds": [embed], "allowed_mentions": {"parse": []}}).encode()
    for attempt in range(3):
        req = urllib.request.Request(
            WEBHOOK,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "avenor-bot/1.0"},
        )
        try:
            urllib.request.urlopen(req, timeout=20).read()
            return True
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            print(f"Discord hatasi {e.code}: {detail}")
            if e.code == 429:  # cok hizli: bekleyip tekrar dene
                try:
                    wait = float(json.loads(detail).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                time.sleep(min(wait, 10))
                continue
            return False
        except Exception as e:
            print(f"Discord'a gonderilemedi: {e}")
            time.sleep(2)
    return False


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
    if not os.path.exists(STATE_FILE):
        st = {}
    else:
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                st = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"{STATE_FILE} okunamadi; veri kaybini onlemek icin bot durduruldu: {e}")
        if not isinstance(st, dict):
            raise SystemExit(f"{STATE_FILE} gecersiz; JSON nesnesi bekleniyordu.")
    st.setdefault("date", "")
    st.setdefault("minutes", {})
    st.setdefault("last_poll", None)  # son basarili bakisin zamani (epoch saniye)
    st.setdefault("prev_online", [])  # son bakista online olan yetkililer
    st.setdefault("last_post", None)  # son mesajin zamani (epoch saniye)
    st.setdefault("window_seen", {})  # son mesajdan beri gorulen yetkililer (isim -> rutbe)
    st.setdefault("history", {})  # gecmis gunler: tarih -> {isim: dakika}
    st.setdefault("last_monthly", None)  # aylik raporun gonderildigi ay (YYYY-AA)
    return st


def save_state(state):
    # Dosyayi atomik degistir; yarim yazilmis JSON birakma.
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temp_file, STATE_FILE)


def monthly_report(state, now_dt):
    """Her ayin 13'unde (kacirilirsa sonraki ilk bakista) gecen ayin 13'unden bu ayin 12'sine kadar
    en aktif 3 yetkiliyi yazar."""
    month_key = now_dt.strftime("%Y-%m")
    if state["last_monthly"] is None:
        state["last_monthly"] = month_key  # ilk kurulum: bu ay icin rapor atma
        return
    if now_dt.day < REPORT_DAY or state["last_monthly"] == month_key:
        return
    state["last_monthly"] = month_key

    end = datetime(now_dt.year, now_dt.month, REPORT_DAY, tzinfo=TZ)  # bu ayin 13'u (dahil degil)
    py, pm = (end.year - 1, 12) if end.month == 1 else (end.year, end.month - 1)
    start = datetime(py, pm, REPORT_DAY, tzinfo=TZ)  # gecen ayin 13'u (dahil)
    last_day = end - timedelta(days=1)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    totals = {}
    for day, per_person in state["history"].items():
        if start_s <= day < end_s:
            for name, minutes in per_person.items():
                totals[name] = totals.get(name, 0) + minutes
    # Rutbe gruplari ayri listelenir (staff.json -> monthly_groups). Her grubun ilk 3'u yazilir.
    groups = CFG.get("monthly_groups") or {"Yetkililer": RANK_ORDER}
    medals = ["🥇", "🥈", "🥉"]
    fields = []
    for title, ranks in groups.items():
        ranked = sorted(
            (
                (n, m)
                for n, m in totals.items()
                if n.lower() in STAFF and STAFF[n.lower()][1] in ranks and m > 0
            ),
            key=lambda x: -x[1],
        )[:3]
        if not ranked:
            continue
        rows = []
        for i, (name, minutes) in enumerate(ranked):
            real, rank = STAFF[name.lower()]
            rows.append(f"{medals[i]} **{i + 1}.** **{real}** × {rank} — {fmt_time(minutes)}")
        fields.extend(chunk_fields(title, rows))
    if fields:
        send(
            {
                "title": "📊 AYIN EN AKTİF YETKİLİLERİ",
                "description": (
                    f"**{start.day} {MONTHS[start.month - 1]} – {last_day.day} {MONTHS[last_day.month - 1]}** "
                    "arası en çok aktif olanlar:\n\u200b"
                ),
                "fields": fields,
                "footer": {"text": "AvenorMC · Aylık yetkili aktifliği"},
            }
        )


def check_new_day(state, now_dt):
    """Gun degistiyse dunun birincisini tebrik et, gunu gecmise kaydet ve sayaci sifirla."""
    today = now_dt.strftime("%Y-%m-%d")
    if state["date"] == today:
        return
    totals = state["minutes"]
    if totals:
        ranked = sorted(totals.items(), key=lambda x: -x[1])
        top, top_min = ranked[0]
        top_rank = STAFF[top.lower()][1] if top.lower() in STAFF else ""
        day_txt = date_tr(state["date"]) if state["date"] else "Dün"
        desc = (
            f"📅 **{day_txt}**\n\n"
            f"🥇 **{top}**" + (f" · {top_rank}" if top_rank else "") + "\n"
            f"⏱️ **{fmt_time(top_min)}**\n\n"
            f"Tebrikler **{top}**! Dün toplam **{fmt_time(top_min)}** "
            f"aktif oldun. Emeğin için teşekkürler! 🎉\n\u200b"
        )
        fields = []
        others = []
        for i, (name, minutes) in enumerate(ranked[1:3], start=1):
            rank = STAFF[name.lower()][1] if name.lower() in STAFF else ""
            others.append(f"{MEDALS[i]} **{name}**" + (f" · {rank}" if rank else "") + f"\n⠀⠀⏱️ {fmt_time(minutes)}")
        if others:
            fields = chunk_fields("Dünün diğer zirvedekileri", others)
        send(
            {
                "title": "🏆 GÜNÜN EN AKTİF YETKİLİSİ",
                "description": desc,
                "fields": fields,
                "footer": {"text": "AvenorMC · Günlük yetkili aktifliği"},
            }
        )
        if state["date"]:
            state["history"][state["date"]] = dict(totals)
    # 45 günden eski kayıtları temizle
    old = (now_dt - timedelta(days=45)).strftime("%Y-%m-%d")
    state["history"] = {d: v for d, v in state["history"].items() if d >= old}
    state["date"] = today
    state["minutes"] = {}
    monthly_report(state, now_dt)


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
    """Gunluk aktiflik listesi: aktiflik suresine gore sirali, kayitlar arasi bosluklu."""
    now_names = {name for name, _ in online_staff}
    seen_names = set(seen or {})
    # Bugun aktifligi kaydedilenler + son pencerede gorulenler + su an online olanlar
    names = set(state["minutes"]) | seen_names | now_names
    entries = []
    for name in names:
        key = name.lower()
        if key not in STAFF:
            continue
        real_name, rank = STAFF[key]
        entries.append((real_name, rank, state["minutes"].get(real_name, 0)))

    entries.sort(
        key=lambda item: (
            -item[2],
            RANK_ORDER.index(item[1]) if item[1] in RANK_ORDER else 999,
            item[0].lower(),
        )
    )

    online_count = len(now_names)
    offline_count = len(entries) - len([e for e in entries if e[0] in now_names])
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    desc = (
        f"🟢 **{online_count}** çevrimiçi　·　⚪ **{offline_count}** çevrimdışı\n"
        f"📅 {date_tr(today)}\n\u200b"
    )

    if entries:
        lines = []
        for index, (name, rank, minutes) in enumerate(entries, start=1):
            pos = MEDALS[index - 1] if index <= 3 and minutes >= 1 else f"**{index}.**"
            status = "🟢" if name in now_names else "⚪"
            lines.append(
                f"{pos} {status} **{name}** · {rank}\n"
                f"⠀⠀⏱️ {fmt_time(minutes)}"
            )
        fields = chunk_fields("📊 BUGÜNÜN AKTİFLİK SIRALAMASI", lines)
    else:
        fields = [{
            "name": "📊 BUGÜNÜN AKTİFLİK SIRALAMASI",
            "value": "Bugün henüz aktif yetkili kaydı bulunmuyor.",
            "inline": False,
        }]

    return {
        "title": "👥 AVENOR MC · YETKİLİ AKTİFLİĞİ",
        "description": desc,
        "fields": fields,
        "footer": {
            "text": (
                f"AvenorMC · {int(POST_MINUTES)} dakikada bir güncellenir"
                " · 🟢 Çevrimiçi  ⚪ Çevrimdışı"
            )
        },
    }


def maybe_post(state, online_staff, now_ts):
    """Son mesajin uzerinden POST_MINUTES gectiyse mesaj atar. Atildiysa True doner."""
    last = state["last_post"]
    if last is not None and (now_ts - last) < (POST_MINUTES - 0.5) * 60:
        return False
    send(build_message(state, online_staff, state["window_seen"]))
    state["window_seen"] = {}
    state["last_post"] = now_ts
    return True


def main():
    start = time.time()
    state = load_state()

    while True:
        now_ts = time.time()
        today_s = datetime.fromtimestamp(now_ts, TZ).strftime("%Y-%m-%d")
        if START_DATE and today_s < START_DATE:
            # Baslangic tarihi (00:00) gelmeden hicbir sey sayilmaz ve mesaj atilmaz
            print(f"Baslangic bekleniyor: {START_DATE} 00:00")
            if time.time() + POLL_SECONDS - start > RUN_MINUTES * 60:
                break
            time.sleep(POLL_SECONDS)
            continue
        players = get_online_players()
        if players is not None:
            check_new_day(state, datetime.fromtimestamp(now_ts, TZ))
            online_staff = poll_once(state, players, now_ts)
            state["window_seen"].update({name: rank for name, rank in online_staff})
            print(f"Bakis: {len(players)} oyuncu, {len(online_staff)} yetkili online.")
            if maybe_post(state, online_staff, now_ts):
                print("Mesaj gonderildi.")
            save_state(state)
        else:
            # Squaremap gecici olarak yanit vermese bile 10 dakikalik Discord logunu durdurma.
            # Eski online durumunu kesin bilgi gibi gostermek yerine veri hatasini acikca bildir.
            last = state["last_post"]
            if last is None or (now_ts - last) >= (POST_MINUTES - 0.5) * 60:
                send({
                    "title": "⚠️ AVENOR MC YETKİLİ LOGU",
                    "description": (
                        "Canli oyuncu listesi su anda alinamiyor. "
                        "Bu nedenle guncel cevrimici durum dogrulanamadi; "
                        "bir sonraki kontrolde tekrar denenecek."
                    ),
                    "footer": {"text": "AvenorMC · Veri kaynagi gecici olarak erisilemiyor"},
                })
                state["last_post"] = now_ts
                save_state(state)
                print("Veri kaynagi hatasi loglandi.")
        # Sonraki bakis calisma suresini asacaksa dongu biter
        if time.time() + POLL_SECONDS - start > RUN_MINUTES * 60:
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

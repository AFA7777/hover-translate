#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_dict — 把 ECDICT 建成本地繁體離線字典 dict.db。

這支程式**只在建字典時跑一次**，是整個專案唯一會連網的地方。
建完之後 hover_translate.py 執行期完全不連網，這支和兩個來源 csv 都可以刪掉。

  python build_dict.py            # 缺檔才下載，然後建 dict.db
  python build_dict.py --verify   # 只驗證現有 dict.db，不重建

來源：github.com/skywind3000/ECDICT（MIT）
  ecdict.csv    62.9 MB  詞條本體
  lemma.en.txt   2.2 MB  詞形還原表（generates -> generate）
"""

import csv
import os
import sqlite3
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "ecdict.csv")
LEMMA_PATH = os.path.join(BASE, "lemma.en.txt")
DB_PATH = os.path.join(BASE, "dict.db")
FIX_PATH = os.path.join(BASE, "用語修正.txt")
RAW = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/"

# OpenCC 的 s2twp 對資訊用語幾乎完美（软件→軟體、内存→記憶體、算法→演算法），
# 但遇到台灣用不同「構詞」而非不同「字」的術語就無能為力，最典型的是
# 线粒体 → 線粒體（台灣是粒線體，字序不同）。這張表在執行期補救。
#
# 左邊是 OpenCC 轉完後的繁體字串，右邊是台灣慣用語。
# 刻意排除歧義詞：函數（數學用函數、程式用函式，兩者台灣都對）、
# 數據（大數據是台灣正式用語）、文件（也指 document）、類、模擬、刷新。
DEFAULT_FIXES = """\
# 台灣用語修正表 —— 在 OpenCC 簡轉繁之後套用
#
# 格式：  簡轉繁後的詞=台灣慣用語        （# 開頭是註解，空行忽略）
# 改完存檔，重啟 hover_translate.py 即生效，不需要重建 dict.db。
#
# 注意：這是無條件字串取代。不要加入短詞或多義詞，例如把「類=類別」加進來，
# 會把「人類」變成「人類別」。只加不會誤傷的完整術語。

# ── 生物 / 醫學 ──
線粒體=粒線體
高爾基體=高基氏體
溶酶體=溶體
過氧化物酶體=過氧化體
脫氧核糖核酸=去氧核糖核酸
脫氧核糖=去氧核糖
質粒=質體
氨基酸=胺基酸
色氨酸=色胺酸
酪氨酸=酪胺酸
苯丙氨酸=苯丙胺酸
谷氨酸=麩胺酸
賴氨酸=離胺酸
艾滋病=愛滋病
激素=荷爾蒙
信息素=費洛蒙
爬行動物=爬蟲類
兩棲動物=兩棲類
哺乳動物=哺乳類

# ── 物理 / 化學 ──
激光=雷射
鐳射=雷射
等離子體=電漿
中微子=微中子
摩爾質量=莫耳質量
阿伏伽德羅=亞佛加厥
薛定諤=薛丁格
玻爾=波耳
晶體管=電晶體
二極管=二極體
三極管=三極體
集成電路=積體電路
地幔=地函

# ── 數學 / 統計 ──
概率=機率
方差=變異數
素數=質數
最大公約數=最大公因數
拓撲=拓樸
均值=平均值

# ── 資訊 / 電機（補 OpenCC 沒蓋到的）──
服務器=伺服器
默認=預設
缺省=預設
字節=位元組
比特=位元
數組=陣列
隊列=佇列
鏈表=鏈結串列
指針=指標
變量=變數
常量=常數
對象=物件
接口=介面
線程=執行緒
進程=行程
緩存=快取
高速緩衝儲存器=快取記憶體
緩衝儲存器=快取記憶體
解釋器=直譯器
調試=除錯
源代碼=原始碼
編程=程式設計
運算符=運算子
標識符=識別字
分辨率=解析度
帶寬=頻寬
黑客=駭客
用戶=使用者
登錄=登入
註銷=登出
菜單=選單
窗口=視窗
剪貼板=剪貼簿
快捷鍵=快速鍵
卸載=解除安裝
解壓=解壓縮
插件=外掛
補丁=修補程式
數字簽名=數位簽章
數碼=數位
硬盤=硬碟
軟盤=磁片
光盤=光碟
優盤=隨身碟
顯卡=顯示卡
主板=主機板
筆記本電腦=筆記型電腦
臺式機=桌上型電腦
智能手機=智慧型手機
攝像頭=網路攝影機
掃描儀=掃描器
音頻=音訊
矢量=向量
傳感器=感測器
執行器=致動器
反饋=回饋
閉環=閉迴路
開環=開迴路
信號=訊號
噪聲=雜訊
採樣=取樣
調製=調變
聲吶=聲納
可再生能源=再生能源
核電站=核電廠
變電站=變電所
"""


def download(name, path):
    if os.path.exists(path) and os.path.getsize(path) > 100000:
        print(f"  {name} 已存在，跳過下載")
        return
    print(f"  下載 {name} …", end="", flush=True)
    t = time.time()
    req = urllib.request.Request(RAW + name, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(path, "wb") as f:
        n = 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            n += len(b)
    print(f" {n/1048576:.1f} MB / {time.time()-t:.1f}s")


def load_lemma():
    """lemma.en.txt 格式： base/詞頻 -> form1,form2,…"""
    out = {}
    with open(LEMMA_PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";") or "->" not in line:
                continue
            left, right = line.split("->", 1)
            base = left.split("/")[0].strip().lower()
            for form in right.split(","):
                form = form.strip().lower()
                if form and form != base:
                    out[form] = base
    return out


# ECDICT exchange 欄位： p:過去式 d:過去分詞 i:現在分詞 3:三單 r:比較級
# t:最高級 s:複數 0:原型 1:變換類型
INFLECTED_KEYS = set("pdi3rts")


def build():
    print("\n[1/5] 取得來源檔")
    download("ecdict.csv", CSV_PATH)
    download("lemma.en.txt", LEMMA_PATH)

    print("\n[2/5] 載入詞形還原表")
    lemma = load_lemma()
    print(f"  lemma.en.txt: {len(lemma):,} 條")

    print("\n[3/5] 讀取 ECDICT 並簡轉繁（s2twp）")
    import opencc
    cc = opencc.OpenCC("s2twp")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE words(
            word TEXT PRIMARY KEY,   -- 小寫，查詢鍵
            disp TEXT,               -- 原始大小寫
            phonetic TEXT,
            trans TEXT,              -- 繁體釋義，義項以 \\n 分隔
            pos TEXT,
            collins INTEGER,
            frq INTEGER,
            tag TEXT
        );
        CREATE TABLE lemma(form TEXT PRIMARY KEY, base TEXT);
    """)

    csv.field_size_limit(10 ** 7)
    rows, kept, skipped, t0 = [], 0, 0, time.time()
    with open(CSV_PATH, encoding="utf-8", newline="", errors="replace") as f:
        rd = csv.DictReader(f)
        for i, r in enumerate(rd, 1):
            word = (r.get("word") or "").strip()
            trans = (r.get("translation") or "").strip()
            if not word or not trans:
                skipped += 1
                continue
            key = word.lower()

            # exchange 補進詞形表：0:原型 反查，其餘是本字的變化形
            ex = r.get("exchange") or ""
            if ex:
                for part in ex.split("/"):
                    if ":" not in part:
                        continue
                    k, v = part.split(":", 1)
                    v = v.strip().lower()
                    if not v:
                        continue
                    if k == "0" and v != key:
                        lemma.setdefault(key, v)
                    elif k in INFLECTED_KEYS and v != key:
                        lemma.setdefault(v, key)

            def num(x):
                try:
                    return int(x)
                except (TypeError, ValueError):
                    return 0

            rows.append((key, word, (r.get("phonetic") or "").strip(),
                         cc.convert(trans.replace("\\n", "\n")),
                         (r.get("pos") or "").strip(),
                         num(r.get("collins")), num(r.get("frq")),
                         (r.get("tag") or "").strip()))
            kept += 1
            if len(rows) >= 20000:
                db.executemany("INSERT OR REPLACE INTO words VALUES(?,?,?,?,?,?,?,?)", rows)
                rows.clear()
                print(f"\r  已處理 {i:,} 列（收錄 {kept:,}）"
                      f" {int(time.time()-t0)}s", end="", flush=True)
    if rows:
        db.executemany("INSERT OR REPLACE INTO words VALUES(?,?,?,?,?,?,?,?)", rows)
    print(f"\r  完成：收錄 {kept:,} 詞，略過 {skipped:,} 筆（無中文釋義）"
          f" 共 {int(time.time()-t0)}s")

    print("\n[4/5] 寫入詞形還原表")
    db.executemany("INSERT OR REPLACE INTO lemma VALUES(?,?)", lemma.items())
    print(f"  合併 ECDICT exchange 後共 {len(lemma):,} 條")

    db.execute("CREATE INDEX idx_lemma ON lemma(form)")
    db.commit()
    db.execute("VACUUM")
    db.commit()
    db.close()

    if not os.path.exists(FIX_PATH):
        with open(FIX_PATH, "w", encoding="utf-8") as f:
            f.write(DEFAULT_FIXES)
        print(f"  已產生 {os.path.basename(FIX_PATH)}")
    else:
        print(f"  {os.path.basename(FIX_PATH)} 已存在，保留你的修改")

    print(f"\n[5/5] dict.db 建立完成："
          f"{os.path.getsize(DB_PATH)/1048576:.1f} MB")


SAMPLES = ["mitochondrion", "generates", "ran", "better", "chloroplast",
           "algorithm", "semiconductor", "probability", "laser", "thread",
           "cache", "variance", "plasma", "neutrino", "eigenvalue",
           "mice", "children", "studying", "acquisition", "serendipity"]


def verify():
    """實測查詢品質，並回報用語修正表命中了哪些。"""
    sys.path.insert(0, BASE)
    from hover_translate import LocalDict
    d = LocalDict(DB_PATH, FIX_PATH)
    print(f"\n=== 查詢實測（字典 {d.count():,} 詞，修正表 {len(d.fixes)} 條）===")
    miss = []
    for w in SAMPLES:
        e = d.lookup(w)
        if not e:
            miss.append(w)
            print(f"  {w:16s} → （查不到）")
            continue
        via = f"  ←{e['via']}" if e.get("via") else ""
        first = e["trans"].split("\n")[0][:60]
        print(f"  {w:16s} → {first}{via}")
        if e.get("phonetic"):
            print(f"  {'':16s}   [{e['phonetic']}]")
    print(f"\n  查得 {len(SAMPLES)-len(miss)}/{len(SAMPLES)}"
          + (f"，查不到：{miss}" if miss else ""))


if __name__ == "__main__":
    if "--verify" in sys.argv:
        verify()
    else:
        build()
        verify()

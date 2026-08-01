---
name: hover-translate
description: Starts, stops, tunes, and troubleshoots hover_translate — a resident Windows tool that speaks the English word under the mouse cursor aloud and then says its Traditional Chinese meaning, using a fully offline local dictionary (no network at runtime). Trigger whenever the user wants to hover the mouse over English text on screen and hear it pronounced and/or rendered in 繁體中文, or refers to 滑鼠翻譯 / 滑鼠指到英文 / 螢幕取詞 / 即時發音 / 查單字工具 / 懸浮翻譯 / 離線字典 / hover translate / screen OCR dictionary. Also use for follow-up requests about that tool — 啟動 / 開啟 / 關掉 / 暫停, changing the trigger key or dwell time, adjusting voices or speech rate, widening the capture box, fixing OCR misreads, fixing a wrong Traditional Chinese term (用語修正.txt), rebuilding the dictionary, adding Japanese support, or questions about its privacy/security posture. Do NOT use this skill to translate text the user has already pasted into chat — that needs no tool.
---

# hover-translate

滑鼠指到螢幕上的英文 → 唸出英文發音 → 用繁體中文說出釋義。**執行期完全離線。**

**專案位置：`<你解壓縮的資料夾>`** —— 下面命令中的 `<專案資料夾>` 請換成實際路徑，或直接告訴 Claude 路徑在哪。

```
hover_translate.py   主程式（單檔常駐，無任何網路模組）
install.py           一鍵安裝的實作（裝套件→建字典→放捷徑）
make_shortcut.py     建立桌面捷徑的實作（win32com，不用 PowerShell）
一鍵安裝.bat          分享給別人時對方唯一要點的檔案（純 ASCII 薄殼）
建立桌面捷徑.bat      重建桌面捷徑「即時翻譯」（純 ASCII 薄殼）
setup.bat / run.bat / make-shortcut.bat
                     上面三個 bat 的 ASCII 檔名別名，內容完全相同。
                     改任一個都要同步改對應的別名，否則兩者行為分歧。
給收到的人.txt        給非技術使用者的安裝與使用說明
skill/SKILL.md       本檔的可攜版（路徑已抽換），隨分享包一起發
icon.ico             捷徑圖示
hover_translate.log  無主控台啟動時的輸出（每次啟動附加一段）
build_dict.py        字典建置（唯一會連網的地方，只跑一次）
selftest.py          端到端自測
dict.db              本地繁體字典 79 MB / 768,739 詞（build_dict.py 產生）
用語修正.txt          台灣用語對照表，執行期套用，改完重啟即生效
config.json          使用者設定（首次執行自動產生）
啟動.bat             雙擊啟動
README.md            完整說明與設定表
```

**`ecdict.csv` 與 `lemma.en.txt` 已於 2026-07-31 刪除**（省 65 MB）。它們只有重建字典時才需要，`build_dict.py` 偵測到不在會自動重新下載。資料夾現在總共約 79 MB，幾乎全是 `dict.db`。

## 最重要的兩件事

**一、skill 本身不能監聽滑鼠。** Claude Code 的 skill 是一份指令檔，只在對話回合內執行。真正做 hover 偵測的是那支常駐的 Python 程式；這個 skill 的工作是**啟動它、調它、修它**。

使用者說「幫我開啟滑鼠翻譯」時，不要試圖用 computer-use 每秒截圖去模擬 —— 那又慢又貴又不可靠。直接啟動那支程式。

**二、執行期零連線是這個專案刻意維持的性質，不要破壞它。**
`hover_translate.py` 原始碼裡不可以出現 `urllib` / `socket` / `http` / `requests` / `ssl`。`selftest.py` 有兩道測試在守這件事（封鎖 socket 後查詢仍須成功、掃描原始碼確認無網路模組）。使用者是為了資安才從線上翻譯換成離線字典的 —— 若要加回任何連線功能，**必須先明確詢問並說明取捨**。

**三、文件敘述必須與程式行為一致，這是專案被公開審查的重點。**
2026-08-01 一份第三方資安審查抓到三處文件與實際不符，全部成立：

- `hover_translate.py` 的開頭 docstring 還留著「免費線上翻譯、寫入 SQLite 快取」—— 離線化之後忘了改。**審查者第一個讀的就是這個檔案的開頭**，說明與行為對不上本身就是紅旗。
- README 寫「原始碼裡 urllib 一律不存在」，但 `build_dict.py` 確實用了 `urllib.request`。正確說法要限定在**主程式**。
- README 寫「磁碟殘留：無」，但 `debug: true` 會把 OCR 到的單字與該行前 60 字元寫進 `hover_translate.log`（無主控台啟動時）。

改動架構後**務必回頭檢查 docstring 與 README**。selftest 現在有一項會掃主程式開頭是否殘留 `線上翻譯` / `SQLite 快取` / `cache.db` / `googleapis` 等舊詞。

## 啟動

**使用者有桌面捷徑「即時翻譯」，不需要 Claude 就能自己啟動。** 如果他只是問「怎麼開」，先告訴他雙擊桌面捷徑就好，不用叫他回來找你。

捷徑走 `pythonw.exe`（無主控台），輸出寫進 `hover_translate.log`。捷徑壞了或資料夾搬過，叫他雙擊 `建立桌面捷徑.bat` 重建。

程式有**單一實例鎖**（具名 mutex `hover_translate_single_instance_v1`）。重複啟動會跳提示並直接結束，所以不會有多份搶麥克風。除錯時若發現「啟動沒反應」，先確認是不是已經有一份在跑。

要由你代為啟動時，背景啟動、不要卡住對話（用 Bash tool 的 `run_in_background: true`）：

```bash
cd "<專案資料夾>" && python hover_translate.py
```

啟動後把操作方式告訴使用者：

- 按住 `Ctrl` + 滑鼠停在英文字上約 0.4 秒 = 觸發
- **`Esc` 連按兩下 = 結束**（第一次按提示「再按一次 Esc 結束」，結束時浮窗顯示「即時翻譯停止」）
- `Ctrl+Alt+H` 暫停 / 恢復
- `Ctrl+Alt+Q` 結束

約 1 秒內會印出 OCR 引擎語言、字典詞數、系統語音清單；有印出來就代表初始化成功。

首次在新機器上：

```bash
python -m pip install winsdk pywin32
python build_dict.py
```

## 停止

告訴使用者 **`Esc` 連按兩下**（最快）或 `Ctrl+Alt+Q`，或：

```bash
powershell "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | Where-Object { $_.CommandLine -like '*hover_translate*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
```

它不會自己再啟動 —— 沒有開機自動執行、沒有服務、沒有排程。

## 改設定

改 `config.json` 就好，**不要改程式碼**。完整欄位表在 `README.md`。改完必須重啟程式才生效 —— 改完記得順手重啟，不要留給使用者。

| 使用者說 | 改哪裡 |
|---|---|
| 太吵 / 誤觸太多 | `dwell_ms` 調大到 600–800；或 `modifier` 換成 `"alt"` |
| 不想按鍵，滑過去就唸 | `modifier` 設 `"none"`（先提醒會很吵） |
| 不要唸中文，只要看 | `speak_chinese: false` |
| 只要發音不要釋義 | `speak_chinese: false` + `max_senses: 1` |
| 想練聽力，唸整句 | `speak_sentence_english: true` |
| 唸太快 / 太慢 | `english_rate` / `chinese_rate`，範圍 `-10` ~ `10` |
| 義項太多太雜 | `max_senses` 調成 2 |
| 不要音標 | `show_phonetic: false` |
| 浮窗太透明／看不清楚 | `opacity` 調高（1.0 = 全不透明）。使用者目前設 `0.9`（九成實心、一成穿透） |
| 想更透明 | `opacity` 調低，但**先提醒**：低於 0.6 底下文字會透上來，最暗的整句那行會先糊掉。真的要透就同時把 `FG_NOTE` 調亮或 `show_sentence: false` |
| 不想看到整句 | `show_sentence: false` |
| Esc 按一下就要關 | `esc_quit: "single"`（先提醒 Esc 是日常最常按的鍵，容易誤關） |
| Esc 常誤觸關掉程式 | `esc_quit: "off"`，或把 `esc_double_ms` 調小到 300 |
| 不要結束時的浮窗 | `quit_toast_ms: 0` |
| 小字認不出來 | `ocr_scale` 調 3 |
| 浮窗消失太快 | `hide_after_ms` 調大 |
| 字太小看不清 | `font_size_word` / `font_size_trans` 調大 |
| 星號/考試標籤看不懂或不想要 | 見下面「浮窗上的 ★ 與標籤」 |

改 `App.quit()` 時注意：**一定要先 `time.sleep` 再把 `self.running` 設 False**。pump() 一看到 running 為假就 `root.destroy()`，浮窗會連同視窗立刻消失，使用者只看得到一閃。selftest 有一項在守這個順序。

## 浮窗外觀

深色卡片，四層明度階：單字＋音標 → 主要釋義（`FG_TRANS` 綠，全窗唯一高彩度）→ 其餘義項（`FG_SENSE` 灰）→ 分隔線 → 整句（`FG_NOTE` 最暗）→ 星級（暖金）與考試標籤。

**圓角/外框/陰影交給 DWM**（`_apply_dwm_style()`，Win11 的 `DwmSetWindowAttribute`），GPU 合成、零執行成本、不需要 Pillow。非 Win11 靜默失敗退回直角。

改配色只改 Overlay 的類別常數（`BG` / `FG_*` / `DIVIDER` / `BORDER`）。**改 `BORDER` 要記得它是傳給 DWM 的，需經 `colorref()` 轉成 `0x00BBGGRR`**，直接塞 `#rrggbb` 會變成錯的顏色。

兩個容易再踩的坑：

- **`self.win` 的底色必須等於 `BG`。** `body` 的外距會讓 Toplevel 透出來，預設白色會在卡片下緣露出一條白邊。selftest 有一項在守。
- **加動畫要三思。** 目前所有美化都是靜態屬性，沒有計時器、沒有逐格重繪，所以閒置 CPU 是 0。淡入淡出會讓浮窗每次觸發都多跑十幾格，違背使用者「不佔速度」的要求。

實測：浮窗渲染中位數 6.7ms、字典查詢 0.03ms、閒置 12 秒 CPU 0ms、私有記憶體約 60MB。

## 浮窗上的 ★ 與標籤

義項下方那行小字是 `Overlay.show()` 組出來的 `tags`，兩部分：

**★ = Collins 詞頻星級**（`words.collins`，1–5）。星越多越基礎。全字典 76 萬詞中只有約 1.36 萬詞有星級：

| 星級 | 詞數 | 代表字 |
|---|---|---|
| ★★★★★ | 630 | the, be, and, of, a, to |
| ★★★★ | 1,009 | will, use, may, while, hand |
| ★★★ | 1,418 | make, know, part, right, live |
| ★★ | 3,036 | in, can, up, well, down |
| ★ | 7,540 | take, just, even, might, home |

沒星 = 專業術語或冷僻字（`mitochondrion`、`eigenvalue` 都沒星）。

**考試標籤**（`words.tag`）：`gre` 7,504 詞、`toefl` 6,974、`cet6` 5,407、`ielts` 5,040、`ky` 4,801、`cet4` 3,849、`gk` 3,677、`zk` 1,603。

`zk`/`gk`/`ky`/`cet4`/`cet6` 是中國的中考／高考／考研／四六級，對台灣使用者沒意義，**使用者已明確要求隱藏**。現在由 `config.json` 的 `exam_tags` 白名單控制，預設 `["toefl","ielts","gre"]`，並透過 `Overlay.EXAM_LABEL` 顯示成中文（托福／雅思／GRE）。設成 `[]` 可整排關閉；`show_stars: false` 可關星級。

**ECDICT 沒有多益（TOEIC）資料** —— 標籤只有上面那八種，查過 `toeic`/`bec` 都是 0 筆。使用者曾要求加「多益」，確認資料不存在後撤回。若日後要補，需要另尋一份 TOEIC 詞表匯入 `words.tag`，然後在 `EXAM_LABEL` 加 `"toeic": "多益"`、把 `toeic` 放進 `exam_tags` 即可 —— **不要用詞頻去「估算」多益範圍再標成多益，那是造假**。

## 翻譯詞不對時 → 改 `用語修正.txt`

**這是最常見的維護工作。** ECDICT 釋義是簡體，用 OpenCC `s2twp` 轉繁。資訊類幾乎完美（软件→軟體、内存→記憶體、算法→演算法），但 OpenCC 處理不了台灣用**不同構詞**的術語 —— 例如 `线粒体` 只會變成「線粒體」，台灣叫「粒線體」。

`用語修正.txt` 是純文字對照表，格式 `轉繁後的詞=台灣慣用語`，在**執行期**套用。改完存檔重啟程式即生效，**不需要重建 dict.db**。

加新規則前先確認實際查到什麼：

```bash
cd "<專案資料夾>" && python -c "import sys;sys.stdout.reconfigure(encoding='utf-8');from hover_translate import LocalDict;print(LocalDict().lookup('laser')['senses'])"
```

**加規則的鐵則：這是無條件字串取代，不要加短詞或多義詞。** 加 `類=類別` 會把「人類」變成「人類別」。已刻意排除的：函數（數學用函數、程式用函式，台灣兩者都對）、數據（大數據是台灣正式用語）、文件（也指 document）、模擬、刷新。

新增規則後**同時**更新 `build_dict.py` 的 `DEFAULT_FIXES`，否則使用者重建字典時會退回舊版。

## 出問題時

**先跑自測**，它會逐項指出哪一段壞了：

```bash
cd "<專案資料夾>" && python selftest.py
```

只想重驗字典查詢品質（含 20 個代表性單字）：

```bash
cd "<專案資料夾>" && python build_dict.py --verify
```

| 症狀 | 原因與處理 |
|---|---|
| 雙擊捷徑沒反應 | 多半是已經有一份在跑（單一實例鎖擋掉了）。否則看 `hover_translate.log` 最後一段 |
| 捷徑指到錯的路徑 | 雙擊 `建立桌面捷徑.bat` 重建 |
| 啟動就報 FileNotFoundError | `dict.db` 不在，跑 `python build_dict.py` |
| 完全沒反應 | 先確認程式還在跑。再把 `debug: true` 打開重啟，會印出 OCR 全文與各段耗時 —— 看是 OCR 沒認到字，還是挑字挑不到 |
| 唸錯字 / 抓到隔壁的字 | `debug` 看 OCR 全文。OCR 本身讀錯就調高 `ocr_scale`；OCR 對但挑錯是游標座標問題，檢查 DPI 縮放 |
| 有浮窗但不出聲 | 自測第 5 段驗證語音。`english_voice` / `chinese_voice` 是**關鍵字比對**系統已裝的 SAPI 語音名稱，用自測印出的實際清單去對 |
| 顯示「字典查無此字」 | ECDICT 收錄到 2020 年前後，新詞/專有名詞查不到，屬正常。可自行 INSERT 進 `dict.db` 的 `words` 表 |
| 釋義是簡體或中國用語 | 改 `用語修正.txt`，見上一節 |
| 座標整體偏移 | DPI。啟動時已宣告 `PER_MONITOR_DPI_AWARE`；使用者改過螢幕縮放就重啟程式 |
| 全螢幕遊戲抓不到畫面 | 獨佔全螢幕無法 BitBlt，請使用者切視窗化或無邊框視窗 |

## 供應鏈：已鎖定，不要放寬

2026-08-01 依資安審查建議完成三項鎖定，**改動時不要退回寬鬆設定**：

| 項目 | 現況 |
|---|---|
| ECDICT 來源 | 鎖定 commit `bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b`（2025-03-28），**不是 master** |
| 下載完整性 | `build_dict.py` 驗證兩個來源檔的 SHA-256，不符就刪檔並中止 |
| 套件版本 | `winsdk==1.0.0b10`、`pywin32==312`、`opencc==0.1.7`，`requirements.txt` 與 `install.py` 必須一致 |

要跟進上游更新時（ECDICT 更新頻率極低，2025-03 之後未動）：

```bash
cd "<專案資料夾>" && python build_dict.py --hash <新的-commit-sha>
```

它會印出可直接貼回 `build_dict.py` 的 `ECDICT_COMMIT` 與 `SHA256` 常數。改完跑 `selftest.py`，有四項在守這些不變量（鎖 commit、有雜湊驗證、requirements 無 `>=`、docstring 無舊詞）。

## debug 模式有隱私副作用

`debug: true` 會經由 `log()` 印出 OCR 辨識到的單字與該行前 60 字元。**用桌面捷徑（pythonw，無主控台）啟動時，這些內容會落到 `hover_translate.log`。**

所以要使用者開 debug 除錯時，**必須同時提醒**：不要在有成績、個資、密碼、機密文件的畫面上開，除完錯記得關掉並刪除 `hover_translate.log`。README 已有警告方塊。

## 要改架構時

**加日文支援**：OCR 已有 `ja` 語言包，SAPI 有 `Microsoft Haruka Desktop`(ja-JP)。要改 `WORD_RE`（目前只收 `[A-Za-z'\-]`），並需要一份日中字典 —— ECDICT 沒有。

**改成唸整句而非單字**：`handle()` 裡已同時取得 `word` 和 `sentence`，把送進 `speaker.say` 的對象換掉即可。注意整句沒有翻譯（離線字典只查單字）。

**加系統列圖示**：需要 `pystray`。目前沒有 —— 平常走桌面捷徑（`pythonw`，無主控台），所以**執行中沒有任何視覺指示**，使用者只能靠「按住 Ctrl 有沒有反應」判斷它在不在跑。單一實例鎖與結束浮窗就是為了補這個缺口。使用者若抱怨「不知道到底有沒有開」，系統列圖示是正解，`icon.ico` 已經現成可用。

**加回線上翻譯**：見上面「最重要的兩件事」第二點 —— 這會推翻使用者當初的資安決定，**先問過再說**。真要做就設成預設關閉的選項，並保留離線為預設路徑。

動程式碼後一律重跑 `selftest.py`，全綠才交付。

## 環境事實（每台機器不同，請先實測）

**不要沿用別人機器的數值。** 跑一次 `python selftest.py`，它會印出這台機器實際的：

- Windows OCR 可用語言（決定 `ocr_language` 怎麼設）
- 已安裝的 SAPI 語音名稱（決定 `english_voice` / `chinese_voice` 填什麼）

原作者機器上的情況供參考：OCR 只有 `ja` 與 `zh-Hant-TW`（**沒有英文語言包**），但
zh-Hant-TW 引擎辨識英文完全正確，所以不必特地去裝英文包。語音是 Zira(en-US)、
Hanhan(zh-TW)、Haruka(ja-JP)。**你的機器很可能不一樣。**

## 跨機器都成立的技術事實

- 主控台在繁中 Windows 是 cp950，印中文會丟 `UnicodeEncodeError`。主程式已
  `reconfigure(encoding="utf-8")`；**新寫的輔助腳本也要照做**，否則會被這個假錯誤誤導
- 64 位元下所有 ctypes 的 Win32 呼叫**必須設 `argtypes` / `restype`**，否則 handle
  會被截成 int32 而炸 `OverflowError`
- ECDICT 的 `translation` 欄位用**字面 `\n`**（兩個字元）分隔義項，不是真換行
- 程式碼沒有任何絕對路徑，靠 `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`
  定位，所以資料夾放哪、路徑有沒有中文都能跑

## 安裝到自己的 Claude Code

把這個 `skill` 資料夾裡的 `SKILL.md` 複製到：

```
%USERPROFILE%\.claude\skills\hover-translate\SKILL.md
```

之後在對話裡打 `/hover-translate`，或提到「滑鼠翻譯」「螢幕取詞」就會自動載入。
**平常使用完全不需要這個 skill** —— 雙擊桌面捷徑即可；skill 只在要調設定或除錯時有用。

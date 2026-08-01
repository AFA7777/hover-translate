# hover-translate

> **A fully offline hover dictionary for Windows** — screen OCR, no cloud, no telemetry

**Hold `Ctrl` and rest the mouse on any English word on screen for ~0.4s** — it pronounces the word aloud, pops up the phonetic spelling and a Traditional Chinese definition, then speaks the meaning in Chinese.

*[繁體中文](README.md)*

![Screenshot](docs/hero.png)

Works over any window: PDFs, video subtitles, text baked into images, game UIs, anything you cannot select. It reads the **screen pixels**, not a text selection.

## How this differs from other screen translators

| | This project | Typical screen translator |
|---|---|---|
| **Network** | **Zero connections** at runtime; works with the app firewalled off | Calls a cloud translation API |
| **Privacy** | What you look up never leaves your machine | Every lookup is sent to a third party |
| **Chinese** | **Traditional / Taiwan usage**, 104 hand-curated corrections | Usually Simplified or mainland phrasing |
| **OCR** | Windows built-in engine — **331 KB download** | PaddleOCR and friends: hundreds of MB of models |
| **Speech** | English + Chinese, both offline (SAPI) | Often no speech at all |
| **Latency** | 0.03ms lookup | 100–500ms network round trip |

The trade-off is **no context disambiguation** — the dictionary lists every sense rather than picking one for the sentence. Great for looking up words; not a sentence translator.

---

## What it does and does not do

A tool that captures your screen deserves scrutiny, so here it is up front:

| | |
|---|---|
| Keylogging | **No.** It polls the *pressed state* of the trigger key (Ctrl by default; Alt or Shift are configurable) plus H / Q / Esc. Keystroke content is never read or stored. |
| Network access | **Not in the main program.** `hover_translate.py` contains no networking module; verify with a firewall. **`build_dict.py` does** — see below. |
| Screen capture | Only while you hold the trigger key and dwell — one 900×90 px grab around the cursor. No recording; nothing written to disk by default. |
| Data on disk | **None** in normal use (no query history, dictionary is read-only). **Except under `debug: true`** — see the warning below. |
| Admin rights | **Not required.** |
| Autostart | **No.** No registry keys, no service, no scheduled task. |

**To be precise about network access:**

- **`hover_translate.py` (what you run day to day)** — `urllib` / `socket` / `http` / `requests` / `ssl` appear nowhere in it. `selftest.py` enforces this with two checks: lookups must still succeed after `socket.socket` is blocked, and a source scan must find no networking imports.
- **`build_dict.py` (runs once, at dictionary build time)** — uses `urllib.request` to fetch ECDICT from GitHub. This is the project's only network access, and the file can be deleted afterwards.

> ### ⚠️ `debug: true` writes on-screen text to disk
>
> With debug enabled, the program logs the recognised word and the first 60 characters of its line. When launched from the desktop shortcut (no console), that goes into `hover_translate.log`.
>
> **Do not enable `debug` while grades, personal data, passwords or confidential documents are on screen.** Leave it at the default `false`; if you do turn it on, turn it back off and delete `hover_translate.log` afterwards.

---

## Install

Requires **Windows 10/11** and **Python 3.8+**.

```bash
git clone https://github.com/AFA7777/hover-translate.git
cd hover-translate
python install.py
```

Or without a terminal: hit the green **Code → Download ZIP**, extract, and double-click **`setup.bat`**.

The installer pulls the dependencies, downloads and builds the offline dictionary (2–3 minutes), and puts a shortcut on your desktop.

Every batch file ships under both a Chinese and an ASCII name, with identical contents — use whichever your environment displays properly:

| Chinese name | ASCII alias | Purpose |
|---|---|---|
| `一鍵安裝.bat` | `setup.bat` | Install |
| `啟動.bat` | `run.bat` | Launch with a console window (for messages / debugging) |
| `建立桌面捷徑.bat` | `make-shortcut.bat` | Rebuild the desktop shortcut |

> If Python is missing, install it from [python.org](https://www.python.org/downloads/) and **tick "Add Python to PATH"** at the bottom of the installer — that is the usual stumbling block.

### Getting a blue "Windows protected your PC" warning?

Windows tags every file inside a downloaded ZIP as internet-sourced, so running any `.bat` from it triggers SmartScreen. **This happens with any downloaded batch file — it is not specific to this program.**

Two ways around it:

- **Unblock before extracting (recommended, fixes everything at once):** right-click the downloaded ZIP → Properties → tick "Unblock" at the bottom of the General tab → OK → then extract.
- **Allow at run time:** click "More info" → "Run anyway".

The program is not code-signed (that requires a paid certificate), so the warning is unavoidable. All source is in this repository for inspection.

---

## Usage

| Action | Effect |
|---|---|
| Hold `Ctrl` + dwell 0.4s | Look up and speak |
| `Esc` twice | Quit |
| `Ctrl+Alt+H` | Pause / resume |
| `Ctrl+Alt+Q` | Quit |

`Esc` requires a **double press** within 0.6s by default. Esc is one of the most frequently pressed keys in normal use and this is a global hook — a single-press quit would kill the app several times a day by accident. The first press shows a "press Esc again to quit" hint.

<table>
<tr>
<td><img src="docs/word-technical.png" alt="Technical term"></td>
<td><img src="docs/word-inflected.png" alt="Inflected form"></td>
</tr>
<tr>
<td align="center">Technical term (no frequency stars)</td>
<td align="center">Inflected forms resolve to the lemma and gain its full definition</td>
</tr>
</table>

The popup is layered brightest-to-dimmest: **word + phonetics → primary sense (green) → other senses (grey) → divider → source sentence**, with Collins frequency stars and exam tags in the corner.

---

## How it works

```
Ctrl held AND mouse has moved → stationary for 400ms
  ↓  BitBlt grabs 900×90 physical px around the cursor, StretchBlt upscales 2x
  ↓  Windows.Media.Ocr returns per-word bounding rects
  ↓  pick the word whose rect contains the cursor (else nearest on the same line)
  ↓  SAPI speaks the English word
  ↓  local dict.db lookup (0.03ms, no network)
  ↓  popup renders → SAPI speaks the Chinese definition
```

Design notes:

- **No accidental triggers.** The trigger only arms if the mouse *moved after* Ctrl went down. So pressing `Ctrl+S` or `Ctrl+C` while the pointer happens to rest on text never fires — the main annoyance of dwell-only designs.
- **Click-through popup.** `WS_EX_TRANSPARENT | WS_EX_NOACTIVATE` means it swallows no clicks and steals no keyboard focus.
- **Rounded corners via DWM.** `DwmSetWindowAttribute` lets the Windows 11 compositor draw the corners and shadow on the GPU — no self-drawing, no Pillow, no bitmaps. Silently falls back to square corners on older Windows.
- **Speech interruption.** Each trigger bumps a generation counter; anything still speaking is flushed with `SVSFPurgeBeforeSpeak` instead of queueing up.
- **Lemmatisation.** `generates`, `ran`, `mice`, `studying` all resolve. Exact match first, then a 103k-entry lemma table, then suffix heuristics. When a definition is only a form note ("past tense of run"), the lemma's real definition is appended.
- **DPI aware.** Declares `PER_MONITOR_DPI_AWARE` at startup so cursor coordinates match screen pixels under scaling and on multi-monitor setups.

### Performance

| | |
|---|---|
| Popup render | 6.7ms median |
| Dictionary lookup | 0.03ms |
| CPU time over 12s idle | 0ms |
| Private memory | ~60 MB |

Every visual refinement is a static property — no animation, no timers, no per-frame redraw.

---

## Traditional Chinese quality

ECDICT ships Simplified Chinese definitions, converted at build time with OpenCC `s2twp` (Taiwan phrasing). **Computing terms come out near-perfect**: 软件→軟體, 内存→記憶體, 算法→演算法, 视频→影片.

But OpenCC cannot fix terms where Taiwan uses a *different word formation* rather than different characters — the classic case is 线粒体, which becomes 線粒體 when Taiwan actually says 粒線體.

Those are patched by **`用語修正.txt`**, a plain-text mapping applied at runtime — edit, save, restart, done; **no dictionary rebuild needed**. It currently carries 104 entries.

```
線粒體=粒線體
```

> **Rule for new entries: this is an unconditional string replacement.** Never add short or polysemous words — adding `類=類別` would turn 人類 into 人類別. The project deliberately excludes 函數, 數據 and 文件 for this reason.

PRs extending this table are welcome.

---

## Configuration

`config.json` is generated on first run. Edit, save, restart.

Key fields: `modifier`, `dwell_ms`, `capture_width`/`capture_height`, `ocr_scale`, `ocr_language`, `speak_english`/`speak_chinese`, `english_voice`/`chinese_voice`, `english_rate`/`chinese_rate`, `opacity`, `show_sentence`, `show_phonetic`, `show_stars`, `exam_tags`, `max_senses`, `esc_quit`, `hide_after_ms`, `debug`.

See the [Traditional Chinese README](README.md#設定) for the full table.

Two worth calling out:

- `english_voice` / `chinese_voice` are **substring matches** against the SAPI voices installed on *your* machine. Run `selftest.py` to see the actual list.
- `exam_tags` defaults to `["toefl","ielts","gre"]`. ECDICT also carries `zk`/`gk`/`ky`/`cet4`/`cet6` (mainland Chinese exams), hidden by default. Set `[]` to hide the row entirely.

---

## Self-test

```bash
python selftest.py
```

62 checks. It paints known English onto the screen and runs the real pipeline back over it — verifying screen capture, OCR, cursor word-picking, dictionary lookup, Traditional Chinese fixes, lemmatisation, **zero network access**, speech, the popup, Esc handling and the single-instance lock.

---

## Reference environment

**Values differ per machine — trust what `selftest.py` prints on yours.** On the development machine:

- The only Windows OCR languages installed were `ja` and `zh-Hant-TW` — **no English pack**. The zh-Hant-TW engine nonetheless recognises English perfectly (a full test sentence came back verbatim), so installing the English pack is unnecessary. Bonus: it reads Chinese and Japanese too.
- SAPI voices: `Microsoft Zira Desktop` (en-US), `Microsoft Hanhan Desktop` (zh-TW), `Microsoft Haruka Desktop` (ja-JP), all offline.
- Dictionary: 768,739 entries, 103,102 lemma mappings, `dict.db` 79 MB.

---

## Known limitations

- **No context disambiguation.** The dictionary lists every sense; it will not pick one for you the way an online translator does. `thread` gives you "線, 絲, 纖維", not "執行緒". That is the price of running offline.
- **OCR depends on rendering quality.** Dark backgrounds, very small text, serif faces and text over busy imagery all hurt. Raising `ocr_scale` usually helps.
- **English words only.** Digits and punctuation are filtered out. Hyphens and apostrophes stay part of the word.
- **Vocabulary cutoff.** ECDICT covers up to roughly 2020; very new jargon and most proper nouns are missing.
- **Exclusive-fullscreen games** cannot be captured — switch to windowed or borderless.
- **Windows only.** OCR, speech, screen capture and the rounded corners are all Windows-specific APIs.

---

## If you pass this on

When sharing the tool, please include a note like this — licence, limits and risk in one place, so the recipient can judge for themselves:

```
An open-source utility under the MIT licence. Source:
https://github.com/AFA7777/hover-translate

Dictionary data comes from ECDICT (MIT, copyright its original author).
This program bundles no dictionary data; the installer downloads it and
verifies its SHA-256.

The main program runs fully offline (verify with a firewall). It works by
reading the screen and running OCR on it, so do NOT use it on screens
showing passwords, personal data or confidential documents, and leave
debug mode off.

The project is new and has not had a third-party security audit — try it
yourself and evaluate before relying on it.
```

**Please do not describe this tool as "completely safe".** It reads screen content — that is the feature, not a flaw. The honest framing is to state verifiable facts (no network access at runtime, source is public, automated tests enforce both) and let people decide whether that fits their situation.

---

## License

MIT — see [LICENSE](LICENSE). Third-party components are listed in [NOTICE](NOTICE).

This program **bundles no dictionary data**. `build_dict.py` downloads it from the upstream repository and builds the database on the user's own machine.

- Dictionary data: [ECDICT](https://github.com/skywind3000/ECDICT) (MIT)
- Simplified→Traditional conversion: [OpenCC](https://github.com/BYVoid/OpenCC) (Apache 2.0), build-time only

**On the provenance of the dictionary data.** ECDICT is released under the MIT License by its author, and this project relies on that grant. ECDICT is however itself a compilation assembled over many years — per its own README, from community contributions, the open-source cdict dictionary, the English-Chinese portion of the open-source 屌丝字典, and proofreading against BNC/COCA frequency lists.

**Neither this project nor its author can verify the provenance of individual entries in that 768k-row corpus, and no such claim is made.** What is checkable: ECDICT is distributed by its author under MIT; this repository contains no dictionary data; `build_dict.py` fetches it from a pinned upstream commit and verifies its SHA-256 on the user's own machine. If you plan to deploy this where data provenance matters commercially or institutionally, evaluate the [upstream project](https://github.com/skywind3000/ECDICT) on its own terms rather than relying on this note. See [NOTICE](NOTICE).

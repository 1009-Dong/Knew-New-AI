# AI 每日觀察報 — 部署指南

## 你會有的檔案

```
ai_daily_newspaper.html     ← 你的報紙（每天自動更新）
update_news.py              ← 自動更新腳本（大腦）
requirements.txt            ← Python 套件清單
.github/workflows/
  daily_update.yml          ← GitHub 排程設定
```

---

## 步驟一：建立 GitHub Repository

1. 去 github.com，點右上角 **+** → **New repository**
2. Repository name 填：`ai-newspaper`（或任何名字）
3. 選 **Private**（因為會放 API Key）
4. 點 **Create repository**

---

## 步驟二：上傳四個檔案

在 GitHub repository 頁面，點 **Add file** → **Upload files**，上傳：
- `ai_daily_newspaper.html`
- `update_news.py`
- `requirements.txt`

然後手動建立資料夾結構，點 **Add file** → **Create new file**，
檔名填：`.github/workflows/daily_update.yml`
把 `daily_update.yml` 的內容貼進去，存檔。

---

## 步驟三：設定四個 Secrets

在 GitHub repository 頁面：
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

依序新增以下四個：

| Secret 名稱 | 值 |
|------------|---|
| `TAVILY_API_KEY` | 你的 Tavily API Key |
| `ANTHROPIC_API_KEY` | 你的 Anthropic API Key |
| `DROPBOX_ACCESS_TOKEN` | 見步驟四 |
| `DROPBOX_FILE_PATH` | `/AI報紙/ai_daily_newspaper.html` |

---

## 步驟四：取得 Dropbox Access Token

1. 去 **dropbox.com/developers/apps**
2. 點 **Create app**
3. 選 **Scoped access** → **Full Dropbox**
4. App name 填：`ai-newspaper`（或任何名字）
5. 點 **Create app**
6. 在 **Permissions** 頁面，勾選：
   - `files.content.write`
   - `files.content.read`
   - `sharing.write`
   - 點 **Submit**
7. 回到 **Settings** 頁面，往下找 **OAuth 2**
8. 在 **Generate access token** 點 **Generate**
9. 複製這串 token，貼到 GitHub Secrets 的 `DROPBOX_ACCESS_TOKEN`

> ⚠️ 注意：這個 token 是短期的（4 小時），正式使用要換成長期 token
> 見下方「長期 Token 設定」

---

## 步驟五：手動觸發測試

1. 在 GitHub repository 點上方 **Actions** 標籤
2. 左側點 **AI 每日觀察報 自動更新**
3. 右側點 **Run workflow** → **Run workflow**
4. 等待約 3–5 分鐘
5. 點進執行紀錄，確認每個步驟都是綠色 ✓
6. 去 Dropbox 確認 `/AI報紙/` 資料夾裡有 `ai_daily_newspaper.html`

---

## 步驟六：第一次把 HTML 傳到 Dropbox

因為第一次執行時 Dropbox 上還沒有 HTML 檔案，
腳本會嘗試讀 GitHub repository 裡的 `ai_daily_newspaper.html`。

所以你需要先把 HTML 檔案放到 Dropbox，有兩個方法：

**方法 A（最簡單）**：直接拖拉 HTML 檔案到 Dropbox 桌面應用程式的
`/AI報紙/` 資料夾（先手動建立這個資料夾）

**方法 B**：讓第一次 GitHub Actions 執行時，
腳本會讀本機（GitHub repo）的 HTML 檔案，然後自動上傳到 Dropbox

---

## 長期 Dropbox Token 設定

Dropbox 的短期 token 4 小時就過期，正式使用要這樣做：

1. 在 Dropbox App Console 找你的 App
2. **Settings** → **OAuth 2** → **Access token expiration** 改成 **No expiration**
3. 重新 Generate token
4. 把新 token 更新到 GitHub Secrets

---

## 每天的運作

```
每天台灣時間 07:00
    ↓
GitHub Actions 自動觸發
    ↓
搜尋 13 個切角（約 78 篇原始文章）
    ↓
Claude 萃取洞察，產出約 26–40 則新聞條目
    ↓
下載 Dropbox 上的現有 HTML
    ↓
注入今日新聞（保留過去 30 天）
    ↓
上傳回 Dropbox
    ↓
你打開 HTML 就看到今天的報紙 📰
```

---

## 每日成本估算

| 項目 | 費用 |
|------|------|
| Tavily API | 免費（每月 1000 次，每天用約 26 次） |
| Claude API | 約 $0.05–0.15 美元 / 天 |
| GitHub Actions | 免費（每月 2000 分鐘，每天用約 5 分鐘） |
| Dropbox | 免費（你已有） |
| **合計** | **約 $1.5–4.5 美元 / 月** |

---

## 常見問題

**Q：GitHub Actions 執行失敗怎麼辦？**
點進 Actions 的執行紀錄，展開失敗的步驟，看錯誤訊息。
最常見的原因是 API Key 填錯，或 Dropbox Token 過期。

**Q：想改成台灣時間幾點執行？**
修改 `daily_update.yml` 裡的 cron 表達式：
`0 23 * * *` = 台灣早上 7:00（UTC+8 = UTC -8小時）
`0 0 * * *`  = 台灣早上 8:00
`0 1 * * *`  = 台灣早上 9:00

**Q：想手動加一篇新聞怎麼辦？**
直接在 HTML 的 `NEWS` 陣列裡手動加一個物件，格式跟現有條目一樣。

**Q：想增加或修改搜尋切角？**
修改 `update_news.py` 裡的 `SECTIONS` 陣列，
每個切角可以改 `queries`（搜尋關鍵字），
改完 push 到 GitHub 就會在下次執行時生效。

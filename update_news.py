"""
update_news.py
AI 每日觀察報 — 自動更新腳本

執行流程：
  1. 對 13 個切角各發出搜尋請求（Tavily API）
  2. 把搜尋結果送給 Claude，產出結構化新聞條目（JSON）
  3. 讀取現有的 ai_daily_newspaper.html
  4. 把新條目注入 NEWS 陣列最前面，並更新 DAILY_SIGNAL
  5. 把更新後的 HTML 上傳到 Dropbox

需要的環境變數（在 GitHub Secrets 設定）：
  TAVILY_API_KEY
  ANTHROPIC_API_KEY
  DROPBOX_ACCESS_TOKEN
  DROPBOX_FILE_PATH   例如 /AI報紙/ai_daily_newspaper.html
"""

import os
import re
import json
import datetime
import requests

# ═══════════════════════════════════════════════════
#  設定
# ═══════════════════════════════════════════════════

TAVILY_API_KEY      = os.environ["TAVILY_API_KEY"]
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
DROPBOX_ACCESS_TOKEN = os.environ["DROPBOX_ACCESS_TOKEN"]
DROPBOX_FILE_PATH   = os.environ.get("DROPBOX_FILE_PATH", "/AI報紙/ai_daily_newspaper.html")

TODAY = datetime.date.today().isoformat()          # e.g. "2026-05-14"
DATE_PREFIX = TODAY.replace("-", "")               # e.g. "20260514"

# ═══════════════════════════════════════════════════
#  13 個切角的搜尋查詢設計
#  每個切角給 2 個 query，Tavily 各回 3 篇，共約 78 篇原始材料
#  Claude 會從中萃取出最有洞察價值的 2–4 則
# ═══════════════════════════════════════════════════

SECTIONS = [
    {
        "key": "tech",
        "label": "新科技前沿",
        "queries": [
            "AI robotics humanoid physical AI breakthrough 2026",
            "AI wearable device smart glasses new technology 2026"
        ]
    },
    {
        "key": "giants",
        "label": "矽谷巨頭發言",
        "queries": [
            "Jensen Huang Sam Altman Dario Amodei Sundar Pichai AI statement 2026",
            "OpenAI Google Microsoft Anthropic Meta AI announcement CEO 2026"
        ]
    },
    {
        "key": "clevel",
        "label": "C-level 賦能",
        "queries": [
            "CEO CAIO chief AI officer enterprise AI leadership 2026",
            "executive AI adoption productivity personal AI agent CEO 2026"
        ]
    },
    {
        "key": "strategy",
        "label": "AI 轉型策略",
        "queries": [
            "enterprise AI transformation strategy roadmap blueprint 2026",
            "AI operating model corporate AI strategy implementation 2026"
        ]
    },
    {
        "key": "factory",
        "label": "AI Factory",
        "queries": [
            "AI factory enterprise agent pipeline production deployment 2026",
            "LLMOps AgentOps MLOps enterprise AI operations scalable 2026"
        ]
    },
    {
        "key": "marketplace",
        "label": "Agent Marketplace",
        "queries": [
            "agent marketplace enterprise AI agent store Salesforce Microsoft 2026",
            "no-code agent builder citizen developer AI platform 2026"
        ]
    },
    {
        "key": "governance",
        "label": "AI Governance",
        "queries": [
            "AI governance EU AI Act ISO 42001 enterprise compliance 2026",
            "AI risk management responsible AI policy regulation 2026"
        ]
    },
    {
        "key": "arch",
        "label": "Architecture / Platform",
        "queries": [
            "AWS Azure Google Cloud AI platform architecture reference 2026",
            "cloud AI infrastructure hybrid deployment enterprise platform 2026"
        ]
    },
    {
        "key": "data",
        "label": "AI-Ready Data",
        "queries": [
            "AI ready data foundation enterprise data strategy for AI 2026",
            "machine learning deep learning model breakthrough dataset 2026"
        ]
    },
    {
        "key": "usecase",
        "label": "Use Case",
        "queries": [
            "AI agent enterprise use case ROI production deployment case study 2026",
            "agentic AI workflow automation business process manufacturing finance 2026"
        ]
    },
    {
        "key": "productivity",
        "label": "AI Productivity",
        "queries": [
            "AI productivity tool enterprise employee Copilot 2026",
            "generative AI workplace productivity measurement 2026"
        ]
    },
    {
        "key": "cooperation",
        "label": "Human-AI 協作",
        "queries": [
            "human AI collaboration cooperation workplace organizational change 2026",
            "AI impact workforce skills soft skills communication 2026"
        ]
    },
    {
        "key": "literacy",
        "label": "AI Literacy",
        "queries": [
            "AI literacy training enterprise employee upskilling 2026",
            "AI competency workforce education corporate AI learning 2026"
        ]
    },
]

# 地理標籤對照（Claude 用來判斷）
GEO_OPTIONS = ["usa", "eu", "apac", "cn", "tw", "jp", "all"]
IND_OPTIONS = ["mfg", "fin", "med", "ret", "eng", "tech", "gov", "edu", "log", "agr", "med2", "all"]

# ═══════════════════════════════════════════════════
#  STEP 1：用 Tavily 搜尋
# ═══════════════════════════════════════════════════

def tavily_search(query: str, max_results: int = 3) -> list[dict]:
    """
    呼叫 Tavily Search API，回傳文章列表
    每篇包含：title, url, content（摘要）, published_date
    """
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        print(f"  [Tavily 錯誤] {query[:40]}... → {e}")
        return []


def search_section(section: dict) -> list[dict]:
    """
    對一個切角的兩個 query 各搜尋一次，合併結果去重
    """
    all_results = []
    seen_urls = set()
    for q in section["queries"]:
        print(f"  搜尋：{q[:60]}")
        results = tavily_search(q, max_results=3)
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)
    return all_results


# ═══════════════════════════════════════════════════
#  STEP 2：用 Claude 收斂成結構化新聞條目
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一位專業的 AI 產業分析師，專門為企業高階主管撰寫每日 AI 趨勢觀察報。

你的任務：
1. 閱讀提供的搜尋結果
2. 從中挑選出今天最有洞察價值的 2–4 則新聞（去掉重複、去掉無實質內容的）
3. 對每則新聞產出結構化 JSON

洞察的標準：
- 不只是複述事實，而是說清楚「為什麼這件事重要、對企業意味著什麼」
- 優先選擇有具體數字、案例、或明確戰略意涵的新聞
- 避免選泛泛而談的評論文章

地理標籤選項（擇一）：usa / eu / apac / cn / tw / jp / all
產業標籤選項（擇一）：mfg / fin / med / ret / eng / tech / gov / edu / log / agr / med2 / all
可信度：A（一手資料/主要媒體）/ B（二手報導/行業媒體）/ C（部落格/分析文章）

輸出格式：只輸出一個 JSON 陣列，不要有任何其他文字、不要有 markdown 符號。

格式範例：
[
  {
    "title": "新聞標題（繁體中文，保留原文關鍵詞）",
    "insight": "洞察（繁體中文，2–3 句，說明為何重要、對企業的意義）",
    "geo": "usa",
    "ind": "tech",
    "src": "來源名稱",
    "url": "https://...",
    "cred": "A"
  }
]"""


def claude_distill(section: dict, raw_results: list[dict]) -> list[dict]:
    """
    把搜尋結果送給 Claude，產出結構化新聞條目
    """
    if not raw_results:
        print(f"  [跳過] {section['label']} 無搜尋結果")
        return []

    # 組合搜尋結果成文字
    articles_text = ""
    for i, r in enumerate(raw_results, 1):
        articles_text += f"""
--- 文章 {i} ---
標題：{r.get('title', '（無標題）')}
來源：{r.get('url', '')}
發布：{r.get('published_date', '不明')}
摘要：{r.get('content', '')[:600]}
"""

    user_msg = f"""今天是 {TODAY}。
切角：{section['label']}

以下是今天搜尋到的原始文章，請從中萃取出最有洞察價值的新聞條目：

{articles_text}

請輸出 JSON 陣列（只輸出 JSON，不要其他文字）："""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 2000,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["content"][0]["text"].strip()

        # 清理可能的 markdown 包裝
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        items = json.loads(raw_text)

        # 加上 date、id、section
        enriched = []
        for idx, item in enumerate(items):
            item["date"] = TODAY
            item["section"] = section["key"]
            item["id"] = f"{DATE_PREFIX}-{section['key']}-{idx+1:02d}"
            enriched.append(item)

        print(f"  ✓ {section['label']}：產出 {len(enriched)} 則")
        return enriched

    except json.JSONDecodeError as e:
        print(f"  [JSON 解析錯誤] {section['label']}：{e}")
        print(f"  原始回應：{raw_text[:200]}")
        return []
    except Exception as e:
        print(f"  [Claude 錯誤] {section['label']}：{e}")
        return []


# ═══════════════════════════════════════════════════
#  STEP 2b：產出今日頭條訊號
# ═══════════════════════════════════════════════════

def generate_daily_signal(all_items: list[dict]) -> str:
    """
    把今天所有新聞條目送給 Claude，產出一句跨切角的頭條摘要
    """
    if not all_items:
        return f"{TODAY} 今日資料收集中..."

    # 只給標題和洞察，節省 token
    summary_input = "\n".join([
        f"[{item['section']}] {item['title']}"
        for item in all_items[:30]  # 最多 30 則
    ])

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": f"""今天是 {TODAY}。以下是今天收集的 AI 新聞標題：

{summary_input}

請用 1–2 句繁體中文（約 60–80 字），總結今天最重要的 2–3 個跨切角訊號。
要具體，要有洞察，不要泛泛而談。直接輸出文字，不要任何格式符號。"""
                }],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  [頭條訊號錯誤] {e}")
        return f"{TODAY} 今日 AI 趨勢整理完畢"


# ═══════════════════════════════════════════════════
#  STEP 3：從 Dropbox 下載現有 HTML
# ═══════════════════════════════════════════════════

def download_html_from_dropbox() -> str:
    """
    從 Dropbox 下載現有的 HTML 檔案內容
    如果檔案不存在，回傳空字串（第一次執行時）
    """
    try:
        resp = requests.post(
            "https://content.dropboxapi.com/2/files/download",
            headers={
                "Authorization": f"Bearer {DROPBOX_ACCESS_TOKEN}",
                "Dropbox-API-Arg": json.dumps({"path": DROPBOX_FILE_PATH}),
            },
            timeout=30,
        )
        if resp.status_code == 409:
            # 檔案不存在
            print("  Dropbox 上尚無檔案，將使用本機 HTML")
            return ""
        resp.raise_for_status()
        print(f"  ✓ 從 Dropbox 下載成功（{len(resp.content)} bytes）")
        return resp.text
    except Exception as e:
        print(f"  [Dropbox 下載錯誤] {e}")
        return ""


# ═══════════════════════════════════════════════════
#  STEP 4：注入新資料到 HTML
# ═══════════════════════════════════════════════════

def inject_into_html(html: str, new_items: list[dict], signal: str) -> str:
    """
    把新的 NEWS 條目和 DAILY_SIGNAL 注入現有 HTML
    
    策略：
    - 找到 const NEWS = [ 這一行
    - 在它後面插入今天的新條目
    - 在 DAILY_SIGNAL 物件中插入今天的 key
    - 自動清理 30 天前的舊資料（避免檔案無限增大）
    """
    if not html:
        print("  [警告] HTML 為空，請確認 Dropbox 路徑或本機檔案")
        return html

    # ── 1. 插入新聞條目到 NEWS 陣列 ──
    # 把新條目轉成 JS 格式
    new_items_js_parts = []
    for item in new_items:
        # 跳脫單引號
        def esc(s):
            return str(s).replace("\\", "\\\\").replace("'", "\\'")

        js = f"""  {{id:"{esc(item['id'])}",date:"{esc(item['date'])}",section:"{esc(item['section'])}",
   title:"{esc(item['title'])}",
   insight:"{esc(item['insight'])}",
   geo:"{esc(item['geo'])}",ind:"{esc(item['ind'])}",
   src:"{esc(item['src'])}",url:"{esc(item['url'])}",cred:"{esc(item['cred'])}"}},"""
        new_items_js_parts.append(js)

    new_items_js = "\n".join(new_items_js_parts)

    # 找到 const NEWS=[ 或 const NEWS = [ 並在後面插入
    html = re.sub(
        r"(const NEWS\s*=\s*\[)",
        r"\1\n  // ── " + TODAY + r" ──────────────────────────────────────\n" + new_items_js + "\n",
        html,
        count=1,
    )

    # ── 2. 插入今日 DAILY_SIGNAL ──
    signal_escaped = signal.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    new_signal_entry = f'  "{TODAY}": "{signal_escaped}",\n'

    html = re.sub(
        r"(const DAILY_SIGNAL\s*=\s*\{)",
        r"\1\n" + new_signal_entry,
        html,
        count=1,
    )

    # ── 3. 清理 30 天前的舊條目（避免檔案無限增大）──
    cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    # 移除 NEWS 陣列中超過 30 天的條目
    # 找到有 date:"YYYY-MM-DD" 且日期 < cutoff 的整個物件
    def remove_old_items(match):
        date_str = match.group(1)
        if date_str < cutoff:
            return ""  # 移除
        return match.group(0)  # 保留

    # 這個 regex 匹配每個 {id:...,date:"...", ... }, 區塊
    html = re.sub(
        r'\{id:"[^"]*",date:"(\d{4}-\d{2}-\d{2})"[^}]*(?:\}[^,{]*,?)',
        remove_old_items,
        html,
    )

    # 移除 DAILY_SIGNAL 中超過 30 天的 key
    html = re.sub(
        r'"(\d{4}-\d{2}-\d{2})"\s*:\s*"[^"]*",?\s*\n',
        lambda m: "" if m.group(1) < cutoff else m.group(0),
        html,
    )

    print(f"  ✓ HTML 注入完成")
    return html


# ═══════════════════════════════════════════════════
#  STEP 5：上傳回 Dropbox
# ═══════════════════════════════════════════════════

def upload_html_to_dropbox(html_content: str):
    """
    把更新後的 HTML 上傳到 Dropbox（覆蓋舊版本）
    """
    try:
        resp = requests.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                "Authorization": f"Bearer {DROPBOX_ACCESS_TOKEN}",
                "Dropbox-API-Arg": json.dumps({
                    "path": DROPBOX_FILE_PATH,
                    "mode": "overwrite",
                    "autorename": False,
                    "mute": False,
                }),
                "Content-Type": "application/octet-stream",
            },
            data=html_content.encode("utf-8"),
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  ✓ 上傳成功：{result.get('path_display', DROPBOX_FILE_PATH)}")
        print(f"    檔案大小：{result.get('size', 0):,} bytes")
        return True
    except Exception as e:
        print(f"  [Dropbox 上傳錯誤] {e}")
        return False


# ═══════════════════════════════════════════════════
#  STEP 5b：取得 Dropbox 分享連結（可選）
# ═══════════════════════════════════════════════════

def get_dropbox_share_link() -> str:
    """
    取得或建立 Dropbox 公開分享連結
    """
    try:
        # 先嘗試取得現有連結
        resp = requests.post(
            "https://api.dropboxapi.com/2/sharing/list_shared_links",
            headers={
                "Authorization": f"Bearer {DROPBOX_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"path": DROPBOX_FILE_PATH},
            timeout=15,
        )
        resp.raise_for_status()
        links = resp.json().get("links", [])
        if links:
            raw = links[0].get("url", "")
            # 把 ?dl=0 換成 ?dl=1 讓瀏覽器直接開啟 HTML
            return raw.replace("?dl=0", "?dl=1").replace("www.dropbox.com", "dl.dropbox.com")

        # 沒有的話建立新連結
        resp2 = requests.post(
            "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
            headers={
                "Authorization": f"Bearer {DROPBOX_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "path": DROPBOX_FILE_PATH,
                "settings": {"requested_visibility": "public"},
            },
            timeout=15,
        )
        resp2.raise_for_status()
        raw = resp2.json().get("url", "")
        return raw.replace("?dl=0", "?dl=1").replace("www.dropbox.com", "dl.dropbox.com")
    except Exception as e:
        print(f"  [分享連結錯誤] {e}")
        return ""


# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════

def main():
    print(f"\n{'='*60}")
    print(f"  AI 每日觀察報 自動更新")
    print(f"  日期：{TODAY}")
    print(f"{'='*60}\n")

    # ── 1. 搜尋 + 收斂 ──
    all_new_items = []

    for section in SECTIONS:
        print(f"\n[{section['label']}]")

        # 搜尋
        raw_results = search_section(section)
        print(f"  取得 {len(raw_results)} 篇原始文章")

        # LLM 收斂
        items = claude_distill(section, raw_results)
        all_new_items.extend(items)

    print(f"\n共產出 {len(all_new_items)} 則新聞條目")

    if not all_new_items:
        print("沒有新條目，終止執行")
        return

    # ── 2. 產出今日頭條訊號 ──
    print("\n[產出今日頭條訊號]")
    signal = generate_daily_signal(all_new_items)
    print(f"  {signal}")

    # ── 3. 下載現有 HTML ──
    print("\n[從 Dropbox 下載現有 HTML]")
    html = download_html_from_dropbox()

    # 如果 Dropbox 沒有，嘗試讀本機檔案（第一次部署時使用）
    if not html:
        local_path = "ai_daily_newspaper.html"
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                html = f.read()
            print(f"  ✓ 從本機讀取：{local_path}")
        else:
            print(f"  [錯誤] 找不到本機 HTML 檔案，請先上傳初始版本到 Dropbox")
            return

    # ── 4. 注入新資料 ──
    print("\n[注入新資料到 HTML]")
    updated_html = inject_into_html(html, all_new_items, signal)

    # ── 5. 上傳到 Dropbox ──
    print("\n[上傳到 Dropbox]")
    success = upload_html_to_dropbox(updated_html)

    if success:
        # 取得分享連結
        link = get_dropbox_share_link()
        print(f"\n{'='*60}")
        print(f"  ✓ 完成！")
        print(f"  今日新聞：{len(all_new_items)} 則")
        if link:
            print(f"  開啟連結：{link}")
        print(f"{'='*60}\n")
    else:
        print("\n[!] 上傳失敗，請檢查 Dropbox Token")


if __name__ == "__main__":
    main()

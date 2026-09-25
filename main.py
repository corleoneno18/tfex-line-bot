import os
import re
import calendar
import requests
from datetime import datetime, timedelta

# รหัสเดือนของ TFEX
MONTH_MAP = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
    'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12
}

def get_last_trading_day(symbol):
    match = re.match(r'S50([A-Z])(\d{2})', symbol)
    if not match:
        return None
    
    month_code, year_code = match.groups()
    month = MONTH_MAP.get(month_code)
    if not month:
        return None
    
    year = 2000 + int(year_code)
    _, last_day = calendar.monthrange(year, month)
    dt = datetime(year, month, last_day)
    
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
        
    dt -= timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
        
    return dt

def calculate_remaining_days(symbol):
    last_trade_dt = get_last_trading_day(symbol)
    if not last_trade_dt:
        return "-"
    
    today = datetime.now().date()
    target_date = last_trade_dt.date()
    delta = (target_date - today).days
    if delta < 0:
        return "หมดอายุแล้ว"
    return f"{delta} วัน"

def get_active_s50_symbols():
    now = datetime.now()
    curr_yr = str(now.year)[2:]
    next_yr = str(now.year + 1)[2:]
    symbols = []
    for c in ['U', 'V', 'X', 'Z', 'H', 'M']:
        yr = curr_yr if c in ['U', 'V', 'X', 'Z'] else next_yr
        symbols.append(f"S50{c}{yr}")
    return list(dict.fromkeys(symbols))

def fetch_data_dom():
    from playwright.sync_api import sync_playwright

    set_data = {
        "นักลงทุนสถาบัน": "-",
        "บัญชีบริษัทหลักทรัพย์": "-",
        "นักลงทุนต่างชาติ": "-",
        "นักลงทุนภายในประเทศ": "-"
    }
    tfex_data = {
        "นักลงทุนสถาบัน": {},
        "นักลงทุนต่างชาติ": {},
        "บัญชีบริษัทหลักทรัพย์": {},
        "นักลงทุนภายในประเทศ": {}
    }
    results = []
    total_vol = 0
    total_oi = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1440, 'height': 900},
            locale="th-TH"
        )
        page = context.new_page()

        # 1. ดึงข้อมูลประเภทนักลงทุนหุ้น (SET Investor Type) จาก DOM
        print("กำลังอ่านข้อมูล SET Investor Type จากหน้าเว็บ...")
        try:
            page.goto("https://www.settrade.com/th/equities/market-data/investor-type", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # อ่านตาราง หรือ Cards ข้อมูลสถาบัน / ต่างชาติ
            rows = page.query_selector_all("tr, .investor-type-card, div[class*='InvestorType']")
            for row in rows:
                text = row.inner_text()
                if "สถาบัน" in text or "ต่างชาติ" in text or "บริษัทหลักทรัพย์" in text or "ในประเทศ" in text:
                    # ค้นหาตัวเลขในแถว
                    nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?', text)
                    if nums:
                        net_val = nums[-1] # ค่า Net มูลค่าสุทธิมักจะอยู่ท้ายสุด
                        if "สถาบัน" in text: set_data["นักลงทุนสถาบัน"] = net_val
                        elif "บริษัทหลักทรัพย์" in text or "บล." in text: set_data["บัญชีบริษัทหลักทรัพย์"] = net_val
                        elif "ต่างชาติ" in text or "ต่างประเทศ" in text: set_data["นักลงทุนต่างชาติ"] = net_val
                        elif "ในประเทศ" in text or "ทั่วไป" in text: set_data["นักลงทุนภายในประเทศ"] = net_val
        except Exception as e:
            print(f"Error SET Investor DOM: {e}")

        # 2. ดึงข้อมูลประเภทนักลงทุน TFEX จาก DOM
        print("กำลังอ่านข้อมูล TFEX Investor Type จากหน้าเว็บ...")
        try:
            page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # แกะตาราง TFEX
            tables = page.query_selector_all("table")
            for tbl in tables:
                rows = tbl.query_selector_all("tr")
                for r in rows:
                    cells = [c.inner_text().strip() for c in r.query_selector_all("td, th")]
                    if len(cells) >= 4:
                        cat_name = cells[0]
                        inst_val = cells[1]
                        foreign_val = cells[2]
                        retail_val = cells[3]

                        if any(k in cat_name for k in ["Futures", "Options", "Equity"]):
                            tfex_data["นักลงทุนสถาบัน"][cat_name] = inst_val
                            tfex_data["นักลงทุนต่างชาติ"][cat_name] = foreign_val
                            tfex_data["นักลงทุนภายในประเทศ"][cat_name] = retail_val
        except Exception as e:
            print(f"Error TFEX Investor DOM: {e}")

        # 3. ดึงข้อมูลราคา SET50 รายสัญญาโดยเปิดหน้า Overview ของแต่ละสัญญา
        symbols = get_active_s50_symbols()
        print(f"กำลังดึงข้อมูลสัญญา SET50: {symbols}")

        for sym in symbols:
            try:
                url = f"https://www.settrade.com/th/derivatives/quote/{sym}/overview"
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2500) # รอให้ JS แสดงตัวเลขบนหน้าจอ

                body_text = page.inner_text("body")
                
                # สกัดข้อมูลจากข้อความบนหน้าจอด้วย Regex
                def extract_val(pattern, default="-"):
                    m = re.search(pattern, body_text)
                    return m.group(1).strip() if m else default

                last = extract_val(r'(?:ราคาล่าสุด|Last)\s*\n?\s*([\d,]+\.\d{2})')
                if last == "-":
                    last = extract_val(r'([\d,]+\.\d{2})\s*(?:\+|-\d)')

                open_p = extract_val(r'(?:ราคาเปิด|Open)\s*\n?\s*([\d,]+\.\d{2})')
                high = extract_val(r'(?:ราคาสูงสุด|High)\s*\n?\s*([\d,]+\.\d{2})')
                low = extract_val(r'(?:ราคาต่ำสุด|Low)\s*\n?\s*([\d,]+\.\d{2})')
                avg = extract_val(r'(?:ราคาเฉลี่ย|Average|Avg)\s*\n?\s*([\d,]+\.\d{2})')
                vol = extract_val(r'(?:ปริมาณการซื้อขาย|Volume|ปริมาณ \(สัญญา\))\s*\n?\s*([\d,]+)')
                oi = extract_val(r'(?:สถานะคงค้าง|Open Interest|OI)\s*\n?\s*([\d,]+)')

                # คำนวณวันคงเหลือ
                rem = calculate_remaining_days(sym)

                vol_clean = int(vol.replace(",", "")) if vol != "-" and vol.replace(",", "").isdigit() else 0
                oi_clean = int(oi.replace(",", "")) if oi != "-" and oi.replace(",", "").isdigit() else 0

                if oi_clean > 0 or vol_clean > 0 or last != "-":
                    results.append({
                        "symbol": sym, "remaining_days": rem,
                        "last": last, "change_pct": "",
                        "high": high, "low": low, "avg": avg, "open": open_p,
                        "vol": f"{vol_clean:,}", "oi": f"{oi_clean:,}",
                        "vol_num": vol_clean, "oi_num": oi_clean
                    })
                    total_vol += vol_clean
                    total_oi += oi_clean
                    print(f"  + {sym}: Last={last}, Vol={vol_clean}, OI={oi_clean}")
            except Exception as e:
                print(f"  - ข้าม {sym}: {e}")

        browser.close()

    return results, total_vol, total_oi, set_data, tfex_data

def format_investor_summary(set_data, tfex_data):
    groups = [
        ("🌐 **นักลงทุนต่างชาติ**", "นักลงทุนต่างชาติ"),
        ("🏦 **นักลงทุนสถาบัน**", "นักลงทุนสถาบัน"),
        ("💼 **บัญชีบริษัทหลักทรัพย์**", "บัญชีบริษัทหลักทรัพย์"),
        ("👤 **นักลงทุนภายในประเทศ**", "นักลงทุนภายในประเทศ")
    ]
    output = []
    for title, group_key in groups:
        lines = [title]
        set_net = set_data.get(group_key, "-")
        lines.append(f"• Equity Index: {set_net}")
        tfex_group = tfex_data.get(group_key, {})
        for cat in ["Equity Index Futures", "Single Stock Futures", "Currency Futures", "Equity Index Call Options", "Equity Index Put Options"]:
            val = tfex_group.get(cat, "-")
            lines.append(f"• {cat}: {val}")
        output.append("\n".join(lines))
    return "\n\n".join(output)

def format_line_message(results, total_vol, total_oi, set_data, tfex_data):
    investor_summary = format_investor_summary(set_data, tfex_data)
    results_sorted = sorted(results, key=lambda x: x["oi_num"], reverse=True)
    lines = []
    for item in results_sorted:
        lines.append(
            f"📌 **[{item['symbol']}]**\n"
            f"• วันคงเหลือ: {item['remaining_days']}\n"
            f"• ราคาล่าสุด: {item['last']}\n"
            f"• ราคาเปิด: {item['open']}\n"
            f"• ราคาสูงสุด: {item['high']}\n"
            f"• ราคาต่ำสุด: {item['low']}\n"
            f"• ราคาเฉลี่ย: {item['avg']}\n"
            f"• ปริมาณ (สัญญา): {item['vol']}\n"
            f"• สถานะคงค้าง (OI): {item['oi']}"
        )
    
    s50_summary = "\n\n".join(lines) if lines else "ไม่พบข้อมูลสัญญาล่าสุด"
    s50_summary += f"\n\n📊 **สรุปรวม SET50 Futures ทั้งหมด**\n• ปริมาณการซื้อขายรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม (OI): {total_oi:,} สัญญา"
    
    return f"👥 **สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน**\n\n{investor_summary}\n\n====================\n\n📈 **สรุป SET50 Futures วันนี้ (เรียงตาม OI สูงสุด):**\n\n{s50_summary}"

def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    res = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT --- Code: {res.status_code}")

if __name__ == "__main__":
    results, total_vol, total_oi, set_data, tfex_data = fetch_data_dom()
    msg = format_line_message(results, total_vol, total_oi, set_data, tfex_data)
    send_line_message(msg)
    print("ทำงานเสร็จสิ้น!")

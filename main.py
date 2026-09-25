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

def fetch_data_via_browser():
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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        # 1. ดึงประเภทนักลงทุน SET จากหน้าเว็บโดยตรง
        try:
            print("กำลังดึงข้อมูล SET Investor Type...")
            page.goto("https://www.settrade.com/th/equities/market-data/investor-type", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            
            rows = page.locator("table tbody tr").all()
            for row in rows:
                text = row.inner_text()
                parts = [p.strip() for p in text.split('\t') if p.strip()]
                if len(parts) >= 2:
                    name = parts[0]
                    net = parts[-1] # ค่าสุทธิมักจะอยู่คอลัมน์สุดท้าย
                    if "สถาบัน" in name:
                        set_data["นักลงทุนสถาบัน"] = net
                    elif "บริษัทหลักทรัพย์" in name or "บัญชี บล." in name:
                        set_data["บัญชีบริษัทหลักทรัพย์"] = net
                    elif "ต่างประเทศ" in name or "ต่างชาติ" in name:
                        set_data["นักลงทุนต่างชาติ"] = net
                    elif "ในประเทศ" in name or "ทั่วไป" in name:
                        set_data["นักลงทุนภายในประเทศ"] = net
            print(f"✅ SET Investor: {set_data}")
        except Exception as e:
            print(f"❌ Error SET Investor: {e}")

        # 2. ดึงประเภทนักลงทุน TFEX จากหน้าเว็บ
        try:
            print("กำลังดึงข้อมูล TFEX Investor Type...")
            page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            
            rows = page.locator("table tbody tr").all()
            cats = ["Equity Index Futures", "Single Stock Futures", "Currency Futures", "Equity Index Call Options", "Equity Index Put Options"]
            
            for row in rows:
                text = row.inner_text()
                for cat in cats:
                    if cat in text:
                        cols = [c.strip() for c in text.split('\n') if c.strip()]
                        # หากแยกด้วย newline ไม่ได้ ให้ลอง split ด้วย tab
                        if len(cols) < 4:
                            cols = [c.strip() for c in text.split('\t') if c.strip()]
                        
                        # ค่าจะเรียง: สถาบัน, ต่างชาติ, ในประเทศ
                        nums = [c for c in cols if re.match(r'^[\+\-0-9\,\.]+$', c)]
                        if len(nums) >= 3:
                            tfex_data["นักลงทุนสถาบัน"][cat] = nums[0]
                            tfex_data["นักลงทุนต่างชาติ"][cat] = nums[1]
                            tfex_data["นักลงทุนภายในประเทศ"][cat] = nums[2]
            print("✅ TFEX Investor Data Fetched")
        except Exception as e:
            print(f"❌ Error TFEX Investor: {e}")

        # 3. ดึงสัญญา SET50 Futures รายตัว
        symbols = get_active_s50_symbols()
        print(f"กำลังดึงสัญญา SET50: {symbols}")
        for sym in symbols:
            try:
                page.goto(f"https://www.settrade.com/th/derivatives/quote/{sym}/overview", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(2000)
                body_text = page.locator("body").inner_text()

                def get_value(pattern, default="-"):
                    m = re.search(pattern, body_text)
                    return m.group(1).strip() if m else default

                last = get_value(r'ล่าสุด\s*([0-9\,\.]+)')
                if last == "-":
                    last = get_value(r'([0-9\,\.]+)\s*[\+\-]\d+')

                change_pct = get_value(r'([\+\-][0-9\,\.]+\s*\([\+\-][0-9\,\.]%\))')
                high = get_value(r'ราคาสูงสุด\s*([0-9\,\.]+)')
                low = get_value(r'ราคาต่ำสุด\s*([0-9\,\.]+)')
                avg = get_value(r'ราคาเฉลี่ย\s*([0-9\,\.]+)')
                open_p = get_value(r'ราคาเปิด\s*([0-9\,\.]+)')
                vol = get_value(r'ปริมาณ\s*\(สัญญา\)\s*([0-9\,]+)')
                oi = get_value(r'สถานะคงค้าง\s*\(สัญญา\)\s*([0-9\,]+)')

                v_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
                o_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0
                rem = calculate_remaining_days(sym)

                if last != "-" or o_num > 0 or v_num > 0:
                    results.append({
                        "symbol": sym, "remaining_days": rem, "last": last, "change_pct": change_pct,
                        "high": high, "low": low, "avg": avg, "open": open_p, "vol": vol, "oi": oi,
                        "vol_num": v_num, "oi_num": o_num
                    })
                    total_vol += v_num
                    total_oi += o_num
                    print(f"  + {sym}: Last={last}, OI={oi}")
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
            f"• ราคาล่าสุด: {item['last']} {item['change_pct']}\n"
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
    results, total_vol, total_oi, set_data, tfex_data = fetch_data_via_browser()
    msg = format_line_message(results, total_vol, total_oi, set_data, tfex_data)
    send_line_message(msg)
    print("ทำงานเสร็จสิ้น!")

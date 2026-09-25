import os
import re
import time
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

def fetch_set_investor_api():
    """ดึงข้อมูลประเภทนักลงทุน SET จาก API ตรง"""
    set_data = {
        "นักลงทุนสถาบัน": "-",
        "บัญชีบริษัทหลักทรัพย์": "-",
        "นักลงทุนต่างชาติ": "-",
        "นักลงทุนภายในประเทศ": "-"
    }
    url = "https://api.settrade.com/api/set/market/investor-type"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.settrade.com/"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            items = data.get("investorTypes", []) or data.get("data", [])
            for item in items:
                name = item.get("investorTypeName", "") or item.get("name", "")
                net_val = item.get("netValue", item.get("net", "-"))
                if isinstance(net_val, (int, float)):
                    net_val = f"{net_val:,.2f}"
                
                if "สถาบัน" in name:
                    set_data["นักลงทุนสถาบัน"] = net_val
                elif "บริษัทหลักทรัพย์" in name or "บัญชี บล." in name:
                    set_data["บัญชีบริษัทหลักทรัพย์"] = net_val
                elif "ต่างประเทศ" in name or "ต่างชาติ" in name:
                    set_data["นักลงทุนต่างชาติ"] = net_val
                elif "ในประเทศ" in name or "ทั่วไป" in name:
                    set_data["นักลงทุนภายในประเทศ"] = net_val
    except Exception as e:
        print(f"SET API Error: {e}")
        
    return set_data

def get_active_s50_symbols():
    """สร้างรายชื่อสัญญา SET50 ของปีปัจจุบันและปีถัดไปโดยอัตโนมัติ (เป็นแผนสำรองชัวร์ๆ)"""
    now = datetime.now()
    curr_yr = str(now.year)[2:]
    next_yr = str(now.year + 1)[2:]
    
    # สัญญาหลัก H, M, U, Z และสัญญารายเดือน
    codes = ['H', 'M', 'U', 'Z', 'V', 'X', 'Z']
    symbols = []
    for c in ['U', 'V', 'X', 'Z', 'H', 'M']:
        yr = curr_yr if c in ['U', 'V', 'X', 'Z'] else next_yr
        symbols.append(f"S50{c}{yr}")
    
    # กำจัดค่าซ้ำ
    return list(dict.fromkeys(symbols))

def fetch_all_data_robust():
    from playwright.sync_api import sync_playwright
    
    set_data = fetch_set_investor_api()
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        # 1. พยายามดึงสัญลักษณ์จากหน้าเว็บ หากไม่ได้ให้ใช้ชุดสำรอง
        symbols = []
        try:
            page.goto("https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            body = page.locator("body").inner_text()
            symbols = list(dict.fromkeys(re.findall(r'S50[A-Z0-9]{3}', body)))
        except Exception:
            pass
        
        if not symbols:
            symbols = get_active_s50_symbols()
            print(f"ใช้สัญลักษณ์สำรอง: {symbols}")

        # 2. ดึงข้อมูลแต่ละสัญญา
        for sym in symbols:
            try:
                page.goto(f"https://www.settrade.com/th/derivatives/quote/{sym}/overview", wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)
                text = page.locator("body").inner_text()
                
                def extract_val(pattern, default="-"):
                    m = re.search(pattern, text)
                    return m.group(1).strip() if m else default

                last = extract_val(r'([0-9\,\.]+)\s*[\+\-]\d+')
                change_pct = extract_val(r'([\+\-][0-9\,\.]+\s*\([\+\-][0-9\,\.]%\))')
                high = extract_val(r'ราคาสูงสุด\s*([0-9\,\.]+)')
                low = extract_val(r'ราคาต่ำสุด\s*([0-9\,\.]+)')
                avg = extract_val(r'ราคาเฉลี่ย\s*([0-9\,\.]+)')
                open_p = extract_val(r'ราคาเปิด\s*([0-9\,\.]+)')
                vol = extract_val(r'ปริมาณ\s*\(สัญญา\)\s*([0-9\,]+)')
                oi = extract_val(r'สถานะคงค้าง\s*\(สัญญา\)\s*([0-9\,]+)')
                
                rem = calculate_remaining_days(sym)
                v_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
                o_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0

                # เก็บเฉพาะสัญญาที่มีการซื้อขายหรือมี OI
                if last != "-" or o_num > 0 or v_num > 0:
                    results.append({
                        "symbol": sym, "remaining_days": rem, "last": last, "change_pct": change_pct,
                        "high": high, "low": low, "avg": avg, "open": open_p, "vol": vol, "oi": oi,
                        "vol_num": v_num, "oi_num": o_num
                    })
                    total_vol += v_num
                    total_oi += o_num
            except Exception as e:
                print(f"ข้าม {sym}: {e}")

        # 3. ดึง TFEX
        try:
            page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            cats = ["Equity Index Futures", "Single Stock Futures", "Currency Futures", "Equity Index Call Options", "Equity Index Put Options"]
            
            page_text = page.locator("body").inner_text()
            lines = page_text.split('\n')
            for line in lines:
                for cat in cats:
                    if cat in line:
                        parts = [p.strip() for p in line.split() if p.strip()]
                        nums = [p for p in parts if re.match(r'^[\+\-0-9\,\.]+$', p)]
                        if len(nums) >= 3:
                            tfex_data["นักลงทุนสถาบัน"][cat] = nums[0]
                            tfex_data["นักลงทุนต่างชาติ"][cat] = nums[1]
                            tfex_data["นักลงทุนภายในประเทศ"][cat] = nums[2]
        except Exception as e:
            print(f"ดึง TFEX ผิดพลาด: {e}")

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
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    results, total_vol, total_oi, set_data, tfex_data = fetch_all_data_robust()
    msg = format_line_message(results, total_vol, total_oi, set_data, tfex_data)
    send_line_message(msg)

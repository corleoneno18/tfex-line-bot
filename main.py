import os
import re
import time
import calendar
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# รหัสเดือนของ TFEX
MONTH_MAP = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
    'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12
}

def get_last_trading_day(symbol):
    """คำนวณวันทำการก่อนวันสุดท้ายของเดือน จากชื่อสัญญา"""
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
    
    while dt.weekday() >= 5: # 5 = เสาร์, 6 = อาทิตย์
        dt -= timedelta(days=1)
        
    dt -= timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
        
    return dt

def calculate_remaining_days(symbol):
    """คำนวณจำนวนวันคงเหลือ"""
    last_trade_dt = get_last_trading_day(symbol)
    if not last_trade_dt:
        return "-"
    
    today = datetime.now().date()
    target_date = last_trade_dt.date()
    
    delta = (target_date - today).days
    if delta < 0:
        return "หมดอายุแล้ว"
    return f"{delta} วัน"

def get_all_s50_symbols(page):
    """1. ดึงรายชื่อสัญญา SET50 ทั้งหมด"""
    list_url = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    print("กำลังดึงรายชื่อสัญญา SET50 ทั้งหมด...")
    page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("table", timeout=30000)
    time.sleep(3)
    
    text_content = page.locator("body").inner_text()
    symbols = list(dict.fromkeys(re.findall(r'S50[A-Z0-9]+', text_content)))
    print(f"พบสัญญา SET50 ทั้งหมด {len(symbols)} รายการ: {symbols}")
    return symbols

def get_symbol_overview_data(page, symbol):
    """2. ดึงข้อมูลราคาและ OI ของแต่ละสัญญา"""
    quote_url = f"https://www.settrade.com/th/derivatives/quote/{symbol}/overview"
    print(f"กำลังดึงข้อมูลหน้า Overview ของ {symbol}...")
    
    try:
        page.goto(quote_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        
        body_text = page.locator("body").inner_text()
        
        def extract_val(pattern, text, default="-"):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else default

        last = extract_val(r'([0-9\,\.]+)\s*[\+\-]\d+', body_text)
        change_pct = extract_val(r'([\+\-][0-9\,\.]+\s*\([\+\-][0-9\,\.]%\))', body_text)
        high = extract_val(r'ราคาสูงสุด\s*([0-9\,\.]+)', body_text)
        low = extract_val(r'ราคาต่ำสุด\s*([0-9\,\.]+)', body_text)
        avg = extract_val(r'ราคาเฉลี่ย\s*([0-9\,\.]+)', body_text)
        open_p = extract_val(r'ราคาเปิด\s*([0-9\,\.]+)', body_text)
        vol = extract_val(r'ปริมาณ\s*\(สัญญา\)\s*([0-9\,]+)', body_text)
        oi = extract_val(r'สถานะคงค้าง\s*\(สัญญา\)\s*([0-9\,]+)', body_text)
        
        remaining_days_str = calculate_remaining_days(symbol)

        vol_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
        oi_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0

        return {
            "symbol": symbol,
            "remaining_days": remaining_days_str,
            "last": last,
            "change_pct": change_pct,
            "high": high,
            "low": low,
            "avg": avg,
            "open": open_p,
            "vol": vol,
            "oi": oi,
            "vol_num": vol_num,
            "oi_num": oi_num
        }
    except Exception as e:
        print(f"ไม่สามารถดึงข้อมูลของ {symbol} ได้: {e}")
        return None

def fetch_investor_type_data(page):
    """3. ดึงข้อมูลประเภทนักลงทุนทั้งจาก SET และ TFEX"""
    print("กำลังดึงข้อมูลประเภทนักลงทุน SET & TFEX...")
    
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

    # 3.1 ดึงข้อมูล SET (Equity Index) จากตารางรายวัน
    try:
        set_url = "https://www.settrade.com/th/equities/market-data/historical-report/investor-type"
        page.goto(set_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("table", timeout=30000)
        time.sleep(3)
        
        rows = page.locator("table tbody tr").all()
        for row in rows:
            # ดึงเฉพาะ td ในแต่ละ tr เพื่อเลี่ยงการแยก string ผิดพลาด
            cols = [td.inner_text().strip() for td in row.locator("td").all()]
            if len(cols) >= 6:
                inv_type = cols[0]
                net_val = cols[5]  # ช่อง 'สุทธิ' อยู่ที่ col index 5 (6th element)
                
                if "ต่างประเทศ" in inv_type or "ต่างชาติ" in inv_type:
                    set_data["นักลงทุนต่างชาติ"] = net_val
                elif "สถาบัน" in inv_type:
                    set_data["นักลงทุนสถาบัน"] = net_val
                elif "บริษัทหลักทรัพย์" in inv_type or "บัญชี บล." in inv_type:
                    set_data["บัญชีบริษัทหลักทรัพย์"] = net_val
                elif "ทั่วไป" in inv_type or "ในประเทศ" in inv_type:
                    set_data["นักลงทุนภายในประเทศ"] = net_val
    except Exception as e:
        print(f"ข้อผิดพลาดขณะดึงข้อมูล SET: {e}")

    # 3.2 ดึงข้อมูล TFEX Derivatives
    try:
        tfex_url = "https://www.settrade.com/th/derivatives/market-data/investor-type"
        page.goto(tfex_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("table", timeout=30000)
        time.sleep(3)
        
        categories = [
            "Equity Index Futures", 
            "Single Stock Futures", 
            "Currency Futures", 
            "Equity Index Call Options", 
            "Equity Index Put Options"
        ]

        rows = page.locator("table tbody tr").all()
        for row in rows:
            row_text = row.inner_text().strip()
            for cat in categories:
                if cat in row_text:
                    parts = [p.strip() for p in re.split(r'[\n\t]+', row_text) if p.strip()]
                    nums = parts[1:] # ตัดชื่อสินค้าออก
                    
                    if len(nums) >= 9:
                        tfex_data["นักลงทุนสถาบัน"][cat] = nums[2]
                        tfex_data["นักลงทุนต่างชาติ"][cat] = nums[5]
                        tfex_data["นักลงทุนภายในประเทศ"][cat] = nums[8]
                    break
    except Exception as e:
        print(f"ข้อผิดพลาดขณะดึงข้อมูล TFEX: {e}")

    return set_data, tfex_data

def format_investor_summary(set_data, tfex_data):
    """4. จัดฟอร์แมตสรุปประเภทนักลงทุนพร้อม Emoji"""
    groups = [
        ("🌐 **นักลงทุนต่างชาติ**", "นักลงทุนต่างชาติ"),
        ("🏦 **นักลงทุนสถาบัน**", "นักลงทุนสถาบัน"),
        ("💼 **บัญชีบริษัทหลักทรัพย์**", "บัญชีบริษัทหลักทรัพย์"),
        ("👤 **นักลงทุนภายในประเทศ**", "นักลงทุนภายในประเทศ")
    ]
    
    output = []
    
    for title, group_key in groups:
        lines = [title]
        
        # ยอด SET (Equity Index)
        set_net = set_data.get(group_key, "-")
        lines.append(f"• Equity Index: {set_net}")
        
        # ยอด TFEX รายสินค้า
        tfex_group = tfex_data.get(group_key, {})
        for cat in ["Equity Index Futures", "Single Stock Futures", "Currency Futures", "Equity Index Call Options", "Equity Index Put Options"]:
            val = tfex_group.get(cat, "-")
            lines.append(f"• {cat}: {val}")
            
        output.append("\n".join(lines))
        
    return "\n\n".join(output)

def fetch_all_data():
    """5. ดึงข้อมูลทั้งหมด"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # ดึงสัญญา SET50
        symbols = get_all_s50_symbols(page)
        results = []
        total_vol = 0
        total_oi = 0
        
        if symbols:
            for sym in symbols:
                data = get_symbol_overview_data(page, sym)
                if data:
                    results.append(data)
                    total_vol += data["vol_num"]
                    total_oi += data["oi_num"]
                    
        # ดึงสรุปประเภทนักลงทุน
        set_data, tfex_data = fetch_investor_type_data(page)
        
        browser.close()
        return results, total_vol, total_oi, set_data, tfex_data

def format_line_message(results, total_vol, total_oi, set_data, tfex_data):
    """6. รวมข้อความทั้งหมดเข้าด้วยกัน"""
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
        
    s50_summary = "\n\n".join(lines)
    s50_summary += f"\n\n📊 **สรุปรวม SET50 Futures ทั้งหมด**\n• ปริมาณการซื้อขายรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม (OI): {total_oi:,} สัญญา"
    
    final_message = f"👥 **สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน**\n\n{investor_summary}\n\n====================\n\n📈 **สรุป SET50 Futures วันนี้ (เรียงตาม OI สูงสุด):**\n\n{s50_summary}"
    return final_message

def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT ---")
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    print(f"----------------------")

if __name__ == "__main__":
    try:
        results, total_vol, total_oi, set_data, tfex_data = fetch_all_data()
        message = format_line_message(results, total_vol, total_oi, set_data, tfex_data)
        send_line_message(message)
        print("ส่งข้อมูลเข้า LINE สำเร็จเรียบร้อย!")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")

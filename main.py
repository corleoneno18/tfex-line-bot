import os
import re
import calendar
import json
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

def fetch_all_data_via_playwright():
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # เข้าหน้าเว็บแรกเพื่อรับ Cookies & Session Bypass
        try:
            page.goto("https://www.settrade.com/th/home", wait_until="networkidle", timeout=25000)
        except Exception:
            pass

        # 1. ดึง SET Investor Type ผ่าน Browser Context Request
        try:
            res = page.request.get("https://api.settrade.com/api/set/market/investor-type")
            if res.ok:
                data = res.json()
                items = data if isinstance(data, list) else data.get("data", data.get("investorTypes", []))
                for item in items:
                    name = str(item.get("investorTypeName", item.get("name", "")))
                    net_val = item.get("netValue", item.get("net", "-"))
                    if isinstance(net_val, (int, float)):
                        net_val = f"{net_val:,.2f}"

                    if "สถาบัน" in name:
                        set_data["นักลงทุนสถาบัน"] = net_val
                    elif "บริษัทหลักทรัพย์" in name or "บัญชี บล." in name or "Prop" in name:
                        set_data["บัญชีบริษัทหลักทรัพย์"] = net_val
                    elif "ต่างประเทศ" in name or "ต่างชาติ" in name or "Foreign" in name:
                        set_data["นักลงทุนต่างชาติ"] = net_val
                    elif "ในประเทศ" in name or "ทั่วไป" in name or "Retail" in name:
                        set_data["นักลงทุนภายในประเทศ"] = net_val
            print(f"✅ SET Investor Data: {set_data}")
        except Exception as e:
            print(f"❌ SET Investor Error: {e}")

        # 2. ดึง TFEX Investor Type ผ่าน Browser Context Request
        try:
            res = page.request.get("https://api.settrade.com/api/tfex/market/investor-type")
            if res.ok:
                data = res.json()
                items = data if isinstance(data, list) else data.get("data", data.get("investorTypes", []))
                for item in items:
                    cat = item.get("categoryName", item.get("productGroup", item.get("product", "")))
                    inst = item.get("institutionNet", item.get("instNet", "-"))
                    foreign = item.get("foreignNet", item.get("foreignNetValue", "-"))
                    retail = item.get("retailNet", item.get("localNet", "-"))

                    tfex_data["นักลงทุนสถาบัน"][cat] = f"{inst:,}" if isinstance(inst, (int, float)) else str(inst)
                    tfex_data["นักลงทุนต่างชาติ"][cat] = f"{foreign:,}" if isinstance(foreign, (int, float)) else str(foreign)
                    tfex_data["นักลงทุนภายในประเทศ"][cat] = f"{retail:,}" if isinstance(retail, (int, float)) else str(retail)
            print("✅ TFEX Investor Data Fetched")
        except Exception as e:
            print(f"❌ TFEX Investor Error: {e}")

        # 3. ดึงสัญญา SET50 Futures
        symbols = get_active_s50_symbols()
        for sym in symbols:
            try:
                res = page.request.get(f"https://api.settrade.com/api/tfex/quote/{sym}/overview")
                if res.ok:
                    d = res.json()
                    last = d.get("last", d.get("lastPrice", "-"))
                    change = d.get("change", 0)
                    change_pct = d.get("percentChange", d.get("changePercent", 0))
                    high = d.get("high", d.get("highPrice", "-"))
                    low = d.get("low", d.get("lowPrice", "-"))
                    avg = d.get("averagePrice", d.get("avg", "-"))
                    open_p = d.get("open", d.get("openPrice", "-"))
                    vol = d.get("totalVolume", d.get("volume", 0))
                    oi = d.get("openInterest", d.get("oi", 0))

                    v_num = int(vol) if isinstance(vol, (int, float)) else 0
                    o_num = int(oi) if isinstance(oi, (int, float)) else 0
                    change_str = f"{change:+.2f} ({change_pct:+.2f}%)" if isinstance(change, (int, float)) else "-"
                    rem = calculate_remaining_days(sym)

                    if o_num > 0 or v_num > 0 or last != "-":
                        results.append({
                            "symbol": sym, "remaining_days": rem,
                            "last": f"{last:,.2f}" if isinstance(last, (int, float)) else str(last),
                            "change_pct": change_str,
                            "high": f"{high:,.2f}" if isinstance(high, (int, float)) else str(high),
                            "low": f"{low:,.2f}" if isinstance(low, (int, float)) else str(low),
                            "avg": f"{avg:,.2f}" if isinstance(avg, (int, float)) else str(avg),
                            "open": f"{open_p:,.2f}" if isinstance(open_p, (int, float)) else str(open_p),
                            "vol": f"{v_num:,}", "oi": f"{o_num:,}",
                            "vol_num": v_num, "oi_num": o_num
                        })
                        total_vol += v_num
                        total_oi += o_num
            except Exception as e:
                print(f"Error fetching {sym}: {e}")

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
    import requests
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    res = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT --- Code: {res.status_code}")

if __name__ == "__main__":
    results, total_vol, total_oi, set_data, tfex_data = fetch_all_data_via_playwright()
    msg = format_line_message(results, total_vol, total_oi, set_data, tfex_data)
    send_line_message(msg)
    print("ทำงานเสร็จสิ้น!")

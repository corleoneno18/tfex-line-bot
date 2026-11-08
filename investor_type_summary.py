import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

def format_number_with_sign(val_str):
    if not val_str or val_str == "-":
        return "-"
    clean_val = val_str.replace("+", "").replace(",", "").strip()
    try:
        num = int(float(clean_val))
        if num > 0:
            return f"+{num:,}"
        else:
            return f"{num:,}"
    except (ValueError, TypeError):
        return val_str

def fetch_investor_type_data():
    tfex_data = {
        "นักลงทุนต่างชาติ": {},
        "นักลงทุนสถาบัน": {},
        "นักลงทุนภายในประเทศ": {}
    }
    overview_data = {
        "Call": "-",
        "Put": "-"
    }
    set50_data = {
        "latest": "-",
        "change": "-",
        "volume": "-",
        "value": "-"
    }

    print("กำลังดึงข้อมูล TFEX, Total Options และ SET50 Index...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # 1. ดึงข้อมูลประเภทนักลงทุน TFEX
        try:
            page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass

            page.evaluate("window.scrollBy(0, 400)")
            time.sleep(2)

            rows = page.locator("tr").all()
            categories = [
                "Equity Index Futures",
                "Single Stock Futures",
                "Currency Futures",
                "Equity Index Call Options",
                "Equity Index Put Options"
            ]
            
            for r in rows:
                text = r.text_content().strip()
                cleaned_text = " ".join(text.split())
                
                for cat in categories:
                    if cat in cleaned_text:
                        nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*|-', cleaned_text)
                        if len(nums) >= 9:
                            tfex_data["นักลงทุนสถาบัน"][cat] = format_number_with_sign(nums[2])
                            tfex_data["นักลงทุนต่างชาติ"][cat] = format_number_with_sign(nums[5])
                            tfex_data["นักลงทุนภายในประเทศ"][cat] = format_number_with_sign(nums[8])
        except Exception as e:
            print(f"Error TFEX Investor Type: {e}")

        # 2. ดึงข้อมูล Total Options (Equity Index)
        try:
            page.goto("https://www.settrade.com/th/derivatives/overview", wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass

            page.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll('*'));
                elements.forEach(el => {
                    const txt = el.textContent.trim();
                    if (txt === 'Total Options' || txt === 'Equity Index') {
                        el.click();
                    }
                });
            }""")
            time.sleep(3)

            overview_data = page.evaluate("""() => {
                let callVal = "-";
                let putVal = "-";
                const rows = Array.from(document.querySelectorAll('tr, div'));
                let inEquityIndex = false;

                for (let row of rows) {
                    const text = row.innerText || "";
                    if (text.includes("Equity Index")) {
                        inEquityIndex = true;
                        continue;
                    }
                    if (text.includes("Currency") || text.includes("Total Market")) {
                        inEquityIndex = false;
                    }

                    if (inEquityIndex) {
                        if (text.includes("Call") && !text.includes("Put / Call") && !text.includes("Options")) {
                            const nums = text.match(/\\b\\d{1,3}(?:,\\d{3})*\\b/g);
                            if (nums && nums.length > 0) {
                                callVal = nums[nums.length - 1];
                            }
                        }
                        if (text.includes("Put") && !text.includes("Put / Call") && !text.includes("Options")) {
                            const nums = text.match(/\\b\\d{1,3}(?:,\\d{3})*\\b/g);
                            if (nums && nums.length > 0) {
                                putVal = nums[nums.length - 1];
                            }
                        }
                    }
                }
                return { Call: callVal, Put: putVal };
            }""")
        except Exception as e:
            print(f"Error TFEX Overview Options: {e}")

        # 3. ดึงข้อมูล SET50 Index (ล่าสุด, เปลี่ยนแปลง, ปริมาณ, มูลค่า)
        try:
            page.goto("https://www.settrade.com/th/equities/market-summary/overview", wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)

            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass

            set50_data = page.evaluate("""() => {
                let result = { latest: "-", change: "-", volume: "-", value: "-" };
                const rows = Array.from(document.querySelectorAll('tr'));
                for (let r of rows) {
                    const text = r.innerText || "";
                    if (text.includes("SET50") && !text.includes("SET50FF") && !text.includes("SET50")) {
                        // ปรับค้นหาแถวที่เป็น SET50 โดยตรง
                    }
                    if (text.startsWith("SET50\\t") || text.startsWith("SET50 ") || text.includes("SET50")) {
                        const tds = Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim());
                        if (tds.length >= 7 && tds[0] === "SET50") {
                            result.latest = tds[1] || "-";
                            result.change = (tds[2] && tds[3]) ? `${tds[2]} (${tds[3]})` : (tds[2] || "-");
                            result.volume = tds[5] || "-";
                            result.value = tds[6] || "-";
                            break;
                        }
                    }
                }
                return result;
            }""")
        except Exception as e:
            print(f"Error SET50 Overview: {e}")
        finally:
            browser.close()

    return tfex_data, overview_data, set50_data

def format_investor_message(tfex_data, overview_data, set50_data):
    groups = [
        ("🌐 นักลงทุนต่างชาติ", "นักลงทุนต่างชาติ"),
        ("🏦 นักลงทุนสถาบัน", "นักลงทุนสถาบัน"),
        ("👤 นักลงทุนภายในประเทศ", "นักลงทุนภายในประเทศ")
    ]
    
    categories = [
        "Equity Index Futures",
        "Single Stock Futures",
        "Currency Futures",
        "Equity Index Call Options",
        "Equity Index Put Options"
    ]
    
    investor_lines = []
    for title, group_key in groups:
        lines = [title]
        tfex_group = tfex_data.get(group_key, {})
        for cat in categories:
            val = tfex_group.get(cat, "-")
            lines.append(f"• {cat}: {val}")
        investor_lines.append("\n".join(lines))
        
    msg = "👥 สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน (TFEX)\n\n" + "\n\n".join(investor_lines)
    
    # เพิ่มส่วน Total Options
    msg += f"\n\n📈 Total Options (Equity Index)\n• Call: {overview_data.get('Call', '-')}\n• Put: {overview_data.get('Put', '-')}"
    
    # เพิ่มส่วน SET50 Index ต่อท้าย
    msg += (
        f"\n\n📊 SET50 Index\n"
        f"• ล่าสุด: {set50_data.get('latest', '-')}\n"
        f"• เปลี่ยนแปลง: {set50_data.get('change', '-')}\n"
        f"• ปริมาณ (หุ้น): {set50_data.get('volume', '-')}\n"
        f"• มูลค่า (ลบ.): {set50_data.get('value', '-')}"
    )
    
    return msg

def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        print("กรุณาตั้งค่า LINE_CHANNEL_ACCESS_TOKEN และ LINE_USER_ID")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }
    res = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT TFEX --- Status: {res.status_code}")

if __name__ == "__main__":
    tfex_data, overview_data, set50_data = fetch_investor_type_data()
    msg = format_investor_message(tfex_data, overview_data, set50_data)
    send_line_message(msg)

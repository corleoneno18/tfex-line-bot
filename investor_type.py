import os
import requests

def fetch_investor_type_data():
    """ดึงข้อมูลประเภทนักลงทุน TFEX โดยตรงจาก API ของ Settrade"""
    tfex_data = {
        "นักลงทุนสถาบัน": {},
        "นักลงทุนต่างชาติ": {},
        "นักลงทุนภายในประเทศ": {}
    }

    print("กำลังดึงข้อมูลประเภทนักลงทุน TFEX จาก API...")
    url = "https://api.settrade.com/api/market/derivatives/investor-type"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.settrade.com/"
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            # รองรับทั้งโครงสร้างที่เป็น list ของ items หรือเป็น dict
            items = data.get("investorTypes", []) if isinstance(data, dict) else data
            
            for item in items:
                # ดึงชื่อประเภทสินค้า เช่น Equity Index Futures
                cat = item.get("derivativesType", "") or item.get("symbolGroup", "")
                if cat:
                    # แปลงตัวเลขเป็นข้อความพร้อมเครื่องหมาย +/-, ตัวอย่าง: +28,716
                    def fmt(val):
                        if val is None or val == "-": return "-"
                        try:
                            n = int(val)
                            return f"+{n:,}" if n > 0 else f"{n:,}"
                        except:
                            return str(val)

                    tfex_data["นักลงทุนสถาบัน"][cat] = fmt(item.get("institutionNet", item.get("instNet", "-")))
                    tfex_data["นักลงทุนต่างชาติ"][cat] = fmt(item.get("foreignNet", item.get("foreignNet", "-")))
                    tfex_data["นักลงทุนภายในประเทศ"][cat] = fmt(item.get("individualNet", item.get("customerNet", "-")))
        else:
            print(f"API Response Status Code: {res.status_code}")
    except Exception as e:
        print(f"Error fetching API: {e}")

    return tfex_data

def format_investor_message(tfex_data):
    """จัดรูปแบบข้อความ แสดงเฉพาะ ต่างชาติ, สถาบัน, และในประเทศ"""
    groups = [
        ("🌐 **นักลงทุนต่างชาติ**", "นักลงทุนต่างชาติ"),
        ("🏦 **นักลงทุนสถาบัน**", "นักลงทุนสถาบัน"),
        ("👤 **นักลงทุนภายในประเทศ**", "นักลงทุนภายในประเทศ")
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
        
    return "👥 **สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน**\n\n" + "\n\n".join(investor_lines)

def send_line_message(message):
    """ส่งข้อความเข้า LINE"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
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
    print(f"--- LINE API RESULT --- Status: {res.status_code}")

if __name__ == "__main__":
    tfex_data = fetch_investor_type_data()
    msg = format_investor_message(tfex_data)
    send_line_message(msg)
    print("ส่งสรุปประเภทนักลงทุนเข้า LINE สำเร็จ!")

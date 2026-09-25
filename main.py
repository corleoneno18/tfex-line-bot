import os
import re
import time
import requests
from google import genai
from playwright.sync_api import sync_playwright

def get_tfex_data_via_playwright():
    """เปิดหน้าเว็บ Settrade ผ่าน Playwright เพื่อดึงข้อความตาราง"""
    url = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    print("กำลังเปิดเบราว์เซอร์เพื่อดึงข้อมูลตาราง TFEX...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("กำลังรอโหลดตารางราคา...")
            page.wait_for_selector("table", timeout=30000)
            time.sleep(5)  # รอให้ข้อมูล Render ครบถ้วน
            
            text_content = page.locator("body").inner_text()
            browser.close()
            print("ดึงข้อมูลจากหน้าเว็บสำเร็จ!")
            return text_content
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงหน้าเว็บ: {e}")
            browser.close()
            return None

def fallback_parse_content(text_content):
    """สกัดข้อมูลตารางตรงตามโครงสร้าง Settrade (อ้างอิงลำดับคอลัมน์จริง)"""
    print("สลับมาใช้ระบบ Fallback Regex Extractor (ตรงตามโครงสร้างตารางจริง)...")
    
    # Pattern สแกนจับลำดับคอลัมน์:
    # 1:Symbol, 2:Last, 3:Chg, 4:Pct, 5:High, 6:Low, 7:Vol, 8:OI, 9:Settle, 10:Open, 11:Avg
    pattern = r'(S50[A-Z0-9]+)\s+([\d\.\,\-]+)\s+([\+\-\d\.\,]+)\s+([\+\-\d\.\,%]+)\s+([\d\.\,\-]+)\s+([\d\.\,\-]+)\s+([\d\,]+)\s+([\d\,]+)\s+([\d\.\,\-]+)\s+([\d\.\,\-]+)\s+([\d\.\,\-]+)'
    matches = re.findall(pattern, text_content)
    
    lines = []
    total_vol = 0
    total_oi = 0
    
    if matches:
        for m in matches:
            sym, last, chg, pct, high, low, vol, oi, settle, open_p, avg_p = m
            
            v_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
            o_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0
            total_vol += v_num
            total_oi += o_num
            
            lines.append(
                f"📌 **[{sym}]**\n"
                f"• ราคาเปิด: {open_p}\n"
                f"• ราคาสูงสุด: {high}\n"
                f"• ราคาต่ำสุด: {low}\n"
                f"• ราคาล่าสุด: {last}\n"
                f"• ราคาเฉลี่ย: {avg_p}\n"
                f"• เปลี่ยนแปลง: {chg} ({pct})\n"
                f"• ปริมาณซื้อขาย: {vol} สัญญา\n"
                f"• สถานะคงค้าง (OI): {oi} สัญญา"
            )
    else:
        # กรณีหาด้วย Pattern ครบทุกช่องไม่พบ ให้ใช้วิธีจับแยกท่อนตัวเลขแบบเรียงลำดับ
        symbols = list(dict.fromkeys(re.findall(r'S50[A-Z0-9]+', text_content)))
        for sym in symbols:
            match = re.search(re.escape(sym) + r'[\s\S]{1,150}', text_content)
            if match:
                raw_text = match.group(0).replace('\n', ' ')
                tokens = raw_text.split()
                # กรองคำที่ไม่ใช่ตัวเลขออก
                nums = [t for t in tokens if re.match(r'^[\+\-\d\.\,]+%?$', t) or t == '-']
                if len(nums) >= 10:
                    # เรียงตำแหน่งตามตารางจริง: 0:Last, 1:Chg, 2:Pct, 3:High, 4:Low, 5:Vol, 6:OI, 7:Settle, 8:Open, 9:Avg
                    lines.append(
                        f"📌 **[{sym}]**\n"
                        f"• ราคาเปิด: {nums[8]}\n"
                        f"• ราคาสูงสุด: {nums[3]}\n"
                        f"• ราคาต่ำสุด: {nums[4]}\n"
                        f"• ราคาล่าสุด: {nums[0]}\n"
                        f"• ราคาเฉลี่ย: {nums[9]}\n"
                        f"• เปลี่ยนแปลง: {nums[1]} ({nums[2]})\n"
                        f"• ปริมาณซื้อขาย: {nums[5]} สัญญา\n"
                        f"• สถานะคงค้าง (OI): {nums[6]} สัญญา"
                    )

    if lines:
        summary_text = "\n\n".join(lines)
        if total_vol > 0 or total_oi > 0:
            summary_text += f"\n\n📊 **สรุปรวม SET50 Futures ทั้งหมด**\n• ปริมาณการซื้อขายรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม (OI): {total_oi:,} สัญญา"
        return summary_text

    return "ระบบไม่สามารถจัดรูปแบบตารางได้ กรุณาตรวจสอบหน้าเว็บ Settrade อีกครั้ง"

def summarize_with_gemini(raw_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อความหน้าเว็บ Settrade TFEX ด้านล่างนี้ ลำดับคอลัมน์ตารางจริงเรียงดังนี้:
    [ชื่อสัญญา] [ราคาล่าสุด] [เปลี่ยนแปลง] [เปลี่ยนแปลง%] [ราคาสูงสุด] [ราคาต่ำสุด] [ปริมาณ] [สถานะคงค้าง] [ราคาชำระราคา] [ราคาเปิด] [ราคาเฉลี่ย]

    ให้สกัดข้อมูลของ SET50 Futures ทุก Series ทั้งหมดที่มี (เช่น S50U26, S50V26, S50X26, S50Z26, S50H27, S50M27 ฯลฯ)
    และสรุปผลรวมปริมาณซื้อขายรวมกับสถานะคงค้างรวมทั้งหมดท้ายข้อความ
    
    จัดรูปแบบสรุปเป็นข้อความสำหรับส่งเข้า LINE ดังนี้:

    📌 **[ชื่อย่อสัญญา]**
    • ราคาเปิด: 
    • ราคาสูงสุด: 
    • ราคาต่ำสุด: 
    • ราคาล่าสุด: 
    • ราคาเฉลี่ย: 
    • เปลี่ยนแปลง: 
    • ปริมาณซื้อขาย: (สัญญา)
    • สถานะคงค้าง (OI): (สัญญา)

    📊 **สรุปรวม SET50 Futures ทั้งหมด**
    • ปริมาณการซื้อขายรวม: (สัญญา)
    • สถานะคงค้างรวม (OI): (สัญญา)

    ข้อมูลจากหน้าเว็บ:
    {raw_text[:15000]}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"กำลังเรียก Gemini API ครั้งที่ {attempt + 1}...")
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            if response.text and "📌" in response.text:
                print("Gemini ประมวลผลสำเร็จ!")
                return response.text
        except Exception as e:
            print(f"ข้อผิดพลาดจาก Gemini: {e}")
            
        time.sleep(3)
                
    print("Gemini API ไม่พร้อมใช้งาน สลับไปใช้ Fallback Extractor...")
    return None

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
                "text": f"📊 สรุป SET50 Futures วันนี้:\n\n{message}"
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
        text_content = get_tfex_data_via_playwright()
        if text_content:
            summary = summarize_with_gemini(text_content)
            if not summary:
                summary = fallback_parse_content(text_content)
            
            send_line_message(summary)
            print("ทำงานสำเร็จ!")
        else:
            print("ไม่สามารถดึงข้อมูลจากหน้าเว็บได้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")

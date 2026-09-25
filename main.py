import os
import re
import time
import requests
from google import genai
from playwright.sync_api import sync_playwright

def get_tfex_data_via_playwright():
    """เปิดหน้าเว็บ Settrade ผ่าน Playwright เพื่อดึงทั้ง innerText และ HTML"""
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
            time.sleep(5)  # รอให้ข้อมูลตัวเลข Render ครบ
            
            text_content = page.locator("body").inner_text()
            html_content = page.content()
            browser.close()
            print("ดึงข้อมูลจากหน้าเว็บสำเร็จ!")
            return text_content, html_content
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงหน้าเว็บ: {e}")
            browser.close()
            return None, None

def fallback_parse_content(text_content):
    """สกัดข้อมูลตาราง Settrade TFEX ปรับให้ดึงราคาเปิด (Open Price) แทนราคาเฉลี่ย"""
    print("สลับมาใช้ระบบ Fallback Regex Extractor (ปรับใช้ราคาเปิด)...")
    
    # Pattern จับแถวตาราง Settrade TFEX: [Symbol] [Month/Year] [Last] [Chg] [%Chg] [Open] [High] [Low] [Vol] [OI]
    pattern = r'(S50[A-Z0-9]+)\s+([ก-ฮa-zA-Z\.\s\d]+?)\s+([\d\.\,\-]+)\s+([\+\-\d\.\,]+)\s+([\+\-\d\.\,%]+)\s+([\d\.\,\-]+)\s+([\d\.\,\-]+)\s+([\d\.\,\-]+)\s+([\d\,]+)\s+([\d\,]+)'
    matches = re.findall(pattern, text_content)
    
    lines = []
    total_vol = 0
    total_oi = 0
    
    if matches:
        for m in matches:
            sym, month, last, chg, pct, open_p, high, low, vol, oi = m
            
            # คำนวณผลรวม
            v_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
            o_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0
            total_vol += v_num
            total_oi += o_num
            
            lines.append(
                f"📌 **{sym}** ({month.strip()})\n"
                f"• ราคาล่าสุด: {last}\n"
                f"• เปลี่ยนแปลง: {chg} ({pct})\n"
                f"• ราคาเปิด: {open_p}\n"
                f"• ราคาสูงสุด / ต่ำสุด: {high} / {low}\n"
                f"• ปริมาณซื้อขาย: {vol} สัญญา\n"
                f"• สถานะคงค้าง (OI): {oi} สัญญา"
            )
    else:
        # หากค้นหาแพทเทิร์นตารางแบบละเอียดไม่เจอ ให้ใช้ Regex ค้นหาตัวเลขเบื้องต้น
        symbols = list(dict.fromkeys(re.findall(r'S50[A-Z0-9]+', text_content)))
        for sym in symbols:
            match = re.search(re.escape(sym) + r'[\s\S]{1,120}', text_content)
            if match:
                raw_line = match.group(0).replace('\n', ' ')
                tokens = raw_line.split()
                if len(tokens) >= 9:
                    lines.append(
                        f"📌 **{sym}**\n"
                        f"• ราคาล่าสุด: {tokens[3] if len(tokens)>3 else '-'}\n"
                        f"• เปลี่ยนแปลง: {tokens[4] if len(tokens)>4 else '-'} ({tokens[5] if len(tokens)>5 else '-'})\n"
                        f"• ราคาเปิด: {tokens[6] if len(tokens)>6 else '-'}\n"
                        f"• ราคาสูงสุด / ต่ำสุด: {tokens[7] if len(tokens)>7 else '-'} / {tokens[8] if len(tokens)>8 else '-'}"
                    )

    if lines:
        summary_text = "\n\n".join(lines)
        if total_vol > 0 or total_oi > 0:
            summary_text += f"\n\n📊 **สรุปรวม SET50 Futures ทั้งหมด**\n• ปริมาณการซื้อขายรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม (OI): {total_oi:,} สัญญา"
        return summary_text

    return "ระบบไม่สามารถจัดรูปแบบตารางได้ กรุณาตรวจสอบหน้าเว็บ Settrade อีกครั้ง"

def summarize_with_gemini(raw_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อความหน้าเว็บ Settrade TFEX ด้านล่างนี้ ให้สกัดข้อมูลตารางราคาของ SET50 Futures ทุก Series ทั้งหมดที่มี (เช่น S50U26, S50Z26, S50H27 ฯลฯ)
    แล้วจัดรูปแบบสรุปเป็นข้อความอ่านง่ายสำหรับส่งเข้า LINE ดังนี้:

    📌 **[ชื่อย่อสัญญา]**
    • ราคาล่าสุด: 
    • เปลี่ยนแปลง: (พร้อม %)
    • ราคาเปิด: 
    • ราคาสูงสุด / ต่ำสุด: 
    • ปริมาณ (สัญญา): 
    • สถานะคงค้าง (OI): 

    พร้อมสรุปผลรวม ปริมาณสัญญา และ สถานะคงค้าง ทั้งหมดท้ายข้อความด้วย

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
        text_content, html_content = get_tfex_data_via_playwright()
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

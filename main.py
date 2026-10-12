import asyncio
import os
import subprocess
import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# --- المتغيرات الأساسية (قم بتعديلها) ---
BOT_TOKEN = "ضع_توكن_البوت_هنا"
API_ID = 123456 # ضع الـ API_ID
API_HASH = "ضع_الـ_API_HASH_هنا"
VERCEL_WEB_URL = "https://your-vercel-app.vercel.app/?app="

# --- إعدادات GitHub ---
GITHUB_TOKEN = "ضع_توكن_جيت_هب_هنا"
GITHUB_REPO = "ibablack/store" # ضع اسم حسابك ومستودعك

os.makedirs("certs", exist_ok=True)
os.makedirs("signed_ipas", exist_ok=True)
os.makedirs("ipas", exist_ok=True)

user_states = {}
APPS = ["esign", "ksign", "gbox", "scarlet", "feather", "zsign", "cinemana"]

bot = Client("SignBot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

def upload_to_github_release(udid, signed_files):
    headers_api = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    tag_name = f"signed-{udid}"
    
    # 1. حذف الـ Release القديم إذا وجد لنفس الـ UDID
    check_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag_name}"
    res = requests.get(check_url, headers=headers_api)
    if res.status_code == 200:
        rel_id = res.json()["id"]
        requests.delete(f"https://api.github.com/repos/{GITHUB_REPO}/releases/{rel_id}", headers=headers_api)
        requests.delete(f"https://api.github.com/repos/{GITHUB_REPO}/git/refs/tags/{tag_name}", headers=headers_api)

    # 2. إنشاء Release جديد
    create_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    data = {"tag_name": tag_name, "name": f"Signed Apps - {udid}", "body": "تم التوقيع والرفع تلقائياً بواسطة البوت."}
    res = requests.post(create_url, headers=headers_api, json=data)
    release_id = res.json()["id"]

    # 3. رفع التطبيقات الموقعة
    upload_base_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets"
    headers_upload = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/octet-stream"}

    for file_path in signed_files:
        if os.path.exists(file_path):
            file_name = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                requests.post(f"{upload_base_url}?name={file_name}", headers=headers_upload, data=f)

@bot.on_message(filters.document & filters.private)
async def handle_certificates(client: Client, message: Message):
    user_id = message.from_user.id
    file_name = message.document.file_name
    
    if user_id not in user_states:
        user_states[user_id] = {"p12_id": None, "prov_id": None, "udid": None, "step": "waiting_for_files"}
    
    state = user_states[user_id]
    
    if file_name.endswith(".p12"):
        state["p12_id"] = message.document.file_id
        if not state["udid"]: state["udid"] = file_name.rsplit('.', 1)[0]
    elif file_name.endswith(".mobileprovision"):
        state["prov_id"] = message.document.file_id
        if not state["udid"]: state["udid"] = file_name.rsplit('.', 1)[0]
    else:
        return await message.reply_text("❌ البوت يقبل فقط ملفات `.p12` و `.mobileprovision`.")

    if state["p12_id"] and state["prov_id"]:
        state["step"] = "waiting_for_password"
        await message.reply_text("✅ تم استلام ملفات الشهادة بالكامل.\nالرجاء إرسال **كلمة المرور** الخاصة بالشهادة:")
    else:
        missing = ".mobileprovision" if state["p12_id"] else ".p12"
        await message.reply_text(f"📥 تم استلام `{file_name}`.\nبانتظار إرسال ملف `{missing}`...")

@bot.on_message(filters.text & filters.private)
async def handle_password(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id in user_states and user_states[user_id].get("step") == "waiting_for_password":
        password = message.text
        udid = user_states[user_id]["udid"]
        state = user_states[user_id]
        
        processing_msg = await message.reply_text("⏳ جاري التوقيع المحلي للتطبيقات...")
        
        p12_path = f"certs/{udid}.p12"
        prov_path = f"certs/{udid}.mobileprovision"
        await bot.download_media(state["p12_id"], file_name=p12_path)
        await bot.download_media(state["prov_id"], file_name=prov_path)
        
        signed_files_to_upload = []
        for app_name in APPS:
            base_ipa = f"ipas/{app_name}.ipa"
            output_ipa = f"signed_ipas/{app_name}_{udid}.ipa"
            if os.path.exists(base_ipa):
                command = f"zsign -k {p12_path} -p '{password}' -m {prov_path} -o {output_ipa} {base_ipa}"
                subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                signed_files_to_upload.append(output_ipa)
        
        await processing_msg.edit_text("☁️ تم التوقيع! جاري الرفع إلى سيرفرات التثبيت (GitHub Releases)...")
        await asyncio.to_thread(upload_to_github_release, udid, signed_files_to_upload)

        # تنظيف الملفات
        if os.path.exists(p12_path): os.remove(p12_path)
        if os.path.exists(prov_path): os.remove(prov_path)
        for f in signed_files_to_upload:
            if os.path.exists(f): os.remove(f)

        buttons = [
            [InlineKeyboardButton("Esign", url=f"{VERCEL_WEB_URL}esign&udid={udid}"), InlineKeyboardButton("Ksign", url=f"{VERCEL_WEB_URL}ksign&udid={udid}")],
            [InlineKeyboardButton("G BOX", url=f"{VERCEL_WEB_URL}gbox&udid={udid}"), InlineKeyboardButton("SCARLET", url=f"{VERCEL_WEB_URL}scarlet&udid={udid}")],
            [InlineKeyboardButton("FEATHER", url=f"{VERCEL_WEB_URL}feather&udid={udid}"), InlineKeyboardButton("ZSIGN", url=f"{VERCEL_WEB_URL}zsign&udid={udid}")],
            [InlineKeyboardButton("وسينمانا", url=f"{VERCEL_WEB_URL}cinemana&udid={udid}")]
        ]
        
        await processing_msg.delete()
        await message.reply_text(f"✅ تم توقيع التطبيقات ورفعها بنجاح!\nالـ UDID: `{udid}`\nوهو الآن جاهز للتثبيت:", reply_markup=InlineKeyboardMarkup(buttons))
        del user_states[user_id]

if __name__ == "__main__":
    bot.run()

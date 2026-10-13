import os
import subprocess
import requests
import asyncio
from contextlib import asynccontextmanager
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_OWNER = os.environ.get("GITHUB_OWNER") 
GITHUB_REPO = os.environ.get("GITHUB_REPO")   
RENDER_APP_URL = os.environ.get("RENDER_APP_URL") 

if not all([BOT_TOKEN, API_ID, API_HASH, GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, RENDER_APP_URL]):
    print("❌ خطأ: هناك توكنات مفقودة!")
    exit(1)

for d in ["certs", "signed_ipas", "ipas", "images", "templates"]:
    os.makedirs(d, exist_ok=True)

APPS = ["esign", "ksign", "gbox", "scarlet", "feather", "zsign", "cinemana"]
user_states = {}

# إضافة in_memory=True مهمة جداً لضمان عدم تعليق البوت في خوادم ريندر
bot = Client("SignBot", in_memory=True, bot_token=BOT_TOKEN, api_id=int(API_ID), api_hash=API_HASH)

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    print(f"🔔 [مراقبة] تم استلام أمر /start من: {message.from_user.first_name}")
    welcome_text = (
        "👋 أهلاً بك في بوت التوقيع السريع (IBA Black).\n\n"
        "لبدء التوقيع، يرجى إرسال ملفات الشهادة الخاصة بك:\n"
        "1️⃣ ملف الـ `.p12`\n"
        "2️⃣ ملف الـ `.mobileprovision`\n\n"
        "يمكنك إرسالها معاً أو كل ملف على حدة لتتمكن من التثبيت المباشر."
    )
    await message.reply_text(welcome_text)

@bot.on_message(filters.document & filters.private)
async def handle_certs(client: Client, message: Message):
    print(f"📁 [مراقبة] تم استلام ملف: {message.document.file_name}")
    user_id, file_name = message.from_user.id, message.document.file_name
    if user_id not in user_states: user_states[user_id] = {"p12_id": None, "prov_id": None, "udid": None, "step": "waiting_for_files"}
    
    state = user_states[user_id]
    if file_name.endswith(".p12"): state["p12_id"], state["udid"] = message.document.file_id, state["udid"] or file_name.rsplit('.', 1)[0]
    elif file_name.endswith(".mobileprovision"): state["prov_id"], state["udid"] = message.document.file_id, state["udid"] or file_name.rsplit('.', 1)[0]
    else: return await message.reply_text("❌ فقط ملفات .p12 و .mobileprovision")

    if state["p12_id"] and state["prov_id"]:
        state["step"] = "waiting_for_password"
        await message.reply_text("✅ تم استلام الشهادة.\nالرجاء إرسال **كلمة المرور**:")
    else:
        missing = ".mobileprovision" if state["p12_id"] else ".p12"
        await message.reply_text(f"📥 تم استلام `{file_name}`.\nبانتظار `{missing}`...")

@bot.on_message(filters.text & filters.private)
async def handle_password(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].get("step") == "waiting_for_password":
        print(f"🔑 [مراقبة] تم استلام الباسورد، بدء التوقيع...")
        pwd, udid, state = message.text, user_states[user_id]["udid"], user_states[user_id]
        processing_msg = await message.reply_text("⏳ جاري التوقيع المحلي...")
        
        p12_path, prov_path = f"certs/{udid}.p12", f"certs/{udid}.mobileprovision"
        await bot.download_media(state["p12_id"], file_name=p12_path)
        await bot.download_media(state["prov_id"], file_name=prov_path)
        
        signed_files = []
        for app in APPS:
            base, output = f"ipas/{app}.ipa", f"signed_ipas/{app}_{udid}.ipa"
            if os.path.exists(base):
                subprocess.run(f"zsign -k {p12_path} -p '{pwd}' -m {prov_path} -o {output} {base}", shell=True, capture_output=True)
                signed_files.append(output)
        
        await processing_msg.edit_text("☁️ جاري الرفع إلى سيرفرات GitHub Releases المباشرة...")
        await asyncio.to_thread(upload_to_github_release, udid, signed_files)

        for f in [p12_path, prov_path] + signed_files: 
            if os.path.exists(f): os.remove(f)

        buttons = [
            [InlineKeyboardButton("Esign", url=f"{RENDER_APP_URL}/?app=esign&udid={udid}"), InlineKeyboardButton("Ksign", url=f"{RENDER_APP_URL}/?app=ksign&udid={udid}")],
            [InlineKeyboardButton("G BOX", url=f"{RENDER_APP_URL}/?app=gbox&udid={udid}"), InlineKeyboardButton("SCARLET", url=f"{RENDER_APP_URL}/?app=scarlet&udid={udid}")],
            [InlineKeyboardButton("FEATHER", url=f"{RENDER_APP_URL}/?app=feather&udid={udid}"), InlineKeyboardButton("ZSIGN", url=f"{RENDER_APP_URL}/?app=zsign&udid={udid}")],
            [InlineKeyboardButton("وسينمانا", url=f"{RENDER_APP_URL}/?app=cinemana&udid={udid}")]
        ]
        
        await processing_msg.delete()
        await message.reply_text(f"✅ تم التوقيع والرفع بنجاح!\nالـ UDID: `{udid}`\nوهو الآن جاهز للتثبيت:", reply_markup=InlineKeyboardMarkup(buttons))
        del user_states[user_id]

def upload_to_github_release(udid, signed_files):
    headers_api = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    tag_name = f"signed-{udid}"
    
    res = requests.get(f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tags/{tag_name}", headers=headers_api)
    if res.status_code == 200:
        requests.delete(f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{res.json()['id']}", headers=headers_api)
        requests.delete(f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/tags/{tag_name}", headers=headers_api)

    res = requests.post(f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases", headers=headers_api, json={"tag_name": tag_name, "name": f"Signed - {udid}"})
    release_id = res.json()["id"]
    upload_url = f"https://uploads.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{release_id}/assets"

    headers_upload = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/octet-stream"}
    for file_path in signed_files:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                requests.post(f"{upload_url}?name={os.path.basename(file_path)}", headers=headers_upload, data=f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.start()
    yield
    await bot.stop()

api = FastAPI(lifespan=lifespan)
api.mount("/images", StaticFiles(directory="images"), name="images")

@api.get("/")
async def serve_frontend():
    return FileResponse("templates/index.html")

@api.get("/api/plist")
async def generate_plist(app: str, udid: str):
    ipaUrl = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/signed-{udid}/{app}_{udid}.ipa"
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>items</key>
    <array><dict>
        <key>assets</key>
        <array><dict><key>kind</key><string>software-package</string><key>url</key><string>{ipaUrl}</string></dict></array>
        <key>metadata</key>
        <dict>
            <key>bundle-identifier</key><string>com.ibablack.{app}</string>
            <key>bundle-version</key><string>1.0</string>
            <key>kind</key><string>software</string>
            <key>title</key><string>{app.upper()}</string>
        </dict>
    </dict></array>
</dict>
</plist>"""
    return Response(
        content=plist_content, 
        media_type="application/x-apple-aspen-manifest",
        headers={"Content-Disposition": f'attachment; filename="{app}.plist"'}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(api, host="0.0.0.0", port=port)

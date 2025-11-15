import os
import time
import json
import base64
import requests
import streamlit as st
import streamlit.components.v1 as components
from google import genai


# ===============================
# 設定
# ===============================
SYSTEM_PROMPT = """
1⃣知識・定義直接答えます。
2⃣思考・計算問題答えは教えず、解法のヒントのみを示します。
3⃣途中式正誤を判定し、優しく導きます。
4⃣専門用語ステップごとに区切り、専門用語について知っているか確認します。知らなかっ
た場合は、小学生にもわかるように、図や擬音などの表現、例となる面白い文を積極的に使っ
てその場で説明します。
5⃣説明は砕けた会話口調でお願いします。
6⃣いきなりステップを全部出さないでください。「ここで、～～について知っていますか？」
のところでいったん表示するのをやめてください。
7⃣専門用語や途中の過程の分からない部分について説明されたときは、できるだけ詳しく説明
してください。だからと言ってその説明を聞いている人に読むのを飽きさせてしまうような説
明はやめてください。
"""
# --- 共通設定 ---
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (KeyError, AttributeError):
    API_KEY = ""

# ===============================
# 外部CSSの読み込み（レイアウトはstyle.cssで管理）
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")
css_path = os.path.join(os.getcwd(), "style.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ===============================
# アバター画像（静止画のみ）
# ===============================
@st.cache_data
def get_avatar_image():
    base_name = "yukki-static"
    for ext in [".jpg", ".jpeg", ".png"]:
        file_name = base_name + ext
        if os.path.exists(file_name):
            with open(file_name, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8"), (
                    f"data:image/{'jpeg' if ext in ['.jpg', '.jpeg'] else 'png'};base64,"
                ), True
    placeholder_svg = base64.b64encode(
        f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-size="28" fill="#a00" font-family="sans-serif">画像なし</text><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" font-size="16" fill="#a00" font-family="sans-serif">{base_name}.jpg/jpeg/png</text></svg>""".encode("utf-8")
    ).decode("utf-8")
    return placeholder_svg, "data:image/svg+xml;base64,", False

# ===============================
# TTS生成（base64 PCM を保存）
# ===============================
def generate_and_store_tts(text: str):
    if not API_KEY:
        st.session_state.audio_to_play = None
        return
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}},
        },
        "model": TTS_MODEL,
    }
    headers = {"Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            r.raise_for_status()
            result = r.json()
            st.session_state.audio_to_play = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            return
        except requests.exceptions.HTTPError as e:
            if r.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            print("HTTP Error:", e)
            break
        except Exception as e:
            print("TTS Error:", e)
            break
    st.session_state.audio_to_play = None

# ===============================
# セッション初期化
# ===============================
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None
if "chat" not in st.session_state:
    if st.session_state.client:
        st.session_state.chat = st.session_state.client.chats.create(
            model="gemini-2.5-flash",
            config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
        )
    else:
        st.session_state.chat = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None

# ===============================
# サイドバー（静止アバターのみ表示）
# ===============================
with st.sidebar:
    img_base64, data_uri_prefix, has_image = get_avatar_image()
    if not has_image:
        st.warning("アバター画像（yukki-static.jpg/.jpeg/.png）が見つかりません。")
    st.markdown(f'<div class="avatar-container"><img id="avatar" src="{data_uri_prefix}{img_base64}" class="avatar"/></div>', unsafe_allow_html=True)

    # 音声のみ再生（口パクは無し）
    if st.session_state.audio_to_play:
        js = f"""
        <script>
        function base64ToArrayBuffer(base64){{
          const bin = atob(base64); const len = bin.length; const bytes = new Uint8Array(len);
          for(let i=0;i<len;i++) bytes[i]=bin.charCodeAt(i);
          return bytes.buffer;
        }}
        function writeString(view, off, str){{ for (let i=0;i<str.length;i++) view.setUint8(off+i, str.charCodeAt(i)); }}
        function pcmToWav(pcmData, sampleRate){{
          const numChannels=1, bitsPerSample=16, bytesPerSample=bitsPerSample/8;
          const blockAlign=numChannels*bytesPerSample, byteRate=sampleRate*blockAlign, dataSize=pcmData.byteLength;
          const buffer=new ArrayBuffer(44+dataSize), view=new DataView(buffer); let o=0;
          writeString(view,o,'RIFF'); o+=4; view.setUint32(o,36+dataSize,true); o+=4;
          writeString(view,o,'WAVE'); o+=4; writeString(view,o,'fmt '); o+=4;
          view.setUint32(o,16,true); o+=4; view.setUint16(o,1,true); o+=2;
          view.setUint16(o,numChannels,true); o+=2; view.setUint32(o,sampleRate,true); o+=4;
          view.setUint32(o,byteRate,true); o+=4; view.setUint16(o,blockAlign,true); o+=2;
          view.setUint16(o,bitsPerSample,true); o+=2; writeString(view,o,'data'); o+=4;
          view.setUint32(o,dataSize,true); o+=4;
          const pcm16=new Int16Array(pcmData); for(let i=0;i<pcm16.length;i++){{ view.setInt16(o,pcm16[i],true); o+=2; }}
          return new Blob([buffer],{{type:'audio/wav'}});
        }}
        const base64Audio = '{st.session_state.audio_to_play}';
        const sampleRate = 24000;
        const pcm = base64ToArrayBuffer(base64Audio);
        const wavBlob = pcmToWav(pcm, sampleRate);
        const url = URL.createObjectURL(wavBlob);
        const audio = new Audio(url);
        audio.autoplay = true;
        audio.onended = () => URL.revokeObjectURL(url);
        audio.play().catch(()=>URL.revokeObjectURL(url));
        </script>
        """
        components.html(js, height=0, width=0)
        st.session_state.audio_to_play = None

# ===============================
# メイン
# ===============================
st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

st.subheader("音声入力")
components.html("""
<div id="mic-container" class="mic-container">
  <button id="mic-btn" class="mic-btn" onclick="window.parent.startRec()">🎙 話す</button>
  <p id="mic-status" class="mic-status">マイク停止中</p>
</div>
</script>""")
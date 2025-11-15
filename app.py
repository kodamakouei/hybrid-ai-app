import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components
import os
import time

# ===============================
# 設定
# ===============================
SYSTEM_PROMPT = """
あなたは教育的な目的を持つAIアシスタントです。
ユーザーの質問に対して3つのルールに従って応答してください。

1️⃣ 知識・定義は直接答える。
2️⃣ 思考・計算問題は答えを教えず、解法のヒントのみ。
3️⃣ 途中式を見せられた場合は正誤を判定し、優しく導く。
あなたは小学生低学年の先生です。
"""

TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5
SIDEBAR_FIXED_WIDTH = "450px"

# --- APIキー読み込み ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""


# ===============================
# アバター画像取得
# ===============================
@st.cache_data
def get_avatar_image():
    base_name = "yukki-static"
    extensions = [".jpg", ".jpeg", ".png"]
    loaded_image = None
    prefix = ""

    for ext in extensions:
        file = base_name + ext
        if os.path.exists(file):
            with open(file, "rb") as f:
                loaded_image = base64.b64encode(f.read()).decode("utf-8")
                prefix = f"data:image/{'jpeg' if ext in ['.jpg','.jpeg'] else 'png'};base64,"
            break

    if loaded_image:
        return loaded_image, prefix, True

    svg = base64.b64encode(
        f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-size="28" fill="#a00">❌画像なし</text></svg>""".encode()
    ).decode()
    return svg, "data:image/svg+xml;base64,", False


# ===============================
# TTS生成
# ===============================
def generate_and_store_tts(text):
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

    headers = {'Content-Type': 'application/json'}

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            r.raise_for_status()
            result = r.json()

            audio_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            st.session_state.audio_to_play = audio_data
            return

        except Exception:
            time.sleep(2 ** attempt)

    st.session_state.audio_to_play = None


# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")

# --- CSS ---
st.markdown(f"""
<style>
header {{ visibility: hidden; }}
[data-testid="stSidebarContent"] > div:first-child {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    display: flex;
    flex-direction: column;
    align-items: center;
}}
.avatar {{
    width: 400px;
    height: 400px;
    border-radius: 16px;
    object-fit: cover;
}}
section[data-testid="stSidebar"] {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
}}
</style>
""", unsafe_allow_html=True)

# --- 初期化 ---
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None

if "chat" not in st.session_state:
    if st.session_state.client:
        config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
        st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)
    else:
        st.session_state.chat = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None


# ===============================
# サイドバー
# ===============================
with st.sidebar:
    img, prefix, ok = get_avatar_image()
    st.markdown(f"<img src='{prefix}{img}' class='avatar'>", unsafe_allow_html=True)
    if not ok:
        st.warning("⚠️ yukki-static.jpg/png を置いてね")


# ===============================
# メイン
# ===============================
st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考はヒントのみ。画像にも対応！")


# ===============================
# 📸 画像アップローダー（新規追加）
# ===============================
st.subheader("📷 画像を送って質問する")
uploaded_image = st.file_uploader("画像をアップロードしてね", type=["jpg", "jpeg", "png"])

if uploaded_image:
    st.image(uploaded_image, caption="アップロードされた画像", use_column_width=True)


# ===============================
# 会話履歴
# ===============================
st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "🧑"):
        st.markdown(msg["content"])


# ===============================
# チャット入力処理（画像対応版）
# ===============================
if prompt := st.chat_input("質問を書いてね…"):

    st.session_state.messages.append({"role": "user", "content": prompt})

    # --- Gemini Vision の入力 parts を作成 ---
    parts = []

    # 画像があれば追加
    if uploaded_image:
        image_bytes = uploaded_image.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        parts.append({
            "inlineData": {
                "mimeType": uploaded_image.type,
                "data": image_base64
            }
        })

    # テキストも追加
    parts.append({"text": prompt})

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが考え中..."):
            try:
                response = st.session_state.chat.send_message(parts)
                text = response.text

                st.markdown(text)

                # TTS生成
                generate_and_store_tts(text)

                st.session_state.messages.append({"role": "assistant", "content": text})

            except Exception as e:
                msg = f"APIエラー: {e}"
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})

    st.rerun()


# ===============================
# 音声再生（従来通り）
# ===============================
if st.session_state.audio_to_play:
    components.html(f"""
    <script>
        function base64ToArrayBuffer(base64) {{
            const bin = atob(base64);
            const buf = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
            return buf.buffer;
        }}
        const data = base64ToArrayBuffer("{st.session_state.audio_to_play}");
        const audioBlob = new Blob([data], {{type:"audio/wav"}});
        const url = URL.createObjectURL(audioBlob);
        new Audio(url).play();
    </script>
    """, height=0)
    st.session_state.audio_to_play = None

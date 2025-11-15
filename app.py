import streamlit as st
from google import genai
import base64
import json
import requests
import streamlit.components.v1 as components
import os
import time

# =========================================
#  システムプロンプト（元のまま）
# =========================================
SYSTEM_PROMPT = """
あなたは一人の日本人女性の疑似教師であり、「ユッキー」と名乗っています。
...
（あなたの元コードの SYSTEM_PROMPT をそのまま貼ってください）
"""

# =========================================
# APIキー読み込み
# =========================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""

# =========================================
# TTS（音声生成）関数
# =========================================
def generate_and_store_tts(text):
    """
    Gemini Flash 2.0 (tts-1) による日本語音声生成。
    """
    if not text:
        return None

    try:
        client = genai.Client(api_key=API_KEY)

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[text],
            config={
                "audio_config": {
                    "voice_name": "ja-JP-Neural2-B",
                    "speaking_rate": 1.05
                }
            }
        )

        audio_data = None
        for part in response.parts:
            if hasattr(part, "data") and part.data:
                audio_data = part.data
                break

        if not audio_data:
            print("音声パートが見つかりませんでした。")
            return None

        audio_bytes = audio_data
        audio_dir = "generated_audio"
        os.makedirs(audio_dir, exist_ok=True)
        audio_path = os.path.join(
            audio_dir,
            f"tts_{int(time.time())}.wav"
        )

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        print("TTS 音声生成成功:", audio_path)
        return audio_path

    except Exception as e:
        print("TTS生成中にエラー:", e)
        return None


# =========================================
# Streamlit UI 設定
# =========================================
st.set_page_config(
    page_title="ユッキー",
    layout="wide"   # ★サイドバーが無い前提で全幅使用
)

# ---- セッション初期化 ----
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None

if "chat" not in st.session_state:
    if st.session_state.client:
        config = {
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.2
        }
        st.session_state.chat = st.session_state.client.chats.create(
            model="gemini-2.5-flash",
            config=config
        )
    else:
        st.session_state.chat = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None


# =========================================
# メイン画面 UI
# =========================================
st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

# ---------- 画像アップロード ----------
st.subheader("画像を送って質問する")

uploaded_image = st.file_uploader("画像をアップロードしてみよう", type=["jpg", "jpeg", "png"])

if uploaded_image:
    st.image(uploaded_image, caption="アップロードされた画像", use_column_width=True)
    uploaded_bytes = uploaded_image.read()
else:
    uploaded_bytes = None

# ---------- ユーザー音声入力 UI（Web Audio API） ----------
components.html("""
<script>
function startVoiceRecognition() {
    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = "ja-JP";
    recognition.onresult = function(event) {
        const text = event.results[0][0].transcript;
        window.parent.postMessage({type: 'stt-result', text: text}, '*');
    };
    recognition.start();
}
</script>

<button onclick="startVoiceRecognition()" style="
    background-color:#ff8dc7;
    border:none;
    padding:12px 18px;
    border-radius:8px;
    color:white;
    font-size:16px;
    cursor:pointer;
    margin-bottom:10px;
">
🎤 音声で話す
</button>
""", height=80)

# ---------- 音声で認識したテキストの受信 ----------
components.html("""
<script>
window.addEventListener("message", (event) => {
    if (event.data.type === "stt-result") {
        const text = event.data.text;
        window.parent.postMessage({ type: "streamlit:setChatInputValue", value: text }, "*");
        window.parent.postMessage({ type: "streamlit:focusChatInput" }, "*");
    }
});
</script>
""", height=0)

# ---------- チャット履歴 ----------
st.subheader("ユッキーとの会話履歴")

for msg in st.session_state.messages:
    avatar_icon = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# ---------- テキストチャット入力 ----------
if prompt := st.chat_input("質問を入力してください…"):
    # 履歴へ追加
    st.session_state.messages.append({"role": "user", "content": prompt})

    # ファイル付きメッセージ
    file_message = {
        "mime_type": uploaded_image.type if uploaded_image else "text/plain",
        "data": base64.b64encode(uploaded_bytes).decode("utf-8") if uploaded_image else prompt
    }

    # ---- Gemini へ送信 ----
if st.session_state.chat:

    # 画像がある場合
    if uploaded_image:
        response = st.session_state.chat.send_message(
            [
                prompt,
                {
                    "mime_type": uploaded_image.type,
                    "data": uploaded_bytes
                }
            ]
        )

    # テキストだけの場合
    else:
        response = st.session_state.chat.send_message(prompt)

    response_text = response.text if hasattr(response, "text") else str(response)
else:
    response_text = "APIキーが設定されていないため応答できません。"

    # 履歴に追加
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # TTS生成
    audio_path = generate_and_store_tts(response_text)
    if audio_path:
        st.session_state.audio_to_play = audio_path

    st.rerun()

# ---------- 音声再生 ----------
if st.session_state.audio_to_play:
    st.audio(st.session_state.audio_to_play, format="audio/wav")

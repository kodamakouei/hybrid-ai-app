import streamlit as st
from streamlit_mic_recorder import mic_recorder
import google.generativeai as genai
import base64
import requests
import json

# ===================== 設定 =====================
SYSTEM_PROMPT = """
あなたは教育的なAIアシスタントです。
事実の質問には簡潔に答え、思考・計算問題はヒントのみを示します。
"""
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"

# ===================== APIキー読み込み =====================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("❌ Streamlit Secrets に GEMINI_API_KEY が設定されていません。")
    st.stop()

# ===================== Gemini 初期化 =====================
genai.configure(api_key=API_KEY)

# モデルを初期化
if "model" not in st.session_state:
    st.session_state.model = genai.GenerativeModel("gemini-1.5-flash")

if "chat" not in st.session_state:
    st.session_state.chat = st.session_state.model.start_chat(history=[])

# ===================== TTS（音声生成）関数 =====================
def play_tts(text: str):
    """Gemini TTSで音声を生成して再生"""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}
            },
        },
        "model": TTS_MODEL,
    }
    headers = {'Content-Type': 'application/json'}
    r = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
    result = r.json()

    try:
        audio_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        st.audio(base64.b64decode(audio_data), format="audio/wav")
    except Exception as e:
        st.warning(f"音声生成に失敗しました: {e}")

# ===================== Streamlit UI =====================
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー 🎀")
st.caption("音声でも文字でも質問できるAIだよ。思考系問題はヒントだけね💕")

# ===================== 音声録音ボタン =====================
st.markdown("### 🎙️ 音声で質問する")

audio_data = mic_recorder(
    start_prompt="🎤 話す",
    stop_prompt="🛑 停止",
    just_once=True,
    use_container_width=True,
)

# ===================== 音声→テキスト変換 =====================
if audio_data:
    st.audio(audio_data["bytes"])
    st.info("🧠 音声認識中...")

    # 音声をテキストに変換
    model_audio = genai.GenerativeModel("gemini-1.5-flash")
    result = model_audio.generate_content(
        [
            {
                "role": "user",
                "parts": [
                    {"mime_type": "audio/webm", "data": audio_data["bytes"]}
                ],
            }
        ]
    )

    prompt = result.text.strip()
    st.success(f"🗣️ 認識結果: {prompt}")

    # ===================== Geminiへの質問 =====================
    with st.spinner("ユッキーが考え中..."):
        response = st.session_state.chat.send_message(prompt)
        answer = response.text.strip()

        st.chat_message("assistant").markdown(answer)
        play_tts(answer)

# ===================== テキスト入力もサポート =====================
prompt_text = st.chat_input("✍️ 質問を入力してください（または上で話しかけてね）")

if prompt_text:
    with st.chat_message("user"):
        st.markdown(prompt_text)

    with st.chat_message("assistant"):
        with st.spinner("ユッキーが考え中..."):
            response = st.session_state.chat.send_message(prompt_text)
            answer = response.text.strip()
            st.markdown(answer)
            play_tts(answer)

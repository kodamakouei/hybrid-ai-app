import streamlit as st
from streamlit_mic_recorder import mic_recorder
import google.generativeai as genai
import base64
import requests
import json
import os

# ===================== 設定 =====================
SYSTEM_PROMPT = """
あなたは教育的なAIアシスタント「ユッキー」です。
・事実の質問には簡潔に答えること。
・思考や計算問題はヒントのみを教えること。
・ユーザーが成長できるように、優しく導くこと。
"""

# 音声合成モデル (Gemini TTS)
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"

# 音声→テキスト用エンドポイント（Whisper）
STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/whisper-1:transcribe"

# ===================== APIキー =====================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("❌ Streamlit Secrets に GEMINI_API_KEY が設定されていません。")
    st.stop()

# ===================== TTS =====================
def play_tts(text: str):
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}
        },
        "model": TTS_MODEL
    }
    r = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers={"Content-Type": "application/json"}, data=json.dumps(payload))
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

# Geminiチャット初期化
genai.configure(api_key=API_KEY)
if "chat" not in st.session_state:
    model_chat = genai.GenerativeModel("gemini-2.5-flash")
    st.session_state.chat = model_chat.start_chat(history=[])
    st.session_state.chat.send_message(SYSTEM_PROMPT)

# ===================== 音声入力 =====================
st.markdown("### 🎙️ 音声で質問する")
audio_data = mic_recorder(start_prompt="🎤 話す", stop_prompt="🛑 停止", just_once=True, use_container_width=True)

if audio_data:
    st.audio(audio_data["bytes"])
    st.info("🧠 音声認識中...")

    files = {"file": ("audio.webm", audio_data["bytes"], "audio/webm")}
    r = requests.post(f"{STT_URL}?key={API_KEY}", files=files)

    if r.headers.get("Content-Type") == "application/json":
        result = r.json()
        try:
            prompt = result["text"].strip()
            st.success(f"🗣️ 認識結果: {prompt}")

            # ==== チャット ====
            with st.chat_message("user", avatar="🧑"):
                st.markdown(prompt)

            with st.chat_message("assistant", avatar="yukki-icon.jpg"):
                with st.spinner("ユッキーが考え中..."):
                    response = st.session_state.chat.send_message(prompt)
                    answer = response.text.strip()
                    st.markdown(answer)
                    play_tts(answer)

        except Exception as e:
            st.error(f"音声認識エラー: {e}")
            st.json(result)
    else:
        st.error("音声認識APIがJSONを返しませんでした。")
        st.text(r.text)

# ===================== テキスト入力 =====================
prompt_text = st.chat_input("✍️ 質問を入力してください（または上で話しかけてね）")
if prompt_text:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt_text)

    with st.chat_message("assistant", avatar="yukki-icon.jpg"):
        with st.spinner("ユッキーが考え中..."):
            response = st.session_state.chat.send_message(prompt_text)
            answer = response.text.strip()
            st.markdown(answer)
            play_tts(answer)

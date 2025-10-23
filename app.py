import streamlit as st
from google import genai
import os
import base64
import json
import time
import requests
import streamlit.components.v1 as components

# -----------------------------------------------------
# 【システム指示】
# -----------------------------------------------------
SYSTEM_PROMPT = """
あなたは教育的な目的を持つAIアシスタントです。以下のルールに従って回答してください。

【ルール1】 事実・定義などの質問 → 直接簡潔に答える。
【ルール2】 思考・計算・論理の質問 → 解法のヒントのみ。
【ルール3】 途中式の確認 → 正しいかどうかだけ返答。
"""

# -----------------------------------------------------
# --- 共通設定 ---
# -----------------------------------------------------
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5

# --- APIキー ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit Cloudのシークレットを設定してください。")
    st.stop()


# -----------------------------------------------------
# --- 音声を自動再生する関数 ---
# -----------------------------------------------------
@st.cache_data
def base64_to_audio_url(base64_data, sample_rate):
    js_code = f"""
    <script>
        function base64ToArrayBuffer(base64) {{
            const binary_string = window.atob(base64);
            const len = binary_string.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{
                bytes[i] = binary_string.charCodeAt(i);
            }}
            return bytes.buffer;
        }}

        function pcmToWav(pcmData, sampleRate) {{
            const numChannels = 1;
            const bitsPerSample = 16;
            const bytesPerSample = bitsPerSample / 8;
            const blockAlign = numChannels * bytesPerSample;
            const byteRate = sampleRate * blockAlign;
            const dataSize = pcmData.byteLength;
            const buffer = new ArrayBuffer(44 + dataSize);
            const view = new DataView(buffer);
            let offset = 0;

            function writeString(view, offset, string) {{
                for (let i = 0; i < string.length; i++) {{
                    view.setUint8(offset + i, string.charCodeAt(i));
                }}
            }}

            writeString(view, offset, 'RIFF'); offset += 4;
            view.setUint32(offset, 36 + dataSize, true); offset += 4;
            writeString(view, offset, 'WAVE'); offset += 4;
            writeString(view, offset, 'fmt '); offset += 4;
            view.setUint32(offset, 16, true); offset += 4;
            view.setUint16(offset, 1, true); offset += 2;
            view.setUint16(offset, numChannels, true); offset += 2;
            view.setUint32(offset, sampleRate, true); offset += 4;
            view.setUint32(offset, byteRate, true); offset += 4;
            view.setUint16(offset, blockAlign, true); offset += 2;
            view.setUint16(offset, bitsPerSample, true); offset += 2;
            writeString(view, offset, 'data'); offset += 4;
            view.setUint32(offset, dataSize, true); offset += 4;

            const pcm16 = new Int16Array(pcmData);
            for (let i = 0; i < pcm16.length; i++) {{
                view.setInt16(offset, pcm16[i], true);
                offset += 2;
            }}
            return new Blob([buffer], {{ type: 'audio/wav' }});
        }}

        const pcmData = base64ToArrayBuffer('{base64_data}');
        const wavBlob = pcmToWav(pcmData, {sample_rate});
        const audioUrl = URL.createObjectURL(wavBlob);
        const audio = new Audio(audioUrl);
        audio.play().catch(e => console.log("Audio autoplay failed:", e));
    </script>
    """
    components.html(js_code, height=0, width=0)


def generate_and_play_tts(text):
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
            response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            part = candidate.get('content', {}).get('parts', [{}])[0]
            audio_data = part.get('inlineData', {})
            if audio_data and audio_data.get('data'):
                mime_type = audio_data.get('mimeType', 'audio/L16;rate=24000')
                sample_rate = int(mime_type.split('rate=')[1]) if 'rate=' in mime_type else 24000
                base64_to_audio_url(audio_data['data'], sample_rate)
                return True
            st.error("音声データを取得できませんでした。")
            return False
        except Exception as e:
            st.error(f"TTSエラー: {e}")
            return False
    return False


# -----------------------------------------------------
# --- 音声入力UI ---
# -----------------------------------------------------
def speech_to_text_ui():
    st.markdown("### 🎙️ 音声で質問する")
    html_code = """
    <script>
    let recognizing = false;
    let recognition;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ja-JP';
        recognition.interimResults = false;
        recognition.continuous = false;

        function startRecognition() {
            if (!recognizing) {
                recognizing = true;
                recognition.start();
                document.getElementById('mic-status').innerText = '🎧 聴き取り中...';
            } else {
                recognizing = false;
                recognition.stop();
                document.getElementById('mic-status').innerText = 'マイク停止中';
            }
        }

        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            const inputBox = window.parent.document.querySelector('textarea');
            if (inputBox) {
                inputBox.value = transcript;
                const enterEvent = new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }});
                inputBox.dispatchEvent(enterEvent);
            }
            document.getElementById('mic-status').innerText = '✅ 認識完了: ' + transcript;
        };

        recognition.onerror = function(event) {
            document.getElementById('mic-status').innerText = '⚠️ エラー: ' + event.error;
        };
    }
    </script>

    <button onclick="startRecognition()">🎤 話す / 停止</button>
    <p id="mic-status">マイク停止中</p>
    """
    components.html(html_code, height=120)


# -----------------------------------------------------
# --- Streamlit本体 ---
# -----------------------------------------------------
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー")
st.caption("私は対話型AIユッキーだよ。数学の問題など思考する問題の答えは教えないからね💕")

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY)

if "chat" not in st.session_state:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model='gemini-2.5-flash', config=config)

USER_AVATAR = "🧑"
AI_AVATAR = "yukki-icon.jpg"

if "messages" not in st.session_state:
    st.session_state.messages = []

# 履歴
for message in st.session_state.messages:
    avatar = USER_AVATAR if message["role"] == "user" else AI_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

# 🎤 音声入力UI
speech_to_text_ui()

# --- 入力処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AI_AVATAR):
        with st.spinner("思考中..."):
            try:
                response = st.session_state.chat.send_message(prompt)
                response_text = response.text.strip()
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                st.info("🔊 音声応答を準備中...")
                generate_and_play_tts(response_text)
            except Exception as e:
                st.error(f"APIエラー: {e}")

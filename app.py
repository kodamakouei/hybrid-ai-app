import streamlit as st
from google import genai
import os
import base64
import json
import time
import requests
import streamlit.components.v1 as components

# -----------------------------------------------------
# 【システム指示】教育的ハイブリッドAIのルール
# -----------------------------------------------------
SYSTEM_PROMPT = """
あなたは、教育的な目的を持つ高度なAIアシスタントです。ユーザーの質問に対し、以下の厳格な3つのルールに従って応答してください。

【応答ルール1：事実・知識の質問（直接回答）】
質問が、**確定した事実**、**固有名詞**、**定義**、**単純な知識**を尋ねるものである場合、**その答えを直接、かつ簡潔な名詞または名詞句で回答してください**。

【応答ルール2：計算・思考・問題解決の質問（解法ガイド）】
質問が、**計算**、**分析**、**プログラミング**、**論理的な思考**を尋ねるものである場合、**最終的な答えや途中式は絶対に教えないでください**。代わりに、ユーザーが次に取るべき**最初の、最も重要な解法のステップ**や**必要な公式のヒント**を教えることで、ユーザーの自習を促してください。

【応答ルール3：途中式の判定（採点モード）】
ユーザーが「この途中式は正しいか？」や「次のステップはこうですか？」という形で**具体的な式や手順**を提示した場合、あなたは**教師としてその式が正しいか間違っているかを判断**し、正しい場合は「その通りです。」と肯定し、間違っている場合は「残念ながら、ここが間違っています。もう一度確認しましょう。」と**間違いの場所や種類を具体的に指摘せずに**優しくフィードバックしてください。
"""

# -----------------------------------------------------
# --- 共通設定 ---
# -----------------------------------------------------
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5

# --- APIキーの読み込み ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit Cloudのシークレットを設定してください。")
    st.stop()

# -----------------------------------------------------
# --- 音声を自動再生するための関数 ---
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

        function writeString(view, offset, string) {{
            for (let i = 0; i < string.length; i++) {{
                view.setUint8(offset + i, string.charCodeAt(i));
            }}
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
    """Gemini TTSで音声生成＋自動再生"""
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
                try:
                    sample_rate = int(mime_type.split('rate=')[1])
                except IndexError:
                    sample_rate = 24000
                base64_to_audio_url(audio_data['data'], sample_rate)
                return True
            st.error("音声データを取得できませんでした。")
            return False
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            st.error(f"APIエラー: {e}")
            return False
        except Exception as e:
            st.error(f"予期せぬエラー: {e}")
            return False
    return False

# -----------------------------------------------------
# --- 音声入力UI（Web Speech API + text_input 経由） ---
# -----------------------------------------------------
def speech_to_text_ui():
    st.markdown("### 🎙️ 音声で質問する")
    text_input_key = "speech_text"
    # hidden text_input を経由して文字起こし
    st.text_input("文字起こし結果（非表示）", key=text_input_key, label_visibility="collapsed")

    html_code = f"""
    <script>
    let recognition;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {{
        recognition = new SpeechRecognition();
        recognition.lang = 'ja-JP';
        recognition.interimResults = false;
        recognition.continuous = false;

        function startRecognition() {{
            recognition.start();
        }}

        recognition.onresult = function(event) {{
            const transcript = event.results[0][0].transcript;
            // Streamlit の text_input に値をセット
            const inputElem = window.parent.document.querySelector('input[data-testid="stTextInput"][id^="widget-{text_input_key}"]');
            if (inputElem) {{
                inputElem.value = transcript;
                inputElem.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }};

        recognition.onerror = function(event) {{
            console.log('SpeechRecognition error:', event.error);
        }};
    }}
    </script>

    <button onclick="startRecognition()">🎤 話す / 停止</button>
    """
    components.html(html_code, height=80)

# -----------------------------------------------------
# --- Streamlitアプリ本体 ---
# -----------------------------------------------------
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー")
st.caption("私は対話型AIユッキーだよ。数学の問題など思考する問題の答えは教えないからね💕")

# Gemini初期化
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY)

if "chat" not in st.session_state:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model='gemini-2.5-flash', config=config)

USER_AVATAR = "🧑"
AI_AVATAR = "yukki-icon.jpg"

if "messages" not in st.session_state:
    st.session_state.messages = []

# 履歴表示
for message in st.session_state.messages:
    avatar_icon = USER_AVATAR if message["role"] == "user" else AI_AVATAR
    with st.chat_message(message["role"], avatar=avatar_icon):
        st.markdown(message["content"])

# 音声入力UI
speech_to_text_ui()

# --- ユーザー入力処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AI_AVATAR):
        with st.spinner("思考中..."):
            try:
                response = st.session_state.chat.send_message(prompt)
                response_text = response.text
                st.markdown(response_text)
                st.info("🔊 音声応答を準備中...")
                generate_and_play_tts(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            except Exception as e:
                st.error(f"APIエラーが発生しました: {e}")

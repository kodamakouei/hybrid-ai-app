import streamlit as st
from google import genai
import base64
import json
import time
import requests
import streamlit.components.v1 as components

# -----------------------------------------------------
# システムプロンプト
# -----------------------------------------------------
SYSTEM_PROMPT = """
あなたは教育的な目的を持つAIアシスタントです。
ユーザーの質問に対して3つのルールに従って応答してください。

1️⃣ 知識・定義は直接答える。
2️⃣ 思考・計算問題は答えを教えず、解法のヒントのみ。
3️⃣ 途中式を見せられた場合は正誤を判定し、優しく導く。
"""

# -----------------------------------------------------
# 共通設定
# -----------------------------------------------------
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit Cloudのシークレットを設定してください。")
    st.stop()

# -----------------------------------------------------
# 音声再生関数
# -----------------------------------------------------
@st.cache_data
def base64_to_audio_url(base64_data, sample_rate):
    js_code = f"""
    <script>
    function base64ToArrayBuffer(base64){{
        const binary_string = window.atob(base64);
        const len = binary_string.length;
        const bytes = new Uint8Array(len);
        for(let i=0;i<len;i++) bytes[i]=binary_string.charCodeAt(i);
        return bytes.buffer;
    }}
    function pcmToWav(pcmData, sampleRate){{
        const numChannels=1, bitsPerSample=16, bytesPerSample=bitsPerSample/8;
        const blockAlign=numChannels*bytesPerSample, byteRate=sampleRate*blockAlign;
        const dataSize=pcmData.byteLength;
        const buffer=new ArrayBuffer(44+dataSize);
        const view=new DataView(buffer);
        let offset=0;
        function writeString(v,o,s){{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i));}}
        writeString(view,offset,'RIFF'); offset+=4;
        view.setUint32(offset,36+dataSize,true); offset+=4;
        writeString(view,offset,'WAVE'); offset+=4;
        writeString(view,offset,'fmt '); offset+=4;
        view.setUint32(offset,16,true); offset+=4;
        view.setUint16(offset,1,true); offset+=2;
        view.setUint16(offset,numChannels,true); offset+=2;
        view.setUint32(offset,sampleRate,true); offset+=4;
        view.setUint32(offset,byteRate,true); offset+=4;
        view.setUint16(offset,blockAlign,true); offset+=2;
        view.setUint16(offset,bitsPerSample,true); offset+=2;
        writeString(view,offset,'data'); offset+=4;
        view.setUint32(offset,dataSize,true); offset+=4;
        const pcm16=new Int16Array(pcmData);
        for(let i=0;i<pcm16.length;i++){{view.setInt16(offset,pcm16[i],true); offset+=2;}}
        return new Blob([buffer],{{type:'audio/wav'}});
    }}
    const pcmData=base64ToArrayBuffer('{base64_data}');
    const wavBlob=pcmToWav(pcmData,{sample_rate});
    const audioUrl=URL.createObjectURL(wavBlob);
    const audio=new Audio(audioUrl);
    audio.play().catch(e=>console.log("Autoplay error:",e));
    </script>
    """
    components.html(js_code, height=0, width=0)

def generate_and_play_tts(text):
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":TTS_VOICE}}}
        },
        "model": TTS_MODEL
    }
    headers={'Content-Type':'application/json'}

    for _ in range(MAX_RETRIES):
        try:
            response=requests.post(f"{TTS_API_URL}?key={API_KEY}",headers=headers,data=json.dumps(payload))
            response.raise_for_status()
            result=response.json()
            audio_data=result["candidates"][0]["content"]["parts"][0].get("inlineData",{})
            if "data" in audio_data:
                mime_type=audio_data.get("mimeType","audio/L16;rate=24000")
                rate=int(mime_type.split("rate=")[1]) if "rate=" in mime_type else 24000
                base64_to_audio_url(audio_data["data"], rate)
                return
        except Exception as e:
            st.write("TTSエラー:", e)
            time.sleep(1)

# -----------------------------------------------------
# 音声認識コンポーネント
# -----------------------------------------------------
def speech_to_text_ui():
    st.markdown("### 🎤 話して質問（音声認識）")

    html_code = """
    <script>
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ja-JP';
        recognition.interimResults = false;
        recognition.continuous = false;

        function startRecognition() {
            document.getElementById('mic-status').innerText = '🎧 聴き取り中...';
            recognition.start();
        }

        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            document.getElementById('mic-status').innerText = '✅ 認識完了: ' + transcript;
            const streamlitInput = window.parent;
            streamlitInput.postMessage(
                { type: 'streamlit:setComponentValue', value: transcript },
                '*'
            );
        }

        recognition.onerror = function(event) {
            document.getElementById('mic-status').innerText = '⚠️ エラー: ' + event.error;
        }
    } else {
        document.getElementById('mic-status').innerText = 'このブラウザは音声認識に非対応です。';
    }
    </script>

    <button onclick="startRecognition()">🎙 話す</button>
    <p id="mic-status">マイク停止中</p>
    """
    result = components.html(html_code, height=120)
    return result

# -----------------------------------------------------
# Streamlit本体
# -----------------------------------------------------
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー")
st.caption("🎓 話しかけるだけで質問できるAIアシスタント")

# Gemini 初期化
if "client" not in st.session_state:
    st.session_state.client=genai.Client(api_key=API_KEY)
if "chat" not in st.session_state:
    config={"system_instruction":SYSTEM_PROMPT,"temperature":0.2}
    st.session_state.chat=st.session_state.client.chats.create(model='gemini-2.5-flash',config=config)

USER_AVATAR="🧑"
AI_AVATAR="yukki-icon.jpg"

if "messages" not in st.session_state:
    st.session_state.messages=[]

# 履歴表示
for msg in st.session_state.messages:
    avatar=USER_AVATAR if msg["role"]=="user" else AI_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# 音声認識からの入力
spoken_text = speech_to_text_ui()

# Chat入力
if prompt := st.chat_input("質問を入力してください...") or st.session_state.get("spoken_text"):
    if prompt:
        st.session_state.messages.append({"role":"user","content":prompt})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=AI_AVATAR):
            with st.spinner("考え中..."):
                try:
                    response = st.session_state.chat.send_message(prompt)
                    text = response.text
                    st.markdown(text)
                    st.info("🔊 音声出力中...")
                    generate_and_play_tts(text)
                    st.session_state.messages.append({"role":"assistant","content":text})
                except Exception as e:
                    st.error(f"エラー: {e}")

import streamlit as st
from google import genai
import base64, json, time, requests
import streamlit.components.v1 as components

# ===============================
# 設定
# ===============================
SYSTEM_PROMPT = """
あなたは教育的な目的を持つAIアシスタントです。
ユーザーの質問に対して3つのルールに従って応答してください。

1️⃣ 知識・定義は直接答える。
2️⃣ 思考・計算問題は答えを教えず、解法のヒントのみ。
3️⃣ 途中式を見せられた場合は正誤を判定し、優しく導く。
"""
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
API_KEY = st.secrets["GEMINI_API_KEY"]

# ===============================
# 音声再生
# ===============================
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
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}
        },
        "model": TTS_MODEL
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
    result = response.json()

    # ✅ 新しい構造に対応
    try:
        audio_data = result["contents"][0]["parts"][0]["inlineData"]
    except KeyError:
        st.error("❌ 音声データを取得できませんでした。レスポンスを確認してください。")
        st.json(result)
        return

    if "data" in audio_data:
        mime_type = audio_data.get("mimeType", "audio/L16;rate=24000")
        rate = int(mime_type.split("rate=")[1]) if "rate=" in mime_type else 24000
        base64_to_audio_url(audio_data["data"], rate)

# ===============================
# Streamlit UI
# ===============================

# ★★★ 修正箇所 1: アバターサイズを大きくするためのカスタムCSSを注入 ★★★
# CSSは、Streamlitのチャットメッセージ内の画像（アバター）をターゲットにサイズを64pxに固定します。
st.markdown("""
<style>
/* Chat Message Avatar Image (User and Assistant) */
div[data-testid="stChatMessage"] img {
    width: 10000px !important;
    height: 10000px !important;
    min-width: 10000px !important;
    min-height: 10000px !important;
    object-fit: cover !important; 
}
/* ユーザーアバター（絵文字）を大きく見せるための調整 */
div[data-testid="stChatMessage"] .st-emotion-cache-1f1f2x2 {
    font-size: 38px !important; 
}

</style>
""", unsafe_allow_html=True)
# ★★★ 修正箇所 1 終了 ★★★

st.set_page_config(page_title="ユッキー", layout="wide")
st.title("🎓 ユッキー（音声入力対応）")

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY)
if "chat" not in st.session_state:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)
if "messages" not in st.session_state:
    st.session_state.messages = []

# ===============================
# 音声入力ボタン（🎙話す→質問欄に入力＆自動送信）
# ===============================
components.html("""
<script>
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP';
    recognition.continuous = false;
    recognition.interimResults = false;

    function startRec() {
        document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
        recognition.start();
    }

    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        document.getElementById("mic-status").innerText = "✅ " + text;

        // Streamlitの質問欄（chat_input）を探す
        const chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (chatInput) {
            chatInput.value = text;
            chatInput.dispatchEvent(new Event('input', { bubbles: true }));

            // 🔥 自動で送信（Enterキーを押す）
            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
            chatInput.dispatchEvent(enterEvent);
        }
    };

    recognition.onerror = (e) => {
        document.getElementById("mic-status").innerText = "⚠️ " + e.error;
    };
} else {
    document.write("このブラウザは音声認識に対応していません。");
}
</script>
<button onclick="startRec()">🎙 話す</button>
<p id="mic-status">マイク停止中</p>
""", height=130)

# ===============================
# チャット画面
# ===============================
for msg in st.session_state.messages:
    avatar = "🧑" if msg["role"] == "user" else "yukki-icon.jpg"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="yukki-icon.jpg"):
        with st.spinner("考え中..."):
            response = st.session_state.chat.send_message(prompt)
            text = response.text
            st.markdown(text)
            st.info("🔊 音声出力中...")
            generate_and_play_tts(text)
            st.session_state.messages.append({"role": "assistant", "content": text})

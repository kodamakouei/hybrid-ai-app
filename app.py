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
あなたは教育的な目的を持つ AI アシスタントです。
ユーザーの質問に対して以下のルールに従ってできるだけかみ砕いてわかりやすく応答してく
ださい。
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
SIDEBAR_FIXED_WIDTH = "450px"
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (KeyError, AttributeError):
    API_KEY = ""
# ===============================
# アバター画像取得 (キャッシュ) - 口パクを廃止し、1枚の静止画のみをロード
# ===============================
@st.cache_data
def get_avatar_image():
    base_name = "yukki-static"
    extensions = [".jpg", ".jpeg", ".png"]
    for ext in extensions:
        file_name = base_name + ext
        if os.path.exists(file_name):
            with open(file_name, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
                prefix = f"data:image/{'jpeg' if ext in ['.jpg', '.jpeg'] else 'png'};base64,"
                return data, prefix, True
    placeholder_svg = base64.b64encode(
        f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="#f8e7ff"/>
        <text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-size="28" fill="#a00" font-family="sans-serif">❌画像なし</text>
        <text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">{base_name}.jpg/jpeg/png</text></svg>""".encode("utf-8")
    ).decode("utf-8")
    return placeholder_svg, "data:image/svg+xml;base64,", False

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
    headers = {"Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            r.raise_for_status()
            result = r.json()
            audio_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            st.session_state.audio_to_play = audio_data
            return
        except requests.exceptions.HTTPError as e:
            if r.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            break
        except Exception:
            break
    st.session_state.audio_to_play = None

st.set_page_config(page_title="ユッキー", layout="wide")

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
    margin: 0 auto;
}}
[data-testid="stSidebarContent"] {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    min-width: {SIDEBAR_FIXED_WIDTH} !important;
    max-width: {SIDEBAR_FIXED_WIDTH} !important;
}}
[data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
</style>
""", unsafe_allow_html=True)

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None
if "chat" not in st.session_state:
    st.session_state.chat = (st.session_state.client.chats.create(
        model="gemini-2.5-flash",
        config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    ) if st.session_state.client else None)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None

with st.sidebar:
    img_base64, data_uri_prefix, has_image = get_avatar_image()
    if not has_image:
        st.warning("アバター画像がありません。")
    st.markdown(f"""
    <img id="avatar" src="{data_uri_prefix}{img_base64}" class="avatar">
    """, unsafe_allow_html=True)

    if st.session_state.audio_to_play:
        # 音声のみ再生（口パク関連JS削除）
        js_code = f"""
        <script>
        function base64ToArrayBuffer(base64) {{
            const bin = window.atob(base64);
            const len = bin.length;
            const bytes = new Uint8Array(len);
            for (let i=0;i<len;i++) bytes[i]=bin.charCodeAt(i);
            return bytes.buffer;
        }}
        function writeString(view, offset, string) {{
            for (let i=0;i<string.length;i++) view.setUint8(offset+i, string.charCodeAt(i));
        }}
        function pcmToWav(pcmData, sampleRate) {{
            const numChannels=1, bitsPerSample=16;
            const bytesPerSample=bitsPerSample/8;
            const blockAlign=numChannels*bytesPerSample;
            const byteRate=sampleRate*blockAlign;
            const dataSize=pcmData.byteLength;
            const buffer=new ArrayBuffer(44+dataSize);
            const view=new DataView(buffer);
            let o=0;
            writeString(view,o,'RIFF'); o+=4;
            view.setUint32(o,36+dataSize,true); o+=4;
            writeString(view,o,'WAVE'); o+=4;
            writeString(view,o,'fmt '); o+=4;
            view.setUint32(o,16,true); o+=4;
            view.setUint16(o,1,true); o+=2;
            view.setUint16(o,numChannels,true); o+=2;
            view.setUint32(o,sampleRate,true); o+=4;
            view.setUint32(o,byteRate,true); o+=4;
            view.setUint16(o,blockAlign,true); o+=2;
            view.setUint16(o,bitsPerSample,true); o+=2;
            writeString(view,o,'data'); o+=4;
            view.setUint32(o,dataSize,true); o+=4;
            const pcm16=new Int16Array(pcmData);
            for (let i=0;i<pcm16.length;i++) {{ view.setInt16(o,pcm16[i],true); o+=2; }}
            return new Blob([buffer],{{type:'audio/wav'}});
        }}
        const base64Audio='{st.session_state.audio_to_play}';
        const sampleRate=24000;
        const pcm=base64ToArrayBuffer(base64Audio);
        const wavBlob=pcmToWav(pcm,sampleRate);
        const url=URL.createObjectURL(wavBlob);
        const audio=new Audio(url);
        audio.autoplay=true;
        audio.onended=()=>URL.revokeObjectURL(url);
        audio.play().catch(()=>URL.revokeObjectURL(url));
        </script>
        """
        components.html(js_code, height=0, width=0)
        st.session_state.audio_to_play = None

st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考はヒントのみ。")

st.subheader("音声入力")
components.html("""
<div id="mic-container" style="padding:10px 0;">
  <button onclick="window.parent.startRec()" style="background:#ff69b4;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:16px;">
    🎙 話す
  </button>
  <p id="mic-status" style="margin-top:10px;">マイク停止中</p>
</div>
<script>
function sendTextToStreamlit(text){
  window.parent.postMessage({type:'SET_CHAT_INPUT',text:text},'*');
}
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec;
if (SR){
  rec = new SR();
  rec.lang='ja-JP'; rec.continuous=false; rec.interimResults=false;
  window.parent.startRec = ()=>{ document.getElementById('mic-status').innerText='🎧 聴き取り中...'; rec.start(); };
  rec.onresult = e => {
    const t = e.results[0][0].transcript;
    document.getElementById('mic-status').innerText='✅ '+t;
    sendTextToStreamlit(t);
  };
  rec.onerror = e => { document.getElementById('mic-status').innerText='⚠️ '+e.error; };
  rec.onend = ()=>{ if (document.getElementById('mic-status').innerText.startsWith('🎧')) document.getElementById('mic-status').innerText='マイク停止中'; };
}else{
  document.getElementById('mic-container').innerHTML='ブラウザが音声認識非対応';
}
</script>
""", height=130)

st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("生成中..."):
            if st.session_state.chat:
                try:
                    resp = st.session_state.chat.send_message(prompt)
                    text = resp.text
                    st.markdown(text)
                    generate_and_store_tts(text)
                    st.session_state.messages.append({"role": "assistant", "content": text})
                except Exception as e:
                    err = f"APIエラー: {e}"
                    st.error(err)
                    st.session_state.messages.append({"role": "assistant", "content": err})
            else:
                msg = "APIキー未設定です。"
                st.markdown(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
    st.rerun()

components.html("""
<script>
window.addEventListener('message', e => {
  if (e.data.type === 'SET_CHAT_INPUT'){
    const ta = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
    if (ta){
      ta.value = e.data.text;
      ta.dispatchEvent(new Event('input',{bubbles:true}));
      ta.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,keyCode:13}));
    }
  }
});
</script>
""", height=0)
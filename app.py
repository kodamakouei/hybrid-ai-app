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
あなたは、教育的な目的を持つ高度なAIアシスタントです。ユーザーの質問に対し、以下の厳格な3つのルールに従って応答してください。

【応答ルール1：事実・知識の質問（直接回答）】
質問が、確定した事実、固有名詞、定義、単純な知識を尋ねるものである場合、その答えを直接、かつ簡潔に回答してください。

【応答ルール2：計算・思考・問題解決】
最終的な答えや途中式は絶対に教えないでください。最初の重要な解法ステップや必要な公式のヒントを教えて自習を促してください。

【応答ルール3：途中式の判定】
ユーザーが途中式や手順を提示した場合、正誤を判定し、間違っていれば優しく再確認を促してください。
"""

# -----------------------------------------------------
# 共通設定
# -----------------------------------------------------
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5

# APIキー
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit Cloudのシークレットを設定してください。")
    st.stop()

# -----------------------------------------------------
# TTS生成関数
# -----------------------------------------------------
@st.cache_data
def base64_to_audio_url(base64_data, sample_rate):
    js_code = f"""
    <script>
    function base64ToArrayBuffer(base64) {{
        const binary_string = window.atob(base64);
        const len = binary_string.length;
        const bytes = new Uint8Array(len);
        for (let i=0;i<len;i++) bytes[i]=binary_string.charCodeAt(i);
        return bytes.buffer;
    }}
    function pcmToWav(pcmData, sampleRate) {{
        const numChannels=1, bitsPerSample=16, bytesPerSample=bitsPerSample/8;
        const blockAlign=numChannels*bytesPerSample, byteRate=sampleRate*blockAlign;
        const dataSize=pcmData.byteLength;
        const buffer=new ArrayBuffer(44+dataSize);
        const view=new DataView(buffer);
        let offset=0;
        function writeString(view, offset, string) {{for(let i=0;i<string.length;i++) view.setUint8(offset+i,string.charCodeAt(i));}}
        writeString(view, offset, 'RIFF'); offset+=4;
        view.setUint32(offset,36+dataSize,true); offset+=4;
        writeString(view, offset,'WAVE'); offset+=4;
        writeString(view, offset,'fmt '); offset+=4;
        view.setUint32(offset,16,true); offset+=4;
        view.setUint16(offset,1,true); offset+=2;
        view.setUint16(offset,numChannels,true); offset+=2;
        view.setUint32(offset,sampleRate,true); offset+=4;
        view.setUint32(offset,byteRate,true); offset+=4;
        view.setUint16(offset,blockAlign,true); offset+=2;
        view.setUint16(offset,bitsPerSample,true); offset+=2;
        writeString(view, offset,'data'); offset+=4;
        view.setUint32(offset,dataSize,true); offset+=4;
        const pcm16=new Int16Array(pcmData);
        for(let i=0;i<pcm16.length;i++) {{
            view.setInt16(offset,pcm16[i],true);
            offset+=2;
        }}
        return new Blob([buffer], {{ type:'audio/wav' }});
    }}
    const pcmData=base64ToArrayBuffer('{base64_data}');
    const wavBlob=pcmToWav(pcmData,{sample_rate});
    const audioUrl=URL.createObjectURL(wavBlob);
    const audio=new Audio(audioUrl);
    audio.play().catch(e=>console.log("Audio autoplay failed:",e));
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

    for attempt in range(MAX_RETRIES):
        try:
            response=requests.post(f"{TTS_API_URL}?key={API_KEY}",headers=headers,data=json.dumps(payload))
            response.raise_for_status()
            result=response.json()
            candidate=result.get('candidates',[{}])[0]
            part=candidate.get('content',{}).get('parts',[{}])[0]
            audio_data=part.get('inlineData',{})
            if audio_data and audio_data.get('data'):
                mime_type=audio_data.get('mimeType','audio/L16;rate=24000')
                try:
                    sample_rate=int(mime_type.split('rate=')[1])
                except:
                    sample_rate=24000
                base64_to_audio_url(audio_data['data'],sample_rate)
                return True
            st.error("音声データを取得できませんでした。")
            return False
        except:
            time.sleep(1)
    return False

# -----------------------------------------------------
# 音声入力UI（chat_input 自動送信対応）
# -----------------------------------------------------
def speech_to_text_ui():
    st.markdown("### 🎙️ 音声で質問する")
    html_code=f"""
    <script>
    let recognizing=false;
    let recognition;
    const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;

    if(SpeechRecognition){{
        recognition=new SpeechRecognition();
        recognition.lang='ja-JP';
        recognition.interimResults=false;
        recognition.continuous=false;

        function toggleRecognition(){{
            if(recognizing){{
                recognition.stop();
                recognizing=false;
                document.getElementById('mic-status').innerText='マイク停止中';
            }}else{{
                recognition.start();
                recognizing=true;
                document.getElementById('mic-status').innerText='🎧 聴き取り中...';
            }}
        }}

        recognition.onresult=function(event){{
            const transcript=event.results[0][0].transcript;
            // chat_input に自動入力
            const chatInput=window.parent.document.querySelector('input[data-testid="stChatInput"]');
            if(chatInput){{
                chatInput.value=transcript;
                const enterEvent=new KeyboardEvent('keydown',{{key:'Enter',bubbles:true}});
                chatInput.dispatchEvent(enterEvent);
            }}
            document.getElementById('mic-status').innerText='✅ 認識完了: '+transcript;
            recognizing=false;
        }}

        recognition.onerror=function(event){{
            console.log('SpeechRecognition error:',event.error);
            document.getElementById('mic-status').innerText='⚠️ エラー: '+event.error;
            recognizing=false;
        }}
    }}else{{
        document.getElementById('mic-status').innerText='このブラウザは音声認識をサポートしていません。';
    }}
    </script>

    <button onclick="toggleRecognition()">🎤 話す / 停止</button>
    <p id="mic-status">マイク停止中</p>
    """
    components.html(html_code,height=100)

# -----------------------------------------------------
# Streamlit 本体
# -----------------------------------------------------
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー")
st.caption("私は対話型AIユッキーだよ。数学の問題など思考する問題の答えは教えないからね💕")

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

# 音声入力UI
speech_to_text_ui()

# chat_input 処理
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role":"user","content":prompt})
    with st.chat_message("user",avatar=USER_AVATAR):
        st.markdown(prompt)
    with st.chat_message("assistant",avatar=AI_AVATAR):
        with st.spinner("思考中..."):
            try:
                response=st.session_state.chat.send_message(prompt)
                response_text=response.text
                st.markdown(response_text)
                st.info("🔊 音声応答を準備中...")
                generate_and_play_tts(response_text)
                st.session_state.messages.append({"role":"assistant","content":response_text})
            except Exception as e:
                st.error(f"APIエラー: {e}")

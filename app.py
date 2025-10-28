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
"""
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore" # 音声モデル（男性的な声）
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""
 
# ===============================
# アバター画像取得 (キャッシュ)
# *技術的制約により、任意の動画ファイル（.mp4など）をリアルタイムTTSと同期させることは困難です。
# *そのため、本アプリでは2枚の画像切替によるアニメーションを採用しています。
# ===============================
@st.cache_data
def get_avatar_images():
    loaded_images = {}
    
    # ユーザーが特定の画像（yukki-closed.jpg, yukki-open.jpg）をアップロードすればそれを優先的に使用できますが、
    # 確実な動作のため、ここでは常に動作するダミーのBase64 SVG画像を使用します。
    
    # 口閉じの画像 (青色のプレースホルダー)
    closed_svg = f"""<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg"><rect width="200" height="200" fill="#4a90e2"/><text x="100" y="100" font-size="20" fill="white" text-anchor="middle" dominant-baseline="middle">Yukki (閉)</text></svg>"""
    loaded_images["closed"] = "data:image/svg+xml;base64," + base64.b64encode(closed_svg.encode('utf-8')).decode('utf-8')

    # 口開きの画像 (緑色のプレースホルダー)
    open_svg = f"""<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg"><rect width="200" height="200" fill="#32a852"/><text x="100" y="100" font-size="20" fill="white" text-anchor="middle" dominant-baseline="middle">Yukki (開)</text></svg>"""
    loaded_images["open"] = "data:image/svg+xml;base64," + base64.b64encode(open_svg.encode('utf-8')).decode('utf-8')
    
    return loaded_images

# ===============================
# TTS処理（音声生成とセッションステート保存）
# ===============================
def generate_and_store_tts(text):
    """テキストからTTSデータを生成し、セッションステートに保存する"""
    if not API_KEY:
        st.session_state.tts_data = None
        return

    # 指数バックオフを用いたAPI呼び出し
    MAX_RETRIES = 3
    RETRY_DELAY = 1

    for attempt in range(MAX_RETRIES):
        payload = {
            "contents": [{
                "parts": [{"text": text}]
            }],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": TTS_VOICE}
                    }
                }
            },
            "model": TTS_MODEL
        }

        headers = {'Content-Type': 'application/json'}
        params = {'key': API_KEY}
        
        try:
            response = requests.post(TTS_API_URL, headers=headers, params=params, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            audio_part = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0]
            audio_data = audio_part.get('inlineData', {}).get('data')
            mime_type = audio_part.get('inlineData', {}).get('mimeType')
            
            if audio_data and mime_type:
                st.session_state.tts_data = {
                    "audio_data": audio_data,
                    "mime_type": mime_type
                }
                return # 成功したら終了
            else:
                st.session_state.tts_data = None
                st.error("TTS応答から音声データが取得できませんでした。")
                return # 失敗したら終了 (リトライ対象外)

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                st.error(f"TTS APIエラー: {e}")
                st.session_state.tts_data = None


# ===============================
# TTSオーディオプレイヤーとアニメーションUI
# ===============================
def talking_avatar_ui(images):
    """TTSデータと連動してアニメーションするアバターとオーディオプレイヤーを配置する"""
    
    if not images:
        return
    
    # HTML/JavaScriptを記述
    html_content = f"""
    <style>
        .avatar-container {{
            text-align: center;
            padding: 1rem;
            border-radius: 12px;
            background-color: #f0f2f6;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        #avatar-image {{
            width: 150px;
            height: 150px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid #4a90e2;
            transition: transform 0.1s ease;
        }}
        #audio-player {{
            display: none; /* プレイヤー自体は非表示 */
        }}
        .status-text {{
            margin-top: 0.5rem;
            font-size: 1rem;
            color: #333;
        }}
    </style>
    <div class="avatar-container">
        <img id="avatar-image" src="{images['closed']}" alt="Yukki Avatar">
        <div class="status-text" id="status-text">準備完了</div>
        <audio id="audio-player" controls preload="auto"></audio>
    </div>

    <script>
        const audioPlayer = document.getElementById('audio-player');
        const avatarImage = document.getElementById('avatar-image');
        const statusText = document.getElementById('status-text');
        const closedImgSrc = "{images['closed']}";
        const openImgSrc = "{images['open']}";
        let animationInterval = null;

        // PCMデータをWAVに変換するヘルパー関数群
        function base64ToArrayBuffer(base64) {{
            const binaryString = window.atob(base64);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{
                bytes[i] = binaryString.charCodeAt(i);
            }}
            return bytes.buffer;
        }}

        function pcmToWav(pcm16, sampleRate) {{
            const pcmData = pcm16.buffer;
            const numChannels = 1;
            const bytesPerSample = 2; // Int16
            const blockAlign = numChannels * bytesPerSample;
            const byteRate = sampleRate * blockAlign;
            const dataSize = pcmData.byteLength;
            const chunkSize = 36 + dataSize;

            const buffer = new ArrayBuffer(44 + dataSize);
            const view = new DataView(buffer);

            let offset = 0;

            // RIFF chunk
            function writeString(s) {{
                for (let i = 0; i < s.length; i++) {{
                    view.setUint8(offset++, s.charCodeAt(i));
                }}
            }}

            writeString('RIFF'); // Chunk ID
            view.setUint32(offset, chunkSize, true); offset += 4; // Chunk size
            writeString('WAVE'); offset += 4; // Format

            // FMT sub-chunk
            writeString('fmt '); offset += 4; // Sub-chunk 1 ID
            view.setUint32(offset, 16, true); offset += 4; // Sub-chunk 1 size (16 for PCM)
            view.setUint16(offset, 1, true); offset += 2; // Audio format (1 for PCM)
            view.setUint16(offset, numChannels, true); offset += 2; // Number of channels
            view.setUint32(offset, sampleRate, true); offset += 4; // Sample rate
            view.setUint32(offset, byteRate, true); offset += 4; // Byte rate
            view.setUint16(offset, blockAlign, true); offset += 2; // Block align
            view.setUint16(offset, 16, true); offset += 2; // Bits per sample (16 bit)

            // DATA sub-chunk
            writeString('data'); offset += 4; // Sub-chunk 2 ID
            view.setUint32(offset, dataSize, true); offset += 4; // Sub-chunk 2 size

            // PCM data
            const pcmView = new Int16Array(pcmData);
            for (let i = 0; i < pcmView.length; i++) {{
                view.setInt16(offset, pcmView[i], true); offset += 2;
            }}

            return new Blob([view], {{ type: 'audio/wav' }});
        }}
        
        // アニメーション制御
        function startAnimation() {{
            let isOpen = true;
            statusText.textContent = "ユッキーが話しています...";
            avatarImage.style.transform = 'scale(1.05)'; // 話し始めに少し拡大

            animationInterval = setInterval(() => {{
                if (isOpen) {{
                    avatarImage.src = openImgSrc;
                }} else {{
                    avatarImage.src = closedImgSrc;
                }}
                isOpen = !isOpen;
            }}, 120); // 120msごとに画像を切り替える

            audioPlayer.play();
        }}

        function stopAnimation() {{
            clearInterval(animationInterval);
            animationInterval = null;
            avatarImage.src = closedImgSrc;
            statusText.textContent = "準備完了";
            avatarImage.style.transform = 'scale(1.0)';
        }}

        // イベントリスナー
        audioPlayer.onplay = startAnimation;
        audioPlayer.onended = stopAnimation;
        audioPlayer.onerror = function() {{
            console.error("Audio playback error.");
            stopAnimation();
        }};
        
        // Streamlitからのメッセージを受信し、音声を再生
        window.addEventListener('message', event => {{
            if (event.data.type === 'PLAY_TTS' && event.data.audioBase64) {{
                const audioData = event.data.audioBase64;
                const mimeType = event.data.mimeType || 'audio/L16;rate=24000';
                
                // MIMEタイプからサンプリングレートを抽出
                const rateMatch = mimeType.match(/rate=(\d+)/);
                const sampleRate = rateMatch ? parseInt(rateMatch[1], 10) : 24000;
                
                // PCM16データをWAV形式に変換
                const pcmData = base64ToArrayBuffer(audioData);
                const pcm16 = new Int16Array(pcmData);
                const wavBlob = pcmToWav(pcm16, sampleRate);
                
                // Blob URLを作成し、Audio要素に設定
                const audioUrl = URL.createObjectURL(wavBlob);
                audioPlayer.src = audioUrl;
                
                // 再生開始（onplayイベントでアニメーションが開始される）
                // audioPlayer.load(); // 不要な場合が多い
                audioPlayer.play().catch(e => console.error("Auto-play failed:", e));
            }}
        }});
    </script>
    """
    
    # UIコンポーネントとして表示
    components.html(html_content, height=200)

# ===============================
# メイン処理
# ===============================
st.set_page_config(page_title="ユッキー先生", layout="wide")

# タイトルと説明
st.title("🤖 ユッキー先生：音声連動AIアシスタント")
st.markdown("質問を入力または音声で話しかけてください。ユッキーが音声とアニメーションで応答します。")

# アバター画像のロード
avatar_images = get_avatar_images()

# --- TTSアニメーションUIの配置 ---
talking_avatar_ui(avatar_images)

# --- Streamlitセッション状態の初期化 ---
if "client" not in st.session_state:
    if API_KEY:
        # APIキーが空でない場合はクライアントを初期化
        st.session_state.client = genai.Client(api_key=API_KEY)
    else:
        st.error("Gemini APIキーが設定されていません。")

if "chat" not in st.session_state and API_KEY:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model='gemini-2.5-flash', config=config)

if "messages" not in st.session_state:
    st.session_state.messages = []

# TTS再生フラグの初期化
if 'tts_data' not in st.session_state:
    st.session_state.tts_data = None
    
# --- 音声認識UIの配置 ---
# (音声認識UIは前回のものをそのまま使用します)
speech_to_text_html = """
<div id="mic-container" style="text-align: center; margin-top: 10px;">
    <button id="mic-button" style="padding: 10px 20px; font-size: 16px; background-color: #4a90e2; color: white; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px #2a70c2;">
        🎙️ 音声入力開始
    </button>
</div>

<script>
const micButton = document.getElementById('mic-button');
const micContainer = document.getElementById('mic-container');
let recognition = null;

if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false; // 発話の度に停止
    recognition.lang = 'ja-JP';

    micButton.onclick = () => {
        if (recognition) {
            micButton.textContent = '🔴 録音中...';
            micButton.style.backgroundColor = '#d9534f';
            micButton.style.boxShadow = '0 4px #a03c39';
            recognition.start();
        }
    };

    recognition.onresult = (event) => {
        const result = event.results[0][0].transcript;
        // Streamlitのチャット入力欄にテキストを送信
        window.parent.postMessage({
            type: 'SET_CHAT_INPUT',
            text: result
        }, '*');
    };

    recognition.onend = () => {
        micButton.textContent = '🎙️ 音声入力開始';
        micButton.style.backgroundColor = '#4a90e2';
        micButton.style.boxShadow = '0 4px #2a70c2';
    };

    recognition.onerror = (event) => {
        micButton.textContent = 'エラー: ' + event.error;
        micButton.style.backgroundColor = '#f0ad4e';
        micButton.style.boxShadow = '0 4px #d49a3e';
    };

} else {
    micContainer.innerHTML = "<p style='color:red;'>このブラウザは音声認識に対応していません。</p>";
}
</script>
"""
components.html(speech_to_text_html, height=100)

st.subheader("ユッキーとの会話履歴")

# --- 会話履歴表示 ---
for msg in st.session_state.messages:
    # アバターのアイコンは固定
    avatar = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
 
# --- チャット入力と処理 --
if prompt := st.chat_input("質問を入力してください..."):
    # ユーザーメッセージの追加
    st.session_state.messages.append({"role": "user", "content": prompt})
    # ユーザーメッセージの表示
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # アシスタントの応答生成
    if st.session_state.get("chat"):
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("思考中..."):
                response = st.session_state.chat.send_message(prompt)
                text = response.text
                st.markdown(text)
            
            # アシスタントメッセージの追加
            st.session_state.messages.append({"role": "assistant", "content": text})
            
            # 音声データを生成してセッションステートに保存
            generate_and_store_tts(text)
            
    else:
        st.session_state.messages.append({"role": "assistant", "content": "APIキーが設定されていないため、お答えできません。"})
    
    st.rerun()

# --- 音声認識からチャット入力へテキストを転送するJavaScript ---
components.html("""
<script>
window.addEventListener('message', event => {
    if (event.data.type === 'SET_CHAT_INPUT') {
        // Streamlitのチャット入力要素を見つけて値を設定する
        const chatInput = window.parent.document.querySelector('input[placeholder="質問を入力してください..."]');
        if (chatInput) {
            chatInput.value = event.data.text;
            
            // エンターキーイベントを発火させて入力を確定させる
            const event = new KeyboardEvent('keydown', {
                key: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true
            });
            chatInput.dispatchEvent(event);
        }
    }
});
</script>
""", height=0)


# --- TTS再生トリガー ---
if st.session_state.get('tts_data'):
    # JavaScriptにメッセージをポストして再生をトリガー
    js_trigger = f"""
    <script>
    const ttsData = {{
        type: 'PLAY_TTS',
        audioBase64: '{st.session_state['tts_data']['audio_data']}',
        mimeType: '{st.session_state['tts_data']['mime_type']}'
    }};
    
    // アニメーションUIをホストしているiframeにメッセージを送信
    const iframes = window.parent.document.querySelectorAll('iframe');
    iframes.forEach(iframe => {{
        iframe.contentWindow.postMessage(ttsData, '*');
    }});
    </script>
    """
    components.html(js_trigger, height=0)
    
    # セッションステートからデータをクリアして、再実行を防ぐ
    del st.session_state['tts_data']

# アバター画像がない場合のエラーを最後に表示 (今回はダミー画像で回避済み)
if not avatar_images:
    st.error("アバター画像を正しく設定するか、アップロードしてください。")

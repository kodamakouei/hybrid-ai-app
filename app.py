import streamlit as st
from google import genai
import os
import base64
import json
import time # 指数バックオフのためにインポート
import requests # APIコールのためにインポート
import streamlit.components.v1 as components

# -----------------------------------------------------
# 【システム指示】教育的ハイブリッドAIのルール
# ... (SYSTEM_PROMPT の定義は変更なし) ...
# -----------------------------------------------------
SYSTEM_PROMPT = """
あなたは、教育的な目的を持つ高度なAIアシスタントです。ユーザーの質問に対し、以下の厳格な3つのルールに従って応答してください。

【応答ルール1：事実・知識の質問（直接回答）】
質問が、**確定した事実**、**固有名詞**、**定義**、**単純な知識**を尋ねるものである場合、**その答えを直接、かつ簡潔な名詞または名詞句で回答してください**。

【応答ルール2：計算・思考・問題解決の質問（解法ガイド）】
質問が、**計算**、**分析**、**プログラミング**、**論理的な思考**を尋ねるものである場合、**最終的な答えや途中式は絶対に教えないでください**。代わりに、ユーザーが次に取るべき**最初の、最も重要な解法のステップ**や**必要な公式のヒント**を教えることで、ユーザーの自習を促してください。
例：「積分の問題」→「まずは部分分数分解を行うと良いでしょう。」

【応答ルール3：途中式の判定（採点モード）】
ユーザーが「この途中式は正しいか？」や「次のステップはこうですか？」という形で**具体的な式や手順**を提示した場合、あなたは**教師としてその式が正しいか間違っているかを判断**し、正しい場合は「その通りです。」と肯定し、間違っている場合は「残念ながら、ここが間違っています。もう一度確認しましょう。」と**間違いの場所や種類を具体的に指摘せずに**優しくフィードバックしてください。
"""
# -----------------------------------------------------

# --- 共通設定 ---
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore" # 明瞭な声を選択
MAX_RETRIES = 5

# StreamlitのシークレットからAPIキーを読み込む
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit Cloudのシークレットを設定してください。")
    st.stop()

# --- TTS（Text-to-Speech）処理関数 ---

@st.cache_data
def base64_to_audio_url(base64_data, sample_rate):
    """
    Base64エンコードされたPCMオーディオデータをWAVファイルに変換し、再生可能なURLを返すためのJavaScriptを生成する。
    """
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

            // RIFF chunk descriptor
            writeString(view, offset, 'RIFF'); offset += 4;
            view.setUint32(offset, 36 + dataSize, true); offset += 4;
            writeString(view, offset, 'WAVE'); offset += 4;

            // FMT sub-chunk
            writeString(view, offset, 'fmt '); offset += 4;
            view.setUint32(offset, 16, true); offset += 4; // Sub-chunk size (16 for PCM)
            view.setUint16(offset, 1, true); offset += 2; // Audio format (1 for PCM)
            view.setUint16(offset, numChannels, true); offset += 2;
            view.setUint32(offset, sampleRate, true); offset += 4;
            view.setUint32(offset, byteRate, true); offset += 4;
            view.setUint16(offset, blockAlign, true); offset += 2;
            view.setUint16(offset, bitsPerSample, true); offset += 2;

            // DATA sub-chunk
            writeString(view, offset, 'data'); offset += 4;
            view.setUint32(offset, dataSize, true); offset += 4;

            // Write PCM data (Int16 to DataView)
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

        // メイン処理の実行
        const pcmData = base64ToArrayBuffer('{base64_data}');
        const wavBlob = pcmToWav(pcmData, {sample_rate});
        const audioUrl = URL.createObjectURL(wavBlob);
        
        // 再生エレメントを作成し、自動再生
        const audio = new Audio(audioUrl);
        // autoplayが動作しないブラウザもあるため、setTimeoutで手動再生を試みる
        audio.play().catch(e => console.log("Audio autoplay failed:", e));
        
    </script>
    """
    # StreamlitでJavaScriptを直接実行する
    components.html(js_code, height=0, width=0)

def generate_and_play_tts(text):
    """テキストから音声を生成し、自動再生する"""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
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
    
    # 指数バックオフを実装したAPIコール
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                f"{TTS_API_URL}?key={API_KEY}", 
                headers=headers, 
                data=json.dumps(payload)
            )
            response.raise_for_status()
            
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            part = candidate.get('content', {}).get('parts', [{}])[0]
            audio_data = part.get('inlineData', {})
            
            if audio_data and audio_data.get('data'):
                # APIから返されるMIMEタイプからサンプリングレートを抽出
                mime_type = audio_data.get('mimeType', 'audio/L16;rate=24000')
                try:
                    sample_rate = int(mime_type.split('rate=')[1])
                except IndexError:
                    sample_rate = 24000 # デフォルト値
                
                # WAVに変換して自動再生するためのJavaScriptを埋め込む
                base64_to_audio_url(audio_data['data'], sample_rate)
                return True

            st.error("AIからの音声データが取得できませんでした。")
            return False

        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            st.error(f"APIエラーが発生しました: {e}. ステータスコード: {response.status_code}")
            return False
        except Exception as e:
            st.error(f"予期せぬエラーが発生しました: {e}")
            return False
    return False


# --- 1. アプリケーションの初期設定 ---
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー")
st.caption("私は対話型AIユッキーだよ。数学の問題など思考する問題の答えは教えないからね💕")

# --- 2. クライアントとセッションの初期化（記憶力の確保） ---
# ... (Geminiクライアントとチャットセッションの初期化は変更なし)
if "client" not in st.session_state:
    try:
        st.session_state.client = genai.Client(api_key=API_KEY)
    except Exception as e:
        st.error(f"Geminiクライアントの初期化に失敗しました: {e}")
        st.stop()

if "chat" not in st.session_state:
    config = {
        "system_instruction": SYSTEM_PROMPT, 
        "temperature": 0.2, 
    }
    st.session_state.chat = st.session_state.client.chats.create(
        model='gemini-2.5-flash', 
        config=config
    )

# アバターの定義
USER_AVATAR = "🧑"  
AI_AVATAR = "yukki-icon.jpg" 

# --- 3. チャット履歴の表示 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# 履歴をすべて表示
for message in st.session_state.messages:
    # 役割に応じてアイコンを切り替え、適用
    avatar_icon = USER_AVATAR if message["role"] == "user" else AI_AVATAR
    with st.chat_message(message["role"], avatar=avatar_icon):
        st.markdown(message["content"])
        
# --- 4. ユーザー入力の処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    # ユーザーのメッセージを履歴に追加
    st.session_state.messages.append({"role": "user", "content": prompt})

    # ユーザーメッセージにアイコンを適用
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    # AIに応答を送信
    with st.chat_message("assistant", avatar=AI_AVATAR):
        with st.spinner("思考中..."):
            try:
                # 記憶のあるチャットセッションを使用
                response = st.session_state.chat.send_message(prompt)
                response_text = response.text
                
                # 応答を画面に表示
                st.markdown(response_text)
                
                # ★修正箇所: 音声を生成し、自動再生
                st.info("🔊 音声応答を準備中...")
                if generate_and_play_tts(response_text):
                    st.empty() # 成功したらメッセージを消す
                else:
                    st.error("音声生成に失敗しました。")


                # AIの応答を履歴に追加
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            except Exception as e:
                st.error(f"APIエラーが発生しました: {e}")

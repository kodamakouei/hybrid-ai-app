import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components
import os
import uuid

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
try:
    API_KEY = st.secrets["GEMINI_API_KEY"] 
except:
    API_KEY = ""

# ===============================
# アバター画像取得 (キャッシュ)
# ===============================
@st.cache_data
def get_avatar_images():
    base_names = ["yukki-close", "yukki-open"]
    extensions = [".jpg", ".jpeg"]
    loaded_images = {}
    data_uri_prefix = ""

    for base in base_names:
        for ext in extensions:
            file_name = base + ext
            try:
                with open(file_name, "rb") as f:
                    loaded_images[base] = base64.b64encode(f.read()).decode("utf-8")
                    data_uri_prefix = f"data:image/{'jpeg' if ext in ['.jpg', '.jpeg'] else 'png'};base64,"
                    break
            except FileNotFoundError:
                continue

    if "yukki-close" in loaded_images and "yukki-open" in loaded_images:
        return loaded_images["yukki-close"], loaded_images["yukki-open"], data_uri_prefix, True
    else:
        st.sidebar.warning("⚠️ アバター画像ファイルが見つかりません。")
        placeholder_svg = base64.b64encode(
            f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">❌画像なし</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        return placeholder_svg, placeholder_svg, "data:image/svg+xml;base64,", False

# ===============================
# 音声データを生成し、Session Stateに保存する関数
# ===============================
def generate_and_store_tts(text):
    if not API_KEY:
        return
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"]},
        "model": TTS_MODEL
    }
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        audio_data_base64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        st.session_state.audio_to_play = audio_data_base64
    except Exception as e:
        st.error(f"❌ 音声データ取得に失敗しました。詳細: {e}")

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")

# --- セッションステートの初期化 ---
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None
# チャットセッションは後から作成するので、ここではNoneで初期化
if "chat" not in st.session_state:
    st.session_state.chat = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None
if "processing" not in st.session_state:
    st.session_state.processing = False

# --- サイドバー ---
with st.sidebar:
// ...existing code...
if voice_prompt:
    prompt = voice_prompt

# --- プロンプト処理とAPI呼び出し ---
if prompt and not st.session_state.processing:
    st.session_state.processing = True

    # ユーザーのメッセージを履歴に追加して表示
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # AIの応答を処理
    if st.session_state.client:
        try:
            # チャットセッションがまだなければ、ここで作成する
            if "chat" not in st.session_state or st.session_state.chat is None:
                config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
                st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)

            response = st.session_state.chat.send_message(prompt)
            text = response.text
            st.session_state.messages.append({"role": "assistant", "content": text})
            generate_and_store_tts(text)
        except Exception as e:
            error_message = f"API呼び出し中にエラーが発生しました: {e}"
            st.error(error_message)
            st.session_state.messages.append({"role": "assistant", "content": error_message})
    else:
        st.session_state.messages.append({"role": "assistant", "content": "APIキーが設定されていないため、お答えできません。"})
    
    # 処理完了後、フラグをリセットして再実行
    st.session_state.processing = False
    st.rerun()
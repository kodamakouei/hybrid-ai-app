import streamlit as st
from google import genai
import base64
import json
import requests
import streamlit.components.v1 as components
import os
import time
from google.genai.types import Part

# =========================================
#  システムプロンプト
# =========================================
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

# =========================================
# APIキー読み込みとサイドバー幅設定
# =========================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""

# サイドバーの推奨幅（ファイルアップローダーが収まる最小幅）
SIDEBAR_FIXED_WIDTH = "330px"

# 📸 サイドバー (画像アップロードをここに固定)
# =========================================
with st.sidebar:
    st.header("📸 画像で質問する")
    st.caption("下のBrowse filesを押してファイルをアップロード")
    
    # 画像アップロード機能（ラベルを空に設定）
    uploaded_image = st.file_uploader("", type=["jpg", "jpeg", "png"])
    
    uploaded_bytes = None
    if uploaded_image:
        # アップロードされた画像を表示し、サイズを小さくする
        st.image(uploaded_image, caption="送信画像", width=300) 
        # バイナリデータの読み込み
        uploaded_bytes = uploaded_image.read()
    else:
        uploaded_bytes = None

# =========================================
# Streamlit UI 設定とカスタム CSS
# =========================================
st.set_page_config(
    page_title="ユッキー",
    layout="wide",
    # ★ サイドバーを固定し、開いた状態を維持
    initial_sidebar_state="expanded", 
    # メニュー（三点リーダー）とフッターを非表示
    menu_items={'About': None, 'Report a bug': None, 'Get help': None}
)

# カスタム CSS でサイドバーの幅固定、リサイズバー、水平スクロールを制御
st.markdown(f"""
<style>
/* Streamlitヘッダーを非表示 */
header {{ visibility: hidden; }}

/* サイドバーのリサイズハンドルを非表示（サイドバーとメインコンテンツの間） */
[data-testid="stSidebarContent"] + div {{
    display: none !important;
}}

/* サイドバーのコンテンツコンテナ */
[data-testid="stSidebarContent"] {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    min-width: {SIDEBAR_FIXED_WIDTH} !important;
    max-width: {SIDEBAR_FIXED_WIDTH} !important;
    background-color: #f7f0ff;
    overflow-x: hidden !important; 
    overflow-y: hidden !important; 
}}

/* サイドバーを閉じるボタン（<<）を非表示 */
[data-testid="stSidebarCollapseButton"] {{
    display: none !important;
}}

/* サイドバー内のコンテンツを中央に寄せたい場合 */
[data-testid="stSidebarContent"] > div:first-child {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
}}
</style>
""", unsafe_allow_html=True)

# ---- セッション初期化 ----
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None

if "chat" not in st.session_state:
    if st.session_state.client:
        config = {
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.2
        }
        st.session_state.chat = st.session_state.client.chats.create(
            model="gemini-2.5-flash",
            config=config
        )
    else:
        st.session_state.chat = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# =========================================
# メイン画面 UI
# =========================================
st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

# ---------- チャット履歴 ----------
st.subheader("ユッキーとの会話履歴")

for msg in st.session_state.messages:
    avatar_icon = "🧑" if msg["role"] == "user" else "yukki-.jpg"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# ---------- テキストチャット入力 ----------
if prompt := st.chat_input("質問を入力してください…"):
    
    # 履歴へ追加 (ユーザー)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Geminiへのメッセージ内容を構築するためのリスト
    contents_to_send = []
    
    # 1. テキストプロンプトを追加
    contents_to_send.append(prompt) 
    
    # 2. 画像データがあれば追加
    if uploaded_image and uploaded_bytes:
        
        # Part.from_bytes() を使って画像データを Part オブジェクトに変換
        try:
            image_part = Part.from_bytes(
                data=uploaded_bytes,
                mime_type=uploaded_image.type
            )
            contents_to_send.append(image_part)
        except Exception as e:
            print(f"画像データのPart変換中にエラーが発生しました: {e}")
            
    # ---- Gemini へ送信 ----
    if st.session_state.chat:
        
        message_content = contents_to_send 
        
        try:
            # chat.send_message にリストを渡す
            response = st.session_state.chat.send_message(message_content)
        except Exception as e:
            # 送信時のエラーをキャッチし、ログに出力
            response_text = f"Gemini API送信エラー: {type(e).__name__} - {e}"
            print(response_text)
            
        else:
            response_text = response.text if hasattr(response, "text") else str(response)

    else:
        response_text = "APIキーが設定されていないため応答できません。"

    # 履歴に追加 (アシスタント)
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # 画像がアップロードされていた場合、次回再実行時に画像が再送信されるのを防ぐための処置
    if uploaded_image:
        # この行はStreamlitのセッション状態には影響しませんが、
        # 変数の参照をリセットする意図で残しています
        uploaded_image = None 

    st.rerun()
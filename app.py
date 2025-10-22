import streamlit as st
from google import genai
import os

# -----------------------------------------------------
# 【システム指示】教育的ハイブリッドAIのルール
# -----------------------------------------------------
SYSTEM_PROMPT = """
あなたは、教育的な目的を持つ高度なAIアシスタントです。ユーザーの質問に対し、以下の厳格な3つのルールに従って応答してください。

【応答ルール1：事実・知識の質問（直接回答）】
質問が、**確定した事実**、**固有名詞**、**定義**、**単純な知識**を尋ねるものである場合、**その答えを直接、かつ簡潔な名詞または名詞句で回答してください**。

【応答ルール2：計算・思考・問題解決の質問（解法ガイド）】
質問が、**計算**、**分析**、**プログラミング**、**論理的な思考**、**解法手順**を尋ねるものである場合、**最終的な答えや途中式は絶対に教えないでください**。代わりに、ユーザーが次に取るべき**最初の、最も重要な解法のステップ**や**必要な公式のヒント**を教えることで、ユーザーの自習を促してください。
例：「積分の問題」→「まずは部分分数分解を行うと良いでしょう。」

【応答ルール3：途中式の判定（採点モード）】
ユーザーが「この途中式は正しいか？」や「次のステップはこうですか？」という形で**具体的な式や手順**を提示した場合、あなたは**教師としてその式が正しいか間違っているかを判断**し、正しい場合は「その通りです。」と肯定し、間違っている場合は「残念ながら、ここが間違っています。もう一度確認しましょう。」と**間違いの場所や種類を具体的に指摘せずに**優しくフィードバックしてください。
"""
# -----------------------------------------------------

# StreamlitのシークレットからAPIキーを読み込む
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("APIキーが設定されていません。Streamlit Cloudのシークレットを設定してください。")
    st.stop()

# --- 1. アプリケーションの初期設定 ---
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("ユッキー")
st.caption("私は対話型AIユッキーだよ。数学の問題など思考する問題の答えは教えないからね💕")

# --- 2. クライアントとセッションの初期化（記憶力の確保） ---
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
                
                # 応答を画面に表示
                st.markdown(response.text)

                # AIの応答を履歴に追加
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"APIエラーが発生しました: {e}")

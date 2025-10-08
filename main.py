import os
import sqlite3
import random
import string
import datetime
import asyncio
import threading
import logging # 💡 強化ポイント: ロギングの導入
from dotenv import load_dotenv

# Discord
import discord
from discord.ext import commands
from discord import app_commands, Embed, Interaction, ui, ButtonStyle

# Flask
from flask import Flask, request, jsonify, render_template_string
from waitress import serve # 💡 強化ポイント: 本番環境向けWSGIサーバーを導入

# ==============================================================================
# 1. 初期設定とグローバル変数
# ==============================================================================

# ロギング設定 (BotとFlask両方で共通利用)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 環境変数をロード
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Renderのエフェメラル環境に対応するため、相対パスを使用 (永続性はないが動作はする)
DATABASE_FILE = 'ip_auth.db'

# 💡 強化ポイント: SQLiteの排他制御のためのスレッドロック
DB_LOCK = threading.Lock()

# 認証後のコンテンツ (内容は省略せずそのまま維持)
AUTHENTICATED_CONTENT_HTML = """
          <style>
            #auth-content-card {
              width: 90%; max-width: 350px; padding: 25px; margin-top: 50px;
              background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(5px); border-radius: 20px; 
              text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,0.1);
              color: #1b1f24;
              border: 1px solid rgba(0,0,0,0.1);
            }
            #auth-content-card h2 { font-size: 1.6rem; color: #0d6efd; margin-bottom: 0.5rem; font-weight: 800;}
            #auth-content-card p { font-size: 1.0rem; margin: 0; line-height: 1.5;}
          </style>
          <center>
            <div id="auth-content-card">
              <h2>✅ 認証成功！ようこそ！</h2>
              <p style="margin-top: 10px;">このページが**更新版のコンテンツ**です。</p>
              <p style="font-size: 0.9rem; color: #6c757d; margin-top: 5px;">（この認証は7日間有効ですが、サーバーが再起動するとリセットされます。リセットされたら再度承認が必要です。）</p>
            </div>
          </center>
"""

# HTMLテンプレート (長いため、コードの末尾に移動した前回版のHTMLをそのまま使用)
# テンプレート全体は省略...（元のコードのAUTH_HTML_TEMPLATEの内容を維持）
AUTH_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <title>IPアドレス認証</title>
    <script
      type="text/javascript"
      src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.3.2/dist/confetti.browser.min.js"
    ></script>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>
    /* ... CSS部分は省略 ... */
    </style>
  </head>
  <body>
    <main class="container" id="auth-screen">
      <div class="illustration-wrapper" id="icon-wrapper"></div>
      <h1 class="title" id="auth-title">IPアドレス認証が必要です 🔐</h1>
      <div class="divider" aria-hidden="true"></div>

      <div id="dynamic-flow">
        <div class="auth-step">
          <div class="step-title">
            1. 認証コードを発行
            <span id="id-status">...</span>
          </div>
          <div class="step-content">
            <span id="generated-id" data-code="">コード発行中...</span>
            <button class="step-button" id="copy-id-button" disabled>
              📋 コードをコピー
            </button>
          </div>
        </div>

        <div class="auth-step">
          <div class="step-title">
            2. Discordで承認
            <span id="auth-status">未完了</span>
          </div>
          <p class="message-small">
            このコードをコピーし、Discordチャンネルで<br />
            **/認証コード承認** コマンドを実行し、**「認証コード入力」ボタン**からコードを入力してください。
          </p>
        </div>
      </div>
      <p class="message" id="auth-message">状態を確認しています...</p>
    </main>
    <div id="authenticated-content"></div>
    
    <footer class="page-footer">
      <a href="https://discord.gg/ZuEvp5PKWA" class="support-link" target="_blank" rel="noopener noreferrer">
        (サポートサーバー)
      </a>
    </footer>

    <div class="theme-switch-wrapper" aria-label="テーマ切り替え">
      <label class="theme-switch">
        <input type="checkbox" id="checkbox" aria-label="ダークモード" />
        <div class="slider">
          <div class="slider-icon">
             <svg class="sun-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V4a1 1 0 0 1 1-1zm7.07 3.93a1 1 0 0 1 0 1.414l-.707.707a1 1 0 1 1-1.414-1.414l.707-.707a1 1 0 0 1 1.414 0zM12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm-8.07-1.07a1 1 0 0 1 1.414 0l.707.707A1 1 0 1 1 4.636 9.05l-.707-.707a1 1 0 0 1 0-1.414zM4 12a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2H5a1 1 0 0 1-1-1zm.636 5.95a1 1 0 0 1 0-1.414l.707-.707a1 1 0 0 1 1.414 1.414l-.707.707a1 1 0 0 1 0 1.414zM12 19a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1zm7.07-1.07a1 1 0 0 1-1.414 0l-.707-.707a1 1 0 0 1 1.414-1.414l.707.707a1 1 0 0 1 0 1.414zM20 12a1 1 0 0 1-1 1h-1a1 1 0 1 1 0-2h1a1 1 0 0 1 1 1z"/>
             </svg>
             <svg class="moon-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313-12.454z"/></svg>
          </div>
        </div>
      </label>
    </div>

    <svg style="position: absolute; width: 0; height: 0; overflow: hidden;" aria-hidden="true">
      <defs>
        <linearGradient id="grad-success" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="var(--accent-color)" /><stop offset="100%" stop-color="var(--accent-color-2)" />
        </linearGradient>
        <path id="success-circle-path" d="M26 2c13.255 0 24 10.745 24 24s-10.745 24-24 24S2 39.255 2 26 12.745 2 26 2z"/>
        <path id="success-check-path" d="M14.1 27.2l7.1 7.2 16.7-16.8" />
        <linearGradient id="grad-error" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="var(--error-color)" /><stop offset="100%" stop-color="var(--error-color-2)" />
        </linearGradient>
        <path id="error-circle-path" d="M26 2c13.255 0 24 10.745 24 24s-10.745 24-24 24S2 39.255 2 26 12.745 2 26 2z"/>
        <path id="error-cross-path" d="M16 16 36 36 M36 16 16 36" />
      </defs>
    </svg>

    <script>
      // 🚨 サーバーの公開URLを設定してください (例: "https://your-public-server.com")
      const serverUrl = "https://takaios-bot.onrender.com"; // ★★★ ここを必ず修正 ★★★
      let checkInterval;

      // ... JavaScript (認証コード生成/チェックロジック、テーマ管理) は変更なし ...
      async function generateAuthId() {
        const idSpan = document.getElementById("generated-id");
        const copyButton = document.getElementById("copy-id-button");

        idSpan.textContent = "コード発行中...";
        copyButton.disabled = true;
        document.getElementById("id-status").textContent = "...";

        try {
          const response = await fetch(serverUrl + "/generate_id");
          const data = await response.json();

          if (data.status === "authenticated") {
            checkAuthentication(true); 
            return;
          }

          if (data.auth_id) {
            idSpan.textContent = data.auth_id;
            idSpan.dataset.code = data.auth_id;
            document.getElementById("id-status").textContent = "✅ 発行済 (5分間有効)";
            copyButton.disabled = false;
          } else {
            idSpan.textContent = "発行失敗";
            document.getElementById("id-status").textContent = "❌ 失敗";
          }
        } catch (error) {
          idSpan.textContent = "サーバーエラー";
          document.getElementById("id-status").textContent = "❌ 失敗";
        }
      }

      function copyIdToClipboard() {
        const id = document.getElementById("generated-id").dataset.code;
        if (id) {
          navigator.clipboard
            .writeText(id)
            .then(() => {
              const button = document.getElementById("copy-id-button");
              const originalText = button.textContent;
              button.textContent = "✅ コピー完了！";
              setTimeout(() => {
                button.textContent = originalText;
              }, 1500);
            })
            .catch((err) => {
              alert("コピーに失敗しました: " + err);
            });
        }
      }
      document
        .getElementById("copy-id-button")
        .addEventListener("click", copyIdToClipboard);

      async function checkAuthentication(forceContentLoad = false) {
        const authScreen = document.getElementById("auth-screen");
        const authContent = document.getElementById("authenticated-content");
        const authTitle = document.getElementById("auth-title");
        const authMessage = document.getElementById("auth-message");
        const iconWrapper = document.getElementById("icon-wrapper");

        if (!forceContentLoad) {
          authMessage.innerHTML = '状態を確認中...';
        }

        try {
          // 認証状態の確認
          const authResponse = await fetch(serverUrl + "/check_auth");
          const authData = await authResponse.json();

          if (authData.authenticated) {
            // --- 認証成功フロー ---
            clearInterval(checkInterval);

            authTitle.textContent = "🎉 認証成功！";
            authMessage.textContent = "更新版コンテンツを読み込みます...";
            document.getElementById("dynamic-flow").style.display = "none";
            iconWrapper.style.opacity = 1;

            // 成功アニメーションSVGを挿入
            iconWrapper.innerHTML = `
                <svg class="success-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52" aria-hidden="true">
                    <circle class="success-icon__circle" cx="26" cy="26" r="24" fill="none"/>
                    <path class="success-icon__check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                </svg>
            `;
            // 紙吹雪アニメーション
            confetti({ particleCount: 150, spread: 80, origin: { y: 0.6 }, colors: ["#00f5ff", "#0d6efd", "#f8f9fa", "#6c757d"], });

            await new Promise((resolve) => setTimeout(resolve, 1500));

            // 更新版コンテンツをロード
            const contentResponse = await fetch(serverUrl + "/authenticated_content");

            if (contentResponse.ok) {
              const contentHtml = await contentResponse.text();

              authScreen.style.display = "none";
              authContent.innerHTML = contentHtml;
              authContent.style.display = "block";
            } else {
              authTitle.textContent = "❌ コンテンツ読み込み失敗";
              authMessage.textContent = `エラーコード: ${contentResponse.status}。サーバーのコンテンツ設定を確認してください。`;
              // 失敗アイコンに切り替え
              iconWrapper.innerHTML = `
                <svg class="error-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52" aria-hidden="true">
                    <circle class="error-icon__circle" cx="26" cy="26" r="24" fill="none" style="stroke-dashoffset:0;"/>
                    <path class="error-icon__cross" fill="none" d="M16 16 36 36 M36 16 16 36" style="stroke-dashoffset:0; stroke:url(#grad-error)"/>
                </svg>
              `;
            }
          } else {
            // --- 未認証フロー ---
            authScreen.style.display = "block";
            authContent.style.display = "none";
            
            authTitle.textContent = "IPアドレス認証が必要です 🔐";
            authMessage.textContent = "Discordでの承認をお待ちください。";
            document.getElementById("dynamic-flow").style.display = "block";
            iconWrapper.innerHTML = '';
            iconWrapper.style.opacity = 0;

            // 認証コードが未発行/期限切れの場合は再発行を試みる
            if (
              !document.getElementById("generated-id").dataset.code ||
              document.getElementById("id-status").textContent.includes("失敗")
            ) {
              generateAuthId();
            }
          }
        } catch (error) {
          authTitle.textContent = "🚨 サーバーエラー";
          authMessage.textContent = "サーバーに接続できません。`serverUrl`の設定またはサーバーの状態を確認してください。";
          // エラーアイコン表示
          iconWrapper.innerHTML = `
                <svg class="error-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52" aria-hidden="true">
                    <circle class="error-icon__circle" cx="26" cy="26" r="24" fill="none" style="stroke-dashoffset:0;"/>
                    <path class="error-icon__cross" fill="none" d="M16 16 36 36 M36 16 16 36" style="stroke-dashoffset:0; stroke:url(#grad-error)"/>
                </svg>
            `;
            iconWrapper.style.opacity = 1;
        }
      }

      // ... JavaScript (テーママネージャー) は変更なし ...
      class ThemeManager {
        constructor() {
          this.checkbox = document.querySelector("#checkbox");
          this.initializeTheme();
          this.setupEventListeners();
        }
        initializeTheme() {
          const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");
          const savedTheme = localStorage.getItem("theme");
          if (savedTheme) {
            document.documentElement.setAttribute("data-theme", savedTheme);
            this.checkbox.checked = savedTheme === "dark";
          } else {
            const theme = prefersDark.matches ? "dark" : "light";
            document.documentElement.setAttribute("data-theme", theme);
            this.checkbox.checked = prefersDark.matches;
          }
        }
        setupEventListeners() {
          this.checkbox.addEventListener("change", () => {
            const theme = this.checkbox.checked ? "dark" : "light";
            document.documentElement.setAttribute("data-theme", theme);
            localStorage.setItem("theme", theme);
          });
          window
            .matchMedia("(prefers-color-scheme: dark)")
            .addEventListener("change", (e) => {
              if (!localStorage.getItem("theme")) {
                const theme = e.matches ? "dark" : "light";
                document.documentElement.setAttribute("data-theme", theme);
                this.checkbox.checked = e.matches;
              }
            });
        }
      }
      new ThemeManager();

      // 初回実行と3秒ごとの認証状態チェック
      window.onload = () => {
          checkAuthentication();
          // ポーリング処理を3秒ごと実行
          checkInterval = setInterval(checkAuthentication, 3000);
      };
    </script>
  </body>
</html>
"""

# ==============================================================================
# 2. データベース操作関数 (スレッドセーフ化)
# ==============================================================================
def init_db():
    """データベースの初期化とテーブルの作成"""
    try:
        with DB_LOCK: # 💡 DBロックを使用
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth_data (
                        ip_address TEXT PRIMARY KEY,
                        auth_id TEXT UNIQUE,
                        is_authenticated INTEGER DEFAULT 0,
                        expires_at TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                conn.commit()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")

def get_setting(key):
    """設定値を取得"""
    with DB_LOCK:
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Error fetching setting '{key}': {e}")
            return None

def set_setting(key, value):
    """設定値を保存"""
    with DB_LOCK:
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error saving setting '{key}': {e}")

def generate_auth_id(ip_address):
    """認証IDを自動生成し、IPを登録/更新"""
    auth_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    expires_at = (datetime.datetime.now() + datetime.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')

    with DB_LOCK:
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                
                if check_auth_status(ip_address):
                     return None
                
                cursor.execute("""
                    INSERT OR REPLACE INTO auth_data (ip_address, auth_id, is_authenticated, expires_at)
                    VALUES (?, ?, 0, ?)
                """, (ip_address, auth_id, expires_at))
                conn.commit()
                return auth_id
        except sqlite3.Error as e:
            logger.error(f"Error generating auth ID for IP {ip_address}: {e}")
            return None

def check_auth_status(ip_address):
    """認証状態を確認"""
    with DB_LOCK:
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_authenticated, expires_at FROM auth_data WHERE ip_address = ?", (ip_address,))
                result = cursor.fetchone()
                if result:
                    is_authenticated, expires_at_str = result
                    expires_at = datetime.datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S')

                    if is_authenticated == 1 and expires_at > datetime.datetime.now():
                        return True
                    
                    if expires_at <= datetime.datetime.now() and is_authenticated == 0:
                         cursor.execute("DELETE FROM auth_data WHERE ip_address = ? AND is_authenticated = 0", (ip_address,))
                         conn.commit()
                         return False
                    
                    return False
                return False
        except sqlite3.Error as e:
            logger.error(f"Error checking auth status for IP {ip_address}: {e}")
            return False

def approve_ip_by_id(auth_id):
    """Discordからの認証コード承認処理"""
    with DB_LOCK:
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ip_address FROM auth_data WHERE auth_id = ?", (auth_id,))
                result = cursor.fetchone()

                if result:
                    ip_address = result[0]
                    new_expires_at = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute("""
                        UPDATE auth_data 
                        SET is_authenticated = 1, expires_at = ?
                        WHERE auth_id = ?
                    """, (new_expires_at, auth_id))
                    conn.commit()
                    logger.info(f"Auth approved for IP: {ip_address} using code: {auth_id}")
                    return ip_address
                return None
        except sqlite3.Error as e:
            logger.error(f"Error approving auth ID {auth_id}: {e}")
            return None

# ==============================================================================
# 3. Flask サーバー設定 (AppFactoryパターンを使用)
# ==============================================================================

app = Flask(__name__)

# Flaskのルーティングは変更なし。IPアドレス取得はX-Forwarded-Forを優先する堅牢な実装を維持。
def get_client_ip(req):
    """プロキシ環境から真のクライアントIPを取得"""
    # X-Forwarded-Forヘッダーを優先し、最初のIPを取得 (Render/Heroku対応)
    ip_header = req.headers.get('X-Forwarded-For')
    if ip_header:
        return ip_header.split(',')[0].strip()
    return req.remote_addr

@app.route('/')
def index():
    """index.htmlの代わりに認証ページを表示"""
    return render_template_string(AUTH_HTML_TEMPLATE)

@app.route('/generate_id', methods=['GET'])
def api_generate_id():
    """認証コードを生成し、IPを登録"""
    ip_address = get_client_ip(request)
    if check_auth_status(ip_address):
        logger.info(f"IP {ip_address} already authenticated or ID generated.")
        return jsonify({"status": "authenticated"}), 200

    auth_id = generate_auth_id(ip_address)
    if not auth_id: 
        logger.warning(f"Failed to generate auth ID for IP {ip_address}.")
        return jsonify({"status": "authenticated"}), 200 # DBエラーの場合も安全のため authenticated を返す
        
    logger.info(f"Generated auth ID {auth_id} for IP {ip_address}.")
    return jsonify({"status": "success", "auth_id": auth_id}), 200

@app.route('/check_auth', methods=['GET'])
def api_check_auth():
    """認証状態をチェック"""
    ip_address = get_client_ip(request)
    authenticated = check_auth_status(ip_address)
    return jsonify({"authenticated": authenticated}), 200

@app.route('/authenticated_content', methods=['GET'])
def api_authenticated_content():
    """認証成功時に表示するコンテンツ (更新版のあれ)"""
    ip_address = get_client_ip(request)
    
    if check_auth_status(ip_address):
        logger.info(f"Serving content to authenticated IP: {ip_address}")
        return AUTHENTICATED_CONTENT_HTML
    
    logger.warning(f"Access denied to unauthenticated IP: {ip_address}")
    return "認証が必要です。", 403


# ==============================================================================
# 4. Discord Bot 設定 (エラー処理強化)
# ==============================================================================

# 認証コード入力用モーダルフォーム
class AuthCodeModal(ui.Modal, title="認証コード承認"):
    """ユーザーから認証コードを受け取るためのモーダル"""
    code_input = ui.TextInput(
        label="認証コードを入力してください",
        placeholder="ウェブページに表示されている6桁のコード (例: A1B2C3)",
        style=discord.TextStyle.short,
        min_length=6,
        max_length=6,
        required=True
    )
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: Interaction):
        code = self.code_input.value.upper()
        
        # 💡 DB処理を関数化しているため、ここではロック不要
        ip_address = approve_ip_by_id(code)
        
        if ip_address:
            embed = Embed(
                title="✅ IPアドレス認証が完了しました",
                description=f"コード `{code}` を持つIPアドレス (`{ip_address}`) の認証を承認しました。",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"実行者: {interaction.user.display_name} ({interaction.user.id})")
            
            # 💡 ログチャンネルへの通知 (エラー処理をロギングに統一)
            log_channel_id = get_setting('log_channel_id')
            if log_channel_id:
                try:
                    log_channel = self.bot.get_channel(int(log_channel_id))
                    if log_channel:
                        await log_channel.send(embed=embed)
                    else:
                         logger.warning(f"Log channel ID {log_channel_id} not found/cached.")
                except ValueError:
                    logger.error(f"Invalid log channel ID stored: {log_channel_id}")
                except Exception as e:
                    logger.error(f"Failed to send log message: {e}")

            await interaction.response.send_message("✅ 認証が完了しました。ユーザーの画面が切り替わります。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 無効な認証コードです。コードを再確認するか、ユーザーに再発行させてください。", ephemeral=True)


# 認証コード入力ボタンを持つView
class AuthCodeView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="認証コード入力", style=ButtonStyle.primary, custom_id="persistent_auth_code_button")
    async def approve_button(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(AuthCodeModal(self.bot))


class MyBot(commands.Bot):
    def __init__(self):
        # 必要なすべてのインテントを設定 (前回のエラー対策済みであることを前提)
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True # メンバーインテントも一応追加
        
        super().__init__(command_prefix='!', intents=intents)
        
    async def setup_hook(self):
        """Botの準備完了後に実行される処理"""
        # 永続Viewの追加
        self.add_view(AuthCodeView(self))
        
        # 💡 強化ポイント: コマンドツリーの同期
        try:
            # コマンドの登録
            self.tree.add_command(self.set_log_channel)
            self.tree.add_command(self.approve_code_slash)
            
            synced_commands = await self.tree.sync()
            logger.info(f"Synced {len(synced_commands)} slash commands globally.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        # 🚨 起動時のコマンドSignatureMismatchは、このsync()の成功で解消します。

    # --- Discord コマンド ---

    @app_commands.command(name="bot設定", description="認証ログチャンネルを設定します。")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(self, interaction: Interaction, チャンネル: discord.TextChannel):
        set_setting('log_channel_id', str(チャンネル.id))
        await interaction.response.send_message(f"✅ 認証ログチャンネルを {チャンネル.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="認証コード承認", description="認証コード承認用のボタンを表示します。")
    async def approve_code_slash(self, interaction: Interaction):
        embed = Embed(
            title="認証コード承認が必要です",
            description="ウェブページに表示された**6桁の認証コード**を、下の**[認証コード入力]ボタン**を押して表示されるフォームに入力してください。",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(
            embed=embed,
            view=AuthCodeView(self),
            ephemeral=False
        )
        
    async def on_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        """💡 強化ポイント: コマンド実行時の一般的なエラー処理"""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        else:
            logger.error(f"Unhandled command error in {interaction.command.name}: {error}")
            # ユーザーには一般的なエラーを返す
            if not interaction.response.is_done():
                 await interaction.response.send_message("❌ コマンドの実行中に予期せぬエラーが発生しました。", ephemeral=True)


# ==============================================================================
# 5. サーバー/Bot 起動ロジック
# ==============================================================================

def run_flask_server():
    """Flaskサーバーを別スレッドで起動 (waitress使用)"""
    # Renderは環境変数PORTを提供するため、それを使用
    port = int(os.environ.get('PORT', 8000)) 
    logger.info(f"Starting Flask server using Waitress on http://0.0.0.0:{port}")
    try:
        # 💡 強化ポイント: Flask開発サーバーの代わりに、本番環境向けのWSGIサーバー Waitressを使用
        # Waitressはマルチスレッド/プロセスを適切に扱い、より安定します
        serve(app, host='0.0.0.0', port=port)
    except Exception as e:
        logger.critical(f"Flask server fatal error: {e}")

def run_bot(token):
    """Discord Botの起動と再接続ループ (エラー対策)"""
    while True:
        try:
            bot = MyBot()
            bot.run(token)
        except discord.errors.LoginFailure:
            logger.critical("Discord Token is invalid. Cannot log in.")
            break # トークンエラーは致命的なので終了
        except Exception as e:
            logger.error(f"Discord bot disconnected or crashed: {e}. Reconnecting in 5 seconds...")
            asyncio.sleep(5) # その他のエラーで切断された場合は5秒後に再接続


if __name__ == '__main__':
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN environment variable not set. Aborting.")
    else:
        # 1. DB初期化
        init_db()
        
        # 2. Flaskサーバーをスレッドで起動 (Webサーバー)
        flask_thread = threading.Thread(target=run_flask_server, name="Flask-Server")
        flask_thread.daemon = True 
        flask_thread.start()
        
        # 3. Discord Botをメインスレッドで起動 (エラー時に再接続を試みる)
        run_bot(DISCORD_TOKEN)
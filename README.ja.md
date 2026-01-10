# MT5 Bridge API

## 概要
`mt5_bridge`はMetaTrader 5ターミナルと外部アプリケーションの間で市場データの取得や注文実行を仲介するためのFastAPIサービス兼CLIツールです。

- **サーバー機能**: MetaTrader 5がインストールされたWindows環境で動作し、REST API機能を提供します。
- **クライアント機能**: Windows、Linux、macOSなど任意のOSで動作し、サーバーと通信してデータの取得や注文を行います。

## 前提条件
- Python 3.9以上
- **サーバーモード**: MetaTrader 5ターミナルがインストールされたWindows環境。
- **クライアントモード**: 任意のOS環境。

## インストール (Poetry)

本プロジェクトはパッケージ管理に [Poetry](https://python-poetry.org/) を使用しています。

```bash
# 依存関係のインストール
poetry install
```

LinuxやmacOS環境では、Windows専用の `MetaTrader5` パッケージは自動的にスキップされ、クライアント機能のみが利用可能な状態でインストールされます。

## 使い方

インストールすると `mt5-bridge` コマンドが利用可能になります。

### 1. サーバーの起動 (Windowsのみ)

MT5がインストールされているWindowsマシンで実行します:

```powershell
# デフォルト設定 (localhost:8000) で起動
poetry run mt5-bridge server

# ホストやポートを指定
poetry run mt5-bridge server --host 0.0.0.0 --port 8000
```

主なオプション:
- `--mt5-path "C:\Path\To\terminal64.exe"`: MT5のパスを明示的に指定して初期化
- `--no-utc`: サーバー時間をUTCに変換せず、そのまま返す（デフォルトはUTC変換有効）

### 2. クライアントの利用 (任意のプラットフォーム)

別のマシン（または同一マシン）からクライアントコマンドでサーバーを操作できます。

```bash
# サーバーのヘルスチェック
poetry run mt5-bridge client --url http://192.168.1.10:8000 health

# 過去レートの取得 (M1, 最新1000本) - シンボル: XAUUSD
poetry run mt5-bridge client --url http://192.168.1.10:8000 rates XAUUSD

# 最新ティックの取得
poetry run mt5-bridge client --url http://192.168.1.10:8000 tick XAUUSD

# 保有ポジションの一覧表示
poetry run mt5-bridge client --url http://192.168.1.10:8000 positions
```

### JSON API

汎用的なHTTPクライアントやライブラリから直接APIを利用することも可能です。

- `GET /health`
- `GET /rates/{symbol}?timeframe=M1&count=1000`
- `GET /tick/{symbol}`
- `GET /positions`
- `POST /order`
- `POST /close`
- `POST /modify`

## 構成
- `mt5_bridge/main.py`: CLIエントリポイントおよびFastAPIサーバー定義。
- `mt5_bridge/mt5_handler.py`: MetaTrader5パッケージのラッパー（条件付きインポートにより非Windows環境でもエラーになりません）。
- `mt5_bridge/client.py`: HTTPクライアントの実装。

## MCP (Copilot CLI) 連携
- 目的: MT5 Bridge APIをCopilot CLI (MCP) として公開します。
- 実行方法:
  - `python mt5_bridge/mcp_server.py --api-base http://localhost:8000`

## サポート・寄付
- <a href="https://github.com/sponsors/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png" alt="GitHub Sponsors" height="32" /></a> GitHub Sponsors: [https://github.com/sponsors/akivajp](https://github.com/sponsors/akivajp)
- <a href="https://buymeacoffee.com/akivajp" style="vertical-align: middle;"><img src="https://github.githubassets.com/assets/buy_me_a_coffee-63ed78263f6e.svg" alt="Buy Me a Coffee" height="32" /></a> Buy Me a Coffee: [https://buymeacoffee.com/akivajp](https://buymeacoffee.com/akivajp)

上記以外の支援方法を希望される場合は Issue や Discussions でご相談ください。
少額の寄付・サポートはいつでも大歓迎です。お気持ちだけでも大きな励みになります。

## ライセンス
本プロジェクトは MIT License の下で提供されます。詳細は `LICENSE` を参照してください。

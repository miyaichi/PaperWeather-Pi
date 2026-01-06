"""
PaperWeather-Pi - E-Ink Weather Dashboard
==========================================
Raspberry Pi Zero 2 W + Waveshare 7.5inch E-Paper HAT用の天気ダッシュボード

主な機能:
- OpenWeather APIから現在の天気と5日間予報を取得
- E-Inkディスプレイに最適化された黒/赤の2色表示
- シミュレーションモード対応（開発環境でPNG出力）
- 環境変数による柔軟な設定管理
- ループモードによる定期的な自動更新
"""

import json
import logging
import argparse
import time
import os
import sys

# ロギング設定（INFO以上のメッセージを出力）
# 他のモジュールをimportする前に設定
logging.basicConfig(
    level = logging.INFO,
    format = '%(asctime)s - %(levelname)s - %(message)s',
    force = True  # 既存の設定を上書き
)

# srcディレクトリをPythonパスに追加（相対インポートのため）
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from weather import WeatherFetcher
from display import EInkDisplay
from renderer import Renderer


def load_env_file(path = ".env"):
    """
    .envファイルから環境変数を読み込む

    Pythonの標準ライブラリのみを使用した軽量な実装。
    既に設定されている環境変数は上書きしない。

    Args:
        path (str): .envファイルのパス（デフォルト: ".env"）

    Note:
        - 空行とコメント行（#で始まる）は無視
        - KEY=VALUE形式でパース
        - ファイルが存在しない場合は警告なしで継続
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding = "utf-8") as env_file:
            for line in env_file:
                stripped = line.strip()
                # 空行とコメント行をスキップ
                if not stripped or stripped.startswith("#"):
                    continue
                # =が含まれない行をスキップ
                if "=" not in stripped:
                    continue
                # KEY=VALUE形式でパース（=が複数ある場合は最初のみ分割）
                key, value = stripped.split("=", 1)
                # 既存の環境変数は上書きしない
                if key and value and key not in os.environ:
                    os.environ[key] = value
        logging.debug("Loaded environment variables from .env")
    except Exception:
        logging.warning("Failed to load .env; continuing without it")


def load_config(path = 'config.json'):
    """
    設定ファイルを読み込み、環境変数で上書きする

    環境変数が設定されている場合、config.jsonの値より優先される。
    これにより、開発環境と本番環境で異なる設定を使い分けられる。

    Args:
        path (str): 設定ファイルのパス（デフォルト: 'config.json'）

    Returns:
        dict: 設定情報の辞書

    環境変数の優先順位:
        1. 環境変数（最優先）
        2. config.json
        3. コード内のデフォルト値

    対応する環境変数:
        - OPENWEATHER_APPID: OpenWeather APIキー
        - LATITUDE, LONGITUDE: 緯度経度（float）
        - LOCALE: ロケール（例: ja_JP）
        - UNITS: 単位系（metric/imperial）
        - REFRESH_INTERVAL_MINUTES: 更新間隔（int）
        - FONT_MAIN, FONT_BOLD: フォントパス
    """
    with open(path, 'r', encoding = 'utf-8') as f:
        config = json.load(f)

    # 環境変数による上書き（APIキー、位置情報など）
    env_overrides = {
        'openweather_appid': os.getenv('OPENWEATHER_APPID'),
        'latitude': os.getenv('LATITUDE'),
        'longitude': os.getenv('LONGITUDE'),
        'locale': os.getenv('LOCALE'),
        'units': os.getenv('UNITS'),
        'refresh_interval_minutes': os.getenv('REFRESH_INTERVAL_MINUTES'),
    }

    for key, value in env_overrides.items():
        if value is None:
            continue
        # 数値型への変換（緯度経度）
        if key in ['latitude', 'longitude']:
            try:
                config[key] = float(value)
            except ValueError:
                logging.warning(f"Invalid numeric value for {key}, keeping config value.")
        # 整数型への変換（更新間隔）
        elif key == 'refresh_interval_minutes':
            try:
                config[key] = int(value)
            except ValueError:
                logging.warning(
                    "Invalid integer for refresh_interval_minutes, keeping config value."
                )
        # その他は文字列としてそのまま使用
        else:
            config[key] = value

    # フォントパスの環境変数上書き（クロスプラットフォーム対応）
    # macOS開発環境とRaspberry Pi本番環境で異なるフォントパスを使用可能
    font_main = os.getenv('FONT_MAIN')
    font_bold = os.getenv('FONT_BOLD')

    if font_main:
        config['fonts']['main'] = font_main
        logging.debug(f"Using FONT_MAIN from environment: {font_main}")

    if font_bold:
        config['fonts']['bold'] = font_bold
        logging.debug(f"Using FONT_BOLD from environment: {font_bold}")

    # APIキーの検証
    if config.get('openweather_appid') in [None, '', 'YOUR_OPENWEATHER_APPID']:
        logging.warning(
            "OpenWeather API key is not set. Set OPENWEATHER_APPID env var or config.json."
        )

    return config


def main():
    """
    メインエントリーポイント

    処理フロー:
        1. コマンドライン引数のパース
        2. 環境変数の読み込み（.env）
        3. 設定ファイルの読み込みと環境変数による上書き
        4. 各モジュールの初期化（WeatherFetcher, Renderer, Display）
        5. 天気データ取得→レンダリング→ディスプレイ更新
        6. ループモードの場合、定期的に5を繰り返す

    コマンドライン引数:
        --config: 設定ファイルのパス（デフォルト: config.json）
        --loop: ループモード（定期的に自動更新）
    """
    parser = argparse.ArgumentParser(description = 'WeatherPi E-Ink')
    parser.add_argument('--config', default = 'config.json', help = 'Path to config file')
    parser.add_argument('--loop', action = 'store_true', help = 'Run in a loop')
    args = parser.parse_args()

    # .envファイルから環境変数を読み込み（設定ファイル読み込み前に実行）
    load_env_file()

    # 設定ファイルを読み込み、環境変数で上書き
    config = load_config(args.config)

    # 入力検証
    lat = config.get('latitude')
    lon = config.get('longitude')

    if lat is None or lon is None:
        logging.error("Latitude and longitude must be set in config.json or environment variables.")
        return

    if not (-90 <= lat <= 90):
        logging.error(f"Invalid latitude: {lat}. Must be between -90 and 90.")
        return

    if not (-180 <= lon <= 180):
        logging.error(f"Invalid longitude: {lon}. Must be between -180 and 180.")
        return

    # 各モジュールの初期化
    # WeatherFetcher: OpenWeather APIからデータ取得
    # localeから言語コードを抽出（ja_JP -> ja, en_US -> en）
    locale = config.get('locale', 'en_US')
    lang = locale.split('_')[0] if '_' in locale else locale

    weather = WeatherFetcher(
        api_key = config['openweather_appid'],
        lat = config['latitude'],
        lon = config['longitude'],
        units = config['units'],
        lang = lang  # 言語コード（ja, en, etc.）
    )

    # Renderer: 天気データを画像に変換
    renderer = Renderer(config)

    # EInkDisplay: E-Inkディスプレイ制御（またはシミュレーション）
    display = EInkDisplay(width = config['display']['width'], height = config['display']['height'])

    # ディスプレイの初期化
    display.init()

    # 更新処理のヘルパー関数
    def update():
        """天気データ取得→レンダリング→表示の一連の処理"""
        try:
            # OpenWeather APIから天気データを取得
            data = weather.fetch()
            if data:
                # 天気データを黒/赤の2色画像に変換
                img_blk, img_red = renderer.render(data)
                # E-Inkディスプレイに表示（またはPNG出力）
                display.display(img_blk, img_red)
                logging.info("Display updated.")
            else:
                logging.error("Failed to fetch data, skipping display update.")
        except Exception as e:
            logging.exception(f"Update cycle failed: {e}")

    # 初回更新
    update()

    # ディスプレイをスリープモードに（低消費電力）
    display.sleep()
    logging.info("Update sequence complete.")

    # ループモード: 定期的に更新を繰り返す
    if args.loop:
        interval = config.get('refresh_interval_minutes', 30) * 60  # 分→秒に変換
        logging.info(f"Entering loop mode. Interval: {interval} seconds")
        while True:
            time.sleep(interval)
            logging.info("Waking up for update...")
            display.init()  # ディスプレイを再初期化
            update()
            display.sleep()  # 再度スリープ


if __name__ == "__main__":
    main()

"""
WeatherFetcher - OpenWeather API連携モジュール
==============================================
OpenWeather One Call APIから天気データを取得する

サポートするAPI:
- One Call API 3.0 (有料プラン)
- One Call API 2.5 (レガシー、自動フォールバック)
"""

import logging

import requests


class WeatherFetcher:
    """
    OpenWeather APIから天気データを取得するクラス

    One Call API 3.0を優先的に使用し、401エラー（認証失敗）が
    返された場合は自動的にAPI 2.5にフォールバックする。

    取得データ:
        - current: 現在の天気（気温、湿度、気圧、風速、UVインデックスなど）
        - hourly: 48時間先までの時間別予報
        - daily: 8日間の日別予報（最高/最低気温、降水確率など）
        - 日出・日没時刻、月相情報

    Attributes:
        api_key (str): OpenWeather APIキー
        lat (float): 緯度（-90～90）
        lon (float): 経度（-180～180）
        units (str): 単位系（'metric'=摂氏, 'imperial'=華氏, 'standard'=ケルビン）
        lang (str): 言語コード（例: 'ja', 'en'）
        timeout (int): HTTPリクエストのタイムアウト秒数
        base_url (str): APIのベースURL（フォールバック時に変更される）
    """

    def __init__(self, api_key, lat, lon, units = 'metric', lang = 'ja', timeout = 10):
        """
        WeatherFetcherの初期化

        Args:
            api_key (str): OpenWeather APIキー
            lat (float): 緯度
            lon (float): 経度
            units (str): 単位系（デフォルト: 'metric'）
            lang (str): 言語コード（デフォルト: 'ja'）
            timeout (int): タイムアウト秒数（デフォルト: 10）
        """
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.units = units
        self.lang = lang
        self.timeout = timeout
        # API 3.0を最初に試行（401エラー時は2.5にフォールバック）
        self.base_url = "https://api.openweathermap.org/data/3.0/onecall"

    def fetch(self):
        """
        OpenWeather APIから天気データを取得

        Returns:
            dict | None: 天気データのJSON（失敗時はNone）

        レスポンス構造（主要フィールド）:
            {
                "current": {
                    "dt": タイムスタンプ,
                    "temp": 気温,
                    "humidity": 湿度(%),
                    "pressure": 気圧(hPa),
                    "wind_speed": 風速(m/s),
                    "uvi": UVインデックス,
                    "weather": [{"icon": "01d", "description": "晴天"}],
                    "sunrise": 日出時刻,
                    "sunset": 日没時刻
                },
                "daily": [
                    {
                        "dt": タイムスタンプ,
                        "temp": {"max": 最高気温, "min": 最低気温},
                        "weather": [{"icon": "01d"}],
                        "moon_phase": 月相(0-1)
                    }
                ],
                "timezone_offset": タイムゾーンオフセット(秒)
            }

        エラー処理:
            - タイムアウト: 10秒でタイムアウト、Noneを返す
            - 401エラー: API 2.5に自動フォールバック
            - その他のエラー: ログ出力してNoneを返す
        """
        # APIリクエストパラメータ
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'units': self.units,
            'lang': self.lang,
            'exclude': 'minutely'  # 分単位データは除外（不要なため）
        }

        try:
            logging.info(f"Fetching weather data for lat={self.lat}, lon={self.lon}")
            response = requests.get(self.base_url, params = params, timeout = self.timeout)

            # API 3.0で401エラー（認証失敗）の場合、API 2.5にフォールバック
            # 無料プランや古いAPIキーはAPI 2.5のみサポート
            if response.status_code == 401 and "3.0" in self.base_url:
                logging.info("Trying OpenWeather API 2.5 onecall (401 from 3.0)...")
                self.base_url = "https://api.openweathermap.org/data/2.5/onecall"
                response = requests.get(self.base_url, params = params, timeout = self.timeout)

            # HTTPステータスコードのチェック（4xx, 5xxでエラー）
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logging.error("Weather API request timed out.")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching weather data: {e}")
            return None

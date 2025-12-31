"""
Renderer - 画像レンダリングモジュール
===================================
天気データをE-Ink用の2色（黒/赤）画像に変換する

主な機能:
- OpenWeather APIのJSONデータを視覚化
- E-Ink用の1bit画像生成（黒レイヤー、赤レイヤー）
- 天気アイコンのダウンロードとキャッシング
- 月齢アイコンの動的生成
- 5日間予報のレンダリング

画面レイアウト (800x480):
┌─────────────────────────────────────────────┐
│ 日付・時刻 │  日出/日没  │  月齢アイコン │
│ (左上)      │  (右上)      │  (右上)      │
├─────────────────────────────────────────────┤
│ 天気アイコン│  湿度・気圧  │              │
│ 現在気温    │  風速・UV    │              │
│ (左中央)    │  (右中央)    │              │
├─────────────────────────────────────────────┤
│ 5日間予報（曜日、アイコン、最高/最低気温） │
│ (下部)                                      │
└─────────────────────────────────────────────┘
"""

from PIL import Image, ImageDraw, ImageFont, ImageOps
import logging
import os
import math
import requests
from datetime import datetime
from i18n import I18n


class Renderer:
    """
    天気データを画像にレンダリングするクラス

    OpenWeather APIのJSONレスポンスを受け取り、E-Ink用の
    黒/赤2色の画像ペアを生成する。

    Attributes:
        config (dict): 設定情報（display、fonts等）
        width (int): 画像の幅（ピクセル）
        height (int): 画像の高さ（ピクセル）
        fonts (dict): フォントスタイル別のImageFontオブジェクト
        cache_dir (str): アイコンキャッシュディレクトリのパス
    """

    def __init__(self, config):
        """
        Rendererの初期化

        Args:
            config (dict): 設定情報（config.json由来）
        """
        self.config = config
        self.width = config['display']['width']
        self.height = config['display']['height']
        self.fonts = {}
        self._load_fonts()

        # 国際化（i18n）の初期化
        # config['locale']から言語を取得（例: 'ja_JP', 'en_US'）
        locale = config.get('locale', 'en_US')
        self.i18n = I18n(locale)

        # アイコンキャッシュディレクトリの作成
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'icons')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _load_fonts(self):
        """
        フォントを読み込む（プライベートメソッド）

        設定ファイルから指定されたTrueTypeフォントを読み込み、
        small/medium/large/hugeの4サイズで初期化。
        フォントが見つからない場合はデフォルトフォントにフォールバック。

        フォントの使い分け:
            - small: ラベル、補足情報
            - medium: 通常のテキスト、日付
            - large: 時刻
            - huge: メインの気温表示（64pt）、太字を使用
        """
        font_conf = self.config['fonts']
        sizes = font_conf['sizes']
        font_path = font_conf.get('main', 'arial.ttf')
        font_bold = font_conf.get('bold', font_path)  # ボールドが未指定なら通常フォント使用

        # フォントファイルの存在確認とフォールバック
        if not os.path.exists(font_path):
            logging.warning(f"Font not found at {font_path}, attempting default.")
            font_path = None
        if not os.path.exists(font_bold):
            font_bold = font_path

        # 各サイズのフォントを読み込み
        for style, size in sizes.items():
            try:
                if font_path:
                    # large/hugeは太字フォントを優先使用
                    path = font_bold if style in ['large', 'huge'] and font_bold else font_path
                    self.fonts[style] = ImageFont.truetype(path, size)
                else:
                    # フォントパスがない場合はデフォルト
                    self.fonts[style] = ImageFont.load_default()
            except IOError:
                logging.error(f"Could not load font {style}. Using default.")
                self.fonts[style] = ImageFont.load_default()

    def render(self, weather_data):
        """
        天気データを画像にレンダリング

        Args:
            weather_data (dict): OpenWeather APIのJSONレスポンス

        Returns:
            tuple: (image_black, image_red)
                - image_black: PIL.Image - 黒色ピクセル用の1bit画像
                - image_red: PIL.Image - 赤色ピクセル用の1bit画像

        レンダリング内容:
            1. ヘッダー（左上）: 日付、時刻
            2. メイン天気（左中央）: 天気アイコン、現在気温、説明文
            3. 日出/日没・月齢（右上）: Sunrise/Sunset時刻、月齢アイコン
            4. 詳細情報（右中央）: 湿度、気圧、風速、UVインデックス
            5. 5日間予報（下部）: 曜日、小アイコン、最高/最低気温

        E-Inkの色使い:
            - 黒レイヤー: 通常のテキスト、アイコン、枠線
            - 赤レイヤー: 最高気温（強調表示）
        """
        # 1bit画像のキャンバス作成（1=白、0=黒/赤）
        image_black = Image.new('1', (self.width, self.height), 1)
        draw_black = ImageDraw.Draw(image_black)

        image_red = Image.new('1', (self.width, self.height), 1)
        draw_red = ImageDraw.Draw(image_red)

        # データ取得失敗時のエラー表示
        if not weather_data:
            draw_black.text((10, 10),
                            "No Weather Data Available",
                            font = self.fonts.get('medium'),
                            fill = 0)
            return image_black, image_red

        # APIデータの抽出
        current = weather_data.get('current', {})
        daily_today = weather_data.get('daily', [{}])[0]

        # --- レイアウト構築 ---

        # タイムゾーンオフセット（UTC→ローカル時刻変換用）
        tz_offset = weather_data.get('timezone_offset', 0)

        # 1. ヘッダー: 日付・時刻（左上）
        current_dt = current.get('dt')
        if current_dt:
            now = datetime.utcfromtimestamp(current_dt + tz_offset)
        else:
            now = datetime.utcnow()
        # 日付と曜日を翻訳
        day_of_week_en = now.strftime("%a")  # Mon, Tue, etc.
        day_of_week = self.i18n(day_of_week_en)  # 月, 火, etc.
        date_str = now.strftime(f"%Y/%m/%d ({day_of_week})")  # 例: 2025/12/31 (火)
        time_str = now.strftime("%H:%M")

        draw_black.text((20, 15), date_str, font = self.fonts.get('medium'), fill = 0)
        draw_black.text((20, 50), time_str, font = self.fonts.get('large'), fill = 0)

        # 2. メイン天気情報（左中央）
        weather_main = current.get('weather', [{}])[0]
        icon_code = weather_main.get('icon', '01d')  # 例: '01d' = 晴天（昼）
        desc = weather_main.get('description', 'N/A')  # 日本語説明文
        temp = current.get('temp', 0)

        # 天気アイコンの取得と配置（150x150px）
        icon_img = self.get_weather_icon(icon_code, size = 150)
        if icon_img:
            # E-Inkは1=白、0=黒
            image_black.paste(icon_img, (20, 100))

        # 現在気温（大きく表示、64ptの太字）
        temp_str = f"{temp:.1f}°C"
        draw_black.text((180, 110), temp_str, font = self.fonts.get('huge'), fill = 0)
        # 天気説明文
        draw_black.text((180, 210), desc, font = self.fonts.get('medium'), fill = 0)

        # 3. 日出・日没・月齢（右上）
        sunrise_ts = current.get('sunrise', 0)
        sunset_ts = current.get('sunset', 0)
        # 月齢の計算（0-29.5日）
        # APIのmoon_phaseは0-1の値（0=新月、0.5=満月）
        moon_phase = daily_today.get('moon_phase', 0)
        moon_age = moon_phase * 29.53  # 朔望周期: 29.53日

        self.draw_sun_moon_rich(
            image_black, draw_black, 450, 20, sunrise_ts, sunset_ts, moon_age, tz_offset
        )

        # 4. 詳細統計情報（右中央）
        humidity = current.get('humidity', 0)  # 湿度(%)
        pressure = current.get('pressure', 0)  # 気圧(hPa)
        wind_speed = current.get('wind_speed', 0)  # 風速(m/s)
        uvi = current.get('uvi', 0)  # UVインデックス

        stats_x = 450
        stats_y = 150
        font_stats = self.fonts.get('medium')
        draw_black.text((stats_x, stats_y),
                        f"{self.i18n('Humidity')}: {humidity}%",
                        font = font_stats,
                        fill = 0)
        draw_black.text((stats_x, stats_y + 35),
                        f"{self.i18n('Pressure')}: {pressure}hPa",
                        font = font_stats,
                        fill = 0)
        draw_black.text((stats_x, stats_y + 70),
                        f"{self.i18n('Wind')}: {wind_speed}m/s",
                        font = font_stats,
                        fill = 0)
        draw_black.text((stats_x, stats_y + 105),
                        f"{self.i18n('UV Index')}: {uvi}",
                        font = font_stats,
                        fill = 0)

        # セパレーター線（上部と下部の区切り）
        draw_black.line((20, 320, 780, 320), fill = 0, width = 3)

        # 5. 5日間予報（下部）
        daily = weather_data.get('daily', [])
        start_y = 340
        col_width = (self.width - 40) // 5  # 5列に均等分割

        for i, day in enumerate(daily[:5]):  # 今日 + 4日間 = 5日間
            x = 20 + i * col_width
            dt = datetime.utcfromtimestamp(day.get('dt', 0) + tz_offset)
            day_name_en = dt.strftime("%a")  # 曜日（Mon, Tue, ...）
            day_name = self.i18n(day_name_en)  # 翻訳（月、火、...）
            d_temp_max = day.get('temp', {}).get('max', 0)  # 最高気温
            d_temp_min = day.get('temp', {}).get('min', 0)  # 最低気温
            d_icon = day.get('weather', [{}])[0].get('icon', '')

            # 曜日
            draw_black.text((x + 10, start_y), day_name, font = self.fonts.get('medium'), fill = 0)

            # 小さい天気アイコン（60x60px）
            d_icon_img = self.get_weather_icon(d_icon, size = 60)
            if d_icon_img:
                image_black.paste(d_icon_img, (x + 10, start_y + 30))

            # 最高気温（赤色で強調）/ 最低気温（黒色）
            draw_red.text((x + 10, start_y + 100),
                          f"{d_temp_max:.0f}°",
                          font = self.fonts.get('medium'),
                          fill = 0)
            draw_black.text((x + 80, start_y + 100),
                            f"{d_temp_min:.0f}°",
                            font = self.fonts.get('medium'),
                            fill = 0)

        return image_black, image_red

    def get_weather_icon(self, code, size):
        """
        天気アイコンのダウンロード、キャッシング、E-Ink用処理

        OpenWeather公式の天気アイコンをダウンロードし、ローカルに
        キャッシュ。E-Ink用に1bit（白黒）画像に変換。

        Args:
            code (str): アイコンコード（例: '01d', '10n'）
                - 01d: 晴天（昼）, 01n: 晴天（夜）
                - 10d: 雨, 13d: 雪, etc.
            size (int): 最終的なアイコンサイズ（ピクセル）

        Returns:
            PIL.Image | None: 1bit画像（失敗時はNone）

        処理フロー:
            1. キャッシュディレクトリに既存ファイルがあるかチェック
            2. なければOpenWeather公式サイトからダウンロード（4x = 200x200px）
            3. 指定サイズにリサイズ（Lanczos補間）
            4. アルファチャネルを使って透明部分を白背景に合成
            5. グレースケール化→2値化（閾値128）

        キャッシュ:
            - パス: cache/icons/{code}.png
            - 有効期限: なし（永続）
        """
        filename = f"{code}.png"
        path = os.path.join(self.cache_dir, filename)

        # キャッシュにない場合はダウンロード
        if not os.path.exists(path):
            url = f"https://openweathermap.org/img/wn/{code}@4x.png"  # 4x = 200x200
            try:
                resp = requests.get(url, timeout = 10)
                if resp.status_code == 200:
                    with open(path, 'wb') as f:
                        f.write(resp.content)
                    logging.info(f"Downloaded icon: {code}")
                else:
                    return None
            except Exception as e:
                logging.error(f"Failed to download icon {code}: {e}")
                return None

        # E-Ink用に画像処理
        try:
            img = Image.open(path)

            # 1. リサイズ（Lanczos補間で高品質）
            img = img.resize((size, size), Image.LANCZOS)

            # 2. アルファチャネル処理（透明→白背景）
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 白背景画像を作成
            bg = Image.new('RGB', img.size, (255, 255, 255))
            # アルファチャネル（split()[3]）をマスクとして合成
            bg.paste(img, mask = img.split()[3])

            # 3. 1bit画像に変換（E-Ink用）
            # グレースケール化
            bw = bg.convert('L')
            # 閾値128で2値化（0-127=黒、128-255=白）
            bw = bw.point(lambda x: 0 if x < 128 else 255, '1')

            return bw
        except Exception as e:
            logging.error(f"Error processing icon {code}: {e}")
            return None

    def draw_sun_moon_rich(self, image, draw, x, y, sunrise, sunset, moon_age, timezone_offset = 0):
        """
        日出・日没・月齢情報を描画

        Args:
            image (PIL.Image): 描画対象の画像（月アイコンを貼り付け）
            draw (ImageDraw.Draw): 描画コンテキスト（テキスト描画）
            x (int): 描画開始X座標
            y (int): 描画開始Y座標
            sunrise (int): 日出時刻（UNIXタイムスタンプ）
            sunset (int): 日没時刻（UNIXタイムスタンプ）
            moon_age (float): 月齢（0-29.5日）
            timezone_offset (int): タイムゾーンオフセット（秒）

        レイアウト:
            - (x, y): "Sunrise" ラベル + 時刻
            - (x+80, y): "Sunset" ラベル + 時刻
            - (x+200, y): 月アイコン + "Age: XX.X"
        """

        # タイムスタンプ→時刻文字列変換のヘルパー関数
        def fmt_ts(ts):
            if not ts:
                return "--:--"
            return datetime.utcfromtimestamp(ts + timezone_offset).strftime("%H:%M")

        sr_time = fmt_ts(sunrise)
        ss_time = fmt_ts(sunset)

        # 月アイコンの位置（右寄せ）
        moon_x = x + 200
        moon_y = y + 10

        # 月アイコンの生成と貼り付け
        moon_size = 100
        moon_img = self.generate_moon_icon(moon_age, moon_size)

        if moon_img:
            image.paste(moon_img, (moon_x, moon_y))

        # テキスト描画
        font_sm = self.fonts.get('small')
        font_md = self.fonts.get('medium')

        # 日出時刻
        draw.text((x, y + 10), self.i18n("Sunrise"), font = font_sm, fill = 0)
        draw.text((x, y + 30), sr_time, font = font_md, fill = 0)

        # 日没時刻
        draw.text((x + 80, y + 10), self.i18n("Sunset"), font = font_sm, fill = 0)
        draw.text((x + 80, y + 30), ss_time, font = font_md, fill = 0)

        # 月齢
        draw.text((moon_x, y + 110),
                  f"{self.i18n('Age')}: {moon_age:.1f}",
                  font = font_sm,
                  fill = 0,
                  align = "center")

    def generate_moon_icon(self, age, size):
        """
        月齢に応じた月アイコンを動的生成

        月齢（0-29.5日）から月の満ち欠けを幾何学的に計算して
        アイコン画像を生成。

        Args:
            age (float): 月齢（日数）
                - 0: 新月
                - 7.4: 上弦の月
                - 14.8: 満月
                - 22.1: 下弦の月
            size (int): 最終的なアイコンサイズ（ピクセル）

        Returns:
            PIL.Image: 1bit画像（月アイコン）

        アルゴリズム:
            1. 200x200の大きめのキャンバスで描画（アンチエイリアス用）
            2. 月の輪郭（円）を描画
            3. 月齢に応じた影を三角関数で計算
                - theta = age / 14.765 * π
                - 各Y座標について、X方向の影の範囲を計算
                - age < 15: 左側から影（新月→満月）
                - age >= 15: 右側から影（満月→新月）
            4. 指定サイズにリサイズ
            5. 1bit画像に変換

        Note:
            WeatherPi/modules/WeatherModule.py から移植
        """
        # アンチエイリアス用に大きめのキャンバス
        _size = 200
        radius = _size // 2

        # L mode: 8bitグレースケール（255=白、0=黒）
        image = Image.new("L", (_size + 2, _size + 2), 255)
        draw = ImageDraw.Draw(image)

        # 月の輪郭（満月の円）
        draw.ellipse([(1, 1), (_size, _size)], outline = 0, width = 2)

        # 影の計算
        # 月齢 0-29.5日 → theta角度
        # 14.765 = 朔望周期の半分（29.53 / 2）
        theta = age / 14.765 * math.pi

        # Y座標ごとに影を描画
        for y in range(-radius, radius, 1):
            try:
                # 円の方程式から影の範囲を計算
                # 定義域エラー防止（acos用）
                val = y / radius
                if val < -1:
                    val = -1
                if val > 1:
                    val = 1

                alpha = math.acos(val)
                x = radius * math.sin(alpha)
                length = radius * math.cos(theta) * math.sin(alpha)

                # 月齢に応じて影の方向を変更
                if age < 15:
                    # 新月→満月: 左から影が消える
                    start = (radius - x + 1, radius + y + 1)
                    end = (radius + length + 1, radius + y + 1)
                else:
                    # 満月→新月: 右から影が増える
                    start = (radius - length + 1, radius + y + 1)
                    end = (radius + x + 1, radius + y + 1)

                # 影を黒線で描画
                draw.line((start, end), fill = 0, width = 2)
            except Exception:
                # 計算エラー時はスキップ
                continue

        # リサイズ（Lanczos補間）
        image = image.resize((size, size), Image.LANCZOS)

        # 1bit画像に変換
        return image.convert('1')

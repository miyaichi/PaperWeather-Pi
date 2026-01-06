"""
Renderer - 画像レンダリングモジュール (Headless Chrome版)
===================================================
天気データをHTML/CSSで構築し、Headless Chromeでレンダリングして
E-Ink用の2色（黒/赤）画像に変換する。
"""

import io
import logging
import math
import os
from datetime import datetime

import requests
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from i18n import I18n
from eink_converter import EInkConverter


class Renderer:
    """
    天気データを画像にレンダリングするクラス

    Attributes:
        config (dict): 設定情報
        width (int): 幅
        height (int): 高さ
        driver (webdriver.Chrome): Selenium WebDriver
    """

    def __init__(self, config):
        self.config = config
        self.width = config['display']['width']
        self.height = config['display']['height']

        # 国際化
        locale = config.get('locale', 'en_US')
        self.i18n = I18n(locale)

        # パス設定
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.cache_dir = os.path.join(self.base_dir, 'cache', 'icons')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        # Jinja2設定
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self.jinja_env = Environment(loader = FileSystemLoader(template_dir))

        # Selenium初期化
        self.driver = self._init_driver()

        # アイコンコンバーター初期化
        self.icon_converter = EInkConverter()

    def _init_driver(self):
        """Selenium WebDriverの初期化"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--hide-scrollbars')
        options.add_argument(f'--window-size={self.width},{self.height}')

        # ログ抑制
        options.add_argument("--log-level=3")

        try:
            # webdriver_managerでドライバを自動取得
            # try finding existing chromedriver first or use manager
            try:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service = service, options = options)
            except Exception:  # pylint: disable=broad-except
                # Should fallback to system one if manager fails (e.g. on different arch/offline)
                driver = webdriver.Chrome(options = options)

            logging.info("Selenium WebDriver initialized successfully.")
            return driver
        except Exception as e:
            logging.error(f"Critical: Could not initialize Selenium WebDriver: {e}")
            # エラー時もNoneを返さず例外送出の方がよいが、呼び出し元の安全性を考慮してError Image用のダミーまたは再試行ロジックが必要
            # ここでは例外を投げる
            raise e

    def __del__(self):
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
            except Exception:  # pylint: disable=broad-except
                pass

    def render(self, weather_data):
        """
        天気データをHTML→スクリーンショット→2色画像に変換

        Returns:
            tuple: (image_black, image_red)
        """
        if not weather_data:
            return self._create_error_image()

        try:
            # 1. コンテキスト作成（データ加工）
            context = self._prepare_context(weather_data)

            # 2. CSS生成
            css_template = self.jinja_env.get_template('style.css')
            css_content = css_template.render(width = self.width, height = self.height)

            # CSS保存（cache/style.css）
            css_path = os.path.join(self.base_dir, 'cache', 'style.css')
            with open(css_path, 'w', encoding = 'utf-8') as f:
                f.write(css_content)

            # 3. HTML生成
            template = self.jinja_env.get_template('weather.html')
            html_content = template.render(**context)

            # 4. HTML保存（cache/render.html）
            html_path = os.path.join(self.base_dir, 'cache', 'render.html')
            with open(html_path, 'w', encoding = 'utf-8') as f:
                f.write(html_content)

            # 5. ブラウザで開く
            url = f"file://{html_path}"
            self.driver.get(url)

            # レンダリング待ち（HTMLが大きければ待つ必要があるが、ローカルファイルなので基本即時）
            # フォント読み込み等で遅延がある場合は time.sleep(0.5) を検討

            # 6. スクリーンショット取得
            # body要素をキャプチャして余計な余白を排除
            body = self.driver.find_element("tag name", "body")
            png_data = body.screenshot_as_png

            img = Image.open(io.BytesIO(png_data)).convert('RGB')

            # サイズ強制（念のため）
            if img.size != (self.width, self.height):
                img = img.resize((self.width, self.height))

            # 7. 色分解（黒/赤）
            return self._process_image_colors(img)

        except Exception as e:
            logging.exception(f"Render failed: {e}")
            return self._create_error_image()

    def _prepare_context(self, data):
        """テンプレート用のデータを辞書にまとめる"""
        current = data.get('current', {})
        daily_today = data.get('daily', [{}])[0]
        tz_offset = data.get('timezone_offset', 0)

        # 日時
        ts = current.get('dt', 0)
        dt = datetime.utcfromtimestamp(ts + tz_offset)
        day_en = dt.strftime("%a")
        day_loc = self.i18n(day_en)

        # 月齢
        moon_phase = daily_today.get('moon_phase', 0)
        moon_age = moon_phase * 29.53

        # アイコン準備 (パスを取得)
        main_icon_code = current.get('weather', [{}])[0].get('icon', '01d')
        main_icon_path = self._ensure_icon(main_icon_code)

        moon_icon_path = self._generate_moon_icon_file(moon_age)

        # 5日間予報
        forecast_days = []
        for day in data.get('daily', [])[:5]:
            d_ts = day.get('dt', 0)
            d_dt = datetime.utcfromtimestamp(d_ts + tz_offset)
            d_day_en = d_dt.strftime("%a")
            d_icon = day.get('weather', [{}])[0].get('icon', '')

            forecast_days.append({
                'day_name': self.i18n(d_day_en),
                'icon_path': self._ensure_icon(d_icon),
                'max_temp': round(day.get('temp', {}).get('max', 0)),
                'min_temp': round(day.get('temp', {}).get('min', 0))
            })

        # コンテキスト辞書
        return {
            'date_str': dt.strftime(f"%Y/%m/%d ({day_loc})"),
            'time_str': dt.strftime("%H:%M"),
            'sunrise_label': self.i18n("Sunrise"),
            'sunrise_time': self._fmt_time(current.get('sunrise'), tz_offset),
            'sunset_label': self.i18n("Sunset"),
            'sunset_time': self._fmt_time(current.get('sunset'), tz_offset),
            'moon_icon_path': moon_icon_path,
            'moon_age_label': self.i18n("Age"),
            'moon_age_value': f"{moon_age:.1f}",
            'main_icon_path': main_icon_path,
            'current_temp': f"{current.get('temp', 0):.1f}°C",
            'description': current.get('weather', [{}])[0].get('description', ''),
            'humidity_label': self.i18n("Humidity"),
            'humidity_val': current.get('humidity', 0),
            'pressure_label': self.i18n("Pressure"),
            'pressure_val': current.get('pressure', 0),
            'wind_label': self.i18n("Wind"),
            'wind_val': current.get('wind_speed', 0),
            'uvi_label': self.i18n("UV Index"),
            'uvi_val': current.get('uvi', 0),
            'forecast_days': forecast_days
        }

    def _fmt_time(self, ts, offset):
        if not ts: return "--:--"
        return datetime.utcfromtimestamp(ts + offset).strftime("%H:%M")

    def _ensure_icon(self, code):
        """OpenWeatherアイコンをダウンロードし、3色E-Ink用に変換して絶対パスを返す"""
        base_filename = f"{code}.png"
        base_path = os.path.join(self.cache_dir, base_filename)

        eink_filename = f"{code}_eink.png"
        eink_path = os.path.join(self.cache_dir, eink_filename)

        # 既に変換済みならそのパスを返す
        if os.path.exists(eink_path):
            return eink_path

        # 原本がなければダウンロード
        if not os.path.exists(base_path):
            url = f"https://openweathermap.org/img/wn/{code}@4x.png"
            try:
                resp = requests.get(url, timeout = 10)
                if resp.status_code == 200:
                    with open(base_path, 'wb') as f:
                        f.write(resp.content)
            except Exception as e:
                logging.error(f"Icon download failed {code}: {e}")
                return base_path  # 失敗したら仕方ないのでbase_pathを返す（存在しなくても）

        # 変換実行
        if os.path.exists(base_path):
            try:
                self.icon_converter.convert(base_path, eink_path)
                return eink_path
            except Exception as e:
                logging.error(f"Icon conversion failed {code}: {e}")
                return base_path

        return base_path

    def _generate_moon_icon_file(self, age):
        """月齢アイコンを生成して保存し、パスを返す"""
        path = os.path.join(self.cache_dir, "moon_current.png")

        # 描画ロジックは既存のものを流用・簡略化
        size = 200
        radius = size // 2

        # 背景透明、白黒描画
        # 今回はブラウザで表示するため、白背景に黒で描画する
        image = Image.new("RGB", (size, size), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # 輪郭
        draw.ellipse([(1, 1), (size - 2, size - 2)], outline = (0, 0, 0), width = 2)

        # 影
        theta = age / 14.765 * math.pi
        for y in range(-radius, radius, 1):
            try:
                val = y / radius
                if val < -1: val = -1
                if val > 1: val = 1
                alpha = math.acos(val)
                x = radius * math.sin(alpha)
                length = radius * math.cos(theta) * math.sin(alpha)

                if age < 15:
                    start = (radius - x, radius + y)
                    end = (radius + length, radius + y)
                else:
                    start = (radius - length, radius + y)
                    end = (radius + x, radius + y)

                draw.line((start, end), fill = (0, 0, 0), width = 2)
            except Exception:  # pylint: disable=broad-except
                continue

        image.save(path)
        return path

    def _process_image_colors(self, img):
        """RGB画像を黒・赤の2つの1bit画像に分解する"""
        width, height = img.size

        # 出力用画像 (1=白, 0=描画色)
        img_black = Image.new('1', (width, height), 1)
        img_red = Image.new('1', (width, height), 1)

        pixels = img.load()
        pixels_blk = img_black.load()
        pixels_red = img_red.load()

        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]

                # 赤色判定 (赤が強く、緑青が弱い)
                # 例: rgb(255, 0, 0) -> R>200, G<100, B<100
                if r > 180 and g < 100 and b < 100:
                    pixels_red[x, y] = 0  # 赤レイヤーに描画
                    pixels_blk[x, y] = 1  # 黒レイヤーは白
                # 黒色判定 (輝度が低い)
                # ITU-R BT.601の輝度計算式を使用（人間の視覚特性を考慮）
                # 緑に敏感(0.587)、赤に中程度(0.299)、青に鈍感(0.114)
                else:
                    luminance = 0.299 * r + 0.587 * g + 0.114 * b
                    if luminance < 128:
                        pixels_blk[x, y] = 0  # 黒レイヤーに描画
                        pixels_red[x, y] = 1  # 赤レイヤーは白
                    else:
                        # 白
                        pixels_blk[x, y] = 1
                        pixels_red[x, y] = 1

        return img_black, img_red

    def _create_error_image(self):
        """エラー時の画像生成"""
        img = Image.new('1', (self.width, self.height), 1)
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Renderer Error", fill = 0)
        return img, Image.new('1', (self.width, self.height), 1)

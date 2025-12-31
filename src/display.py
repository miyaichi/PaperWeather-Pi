"""
EInkDisplay - E-Inkディスプレイ制御モジュール
=========================================
Waveshare E-Inkディスプレイの制御とシミュレーションモード対応

対応ハードウェア:
- Waveshare 7.5inch e-Paper HAT (B) V2 (黒/白/赤の3色)
- 解像度: 800x480ピクセル

動作モード:
1. E-Inkモード: 実際のハードウェアに表示
2. シミュレーションモード: PNG画像ファイルに出力（開発環境用）
"""

import logging

# Waveshareライブラリのインポート試行（なければシミュレーションモード）
try:
    # 実際のE-Inkディスプレイ用ドライバ
    # Raspberry Piにwaveshare-epdがインストールされている場合のみ使用
    from waveshare_epd import epd7in5b_V2
    HAS_EINK = True
except ImportError:
    # 開発環境（macOSなど）ではライブラリがないため、シミュレーションモード
    HAS_EINK = False
    logging.warning("Waveshare E-Ink library not found. Running in simulation mode.")


class EInkDisplay:
    """
    E-Inkディスプレイ制御クラス（ハードウェア抽象化レイヤー）

    waveshare-epdライブラリの有無を自動検出し、以下のモードを切り替え:
    - E-Inkモード: 実際のディスプレイに表示
    - シミュレーションモード: PNG画像ファイルに出力

    E-Inkディスプレイの特性:
        - 電源オフ時も表示が保持される（不揮発性）
        - 更新時のみ電力消費（低消費電力）
        - 更新速度は遅い（数秒）
        - 3色対応（黒、白、赤）

    シミュレーションモード出力ファイル:
        - screen_black.png: 黒色ピクセルレイヤー（1bit画像）
        - screen_red.png: 赤色ピクセルレイヤー（1bit画像）
        - screen_preview.png: 合成プレビュー（RGB画像）

    Attributes:
        width (int): ディスプレイ幅（ピクセル）
        height (int): ディスプレイ高さ（ピクセル）
        epd: Waveshare EPDドライバインスタンス（E-Inkモード時のみ）
        has_eink (bool): E-Inkドライバが利用可能かどうか
    """

    def __init__(self, width = 800, height = 480):
        """
        EInkDisplayの初期化

        Args:
            width (int): ディスプレイ幅（デフォルト: 800）
            height (int): ディスプレイ高さ（デフォルト: 480）
        """
        self.width = width
        self.height = height
        self.epd = None
        self.has_eink = HAS_EINK

        # E-Inkドライバが利用可能な場合、初期化を試行
        if self.has_eink:
            try:
                self.epd = epd7in5b_V2.EPD()
                logging.info("E-Ink driver initialized.")
            except Exception as e:
                logging.error(f"Failed to init E-Ink driver: {e}")
                # ドライバ初期化失敗時はシミュレーションモードにフォールバック
                self.has_eink = False

    def init(self):
        """
        ディスプレイの初期化

        E-Inkモード: ハードウェアを初期化（電源オン、設定読み込み）
        シミュレーションモード: ログ出力のみ

        Note:
            E-Inkディスプレイは使用前に必ず初期化が必要
        """
        if self.has_eink and self.epd:
            logging.info("Initializing E-Ink display Hardware...")
            self.epd.init()
        else:
            logging.info("Simulation: initializing display.")

    def clear(self):
        """
        ディスプレイのクリア（全面白色化）

        E-Inkモード: ディスプレイを白色でクリア
        シミュレーションモード: ログ出力のみ

        Note:
            E-Inkディスプレイは焼き付き防止のため、定期的なクリアが推奨される
        """
        if self.has_eink and self.epd:
            logging.info("Clearing E-Ink display...")
            self.epd.Clear()
        else:
            logging.info("Simulation: clearing display.")

    def sleep(self):
        """
        ディスプレイをスリープモードに移行

        E-Inkモード: ディスプレイを低消費電力モードに（表示内容は保持）
        シミュレーションモード: ログ出力のみ

        Note:
            E-Inkディスプレイは表示更新後、必ずスリープさせることで
            電力消費を最小化し、ディスプレイの寿命を延ばす
        """
        if self.has_eink and self.epd:
            logging.info("Sleeping E-Ink display...")
            self.epd.sleep()
        else:
            logging.info("Simulation: sleeping display.")

    def display(self, image_black, image_red = None):
        """
        画像をディスプレイに表示

        E-Inkモード: 実際のディスプレイに画像を転送して表示
        シミュレーションモード: PNG画像ファイルに出力

        Args:
            image_black (PIL.Image): 黒色ピクセル用の1bit画像
                - モード '1' (1bit)
                - 0=黒ピクセル、1=白ピクセル
            image_red (PIL.Image, optional): 赤色ピクセル用の1bit画像
                - モード '1' (1bit)
                - 0=赤ピクセル、1=白ピクセル

        E-Inkの色合成ルール:
            - 黒レイヤー=0, 赤レイヤー=1 → 黒
            - 黒レイヤー=1, 赤レイヤー=0 → 赤
            - 黒レイヤー=1, 赤レイヤー=1 → 白

        シミュレーションモード出力:
            - screen_black.png: 黒色レイヤー
            - screen_red.png: 赤色レイヤー
            - screen_preview.png: 黒と赤を合成したプレビュー画像
        """
        if self.has_eink and self.epd:
            logging.info("Sending buffer to E-Ink display...")
            # PIL ImageをWaveshareドライバ用のバイトバッファに変換
            buffer_black = self.epd.getbuffer(image_black)
            buffer_red = self.epd.getbuffer(image_red) if image_red else None
            # ディスプレイに転送して表示（この処理に数秒かかる）
            self.epd.display(buffer_black, buffer_red)
        else:
            # シミュレーションモード: PNG画像に保存
            logging.info("Simulation: Saving 'screen_black.png' and 'screen_red.png'...")
            # 各レイヤーを個別に保存
            image_black.save("screen_black.png")
            if image_red:
                image_red.save("screen_red.png")

            # プレビュー画像の生成（黒と赤を合成したRGB画像）
            try:
                from PIL import Image, ImageOps

                # 白背景のRGB画像を作成
                preview = Image.new("RGB", (self.width, self.height), "white")
                # 黒レイヤーを貼り付け（1bit→RGB変換）
                preview.paste(image_black.convert("1").convert("RGB"), (0, 0))

                # 赤レイヤーがある場合、合成
                if image_red:
                    # 赤マスク（0と1を反転）
                    red_mask = ImageOps.invert(image_red.convert("L"))
                    # 赤色レイヤー（RGBA形式、完全な赤）
                    red_layer = Image.new("RGBA", image_red.size, (255, 0, 0, 255))
                    # マスクを使って赤レイヤーを貼り付け
                    preview.paste(red_layer, (0, 0), red_mask)

                # プレビュー画像を保存
                preview.save("screen_preview.png")
                logging.info("Simulation preview saved to 'screen_preview.png'.")
            except Exception:
                logging.debug("Failed to build simulation preview.")

#!/usr/bin/env python3
"""
E-Ink Display用天気アイコン変換ツール - 改良版
赤・白・黒の3色に変換し、パラメータ調整が可能
"""

from PIL import Image, ImageFilter
import logging
import numpy as np
import argparse
import os


class EInkConverter:
    """E-Ink Display用画像変換クラス"""

    def __init__(
        self,
        red_hue_range = (0, 30),  # 赤の色相範囲
        red_saturation_min = 50,  # 赤の彩度最小値
        dark_threshold = 128,  # 黒判定の明度閾値
        outline_width = 2,  # 縁取り幅
        use_anti_alias = True
    ):  # アンチエイリアス使用
        """
        Args:
            red_hue_range: 赤と判定する色相範囲 (0-360度)
            red_saturation_min: 赤と判定する最小彩度 (0-255)
            dark_threshold: この明度以下を黒とする (0-255)
            outline_width: 縁取りの太さ（ピクセル）
            use_anti_alias: アンチエイリアス処理を使用
        """
        self.red_hue_range = red_hue_range
        self.red_saturation_min = red_saturation_min
        self.dark_threshold = dark_threshold
        self.outline_width = outline_width
        self.use_anti_alias = use_anti_alias

    def rgb_to_hsv(self, r, g, b):
        """RGB値をHSV値に変換"""
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val

        # Hue
        if diff == 0:
            h = 0
        elif max_val == r:
            h = (60 * ((g - b) / diff) + 360) % 360
        elif max_val == g:
            h = (60 * ((b - r) / diff) + 120) % 360
        else:
            h = (60 * ((r - g) / diff) + 240) % 360

        # Saturation
        s = 0 if max_val == 0 else (diff / max_val) * 255

        # Value
        v = max_val * 255

        return h, s, v

    def is_red(self, r, g, b):
        """ピクセルが赤系かどうか判定"""
        h, s, v = self.rgb_to_hsv(r, g, b)

        # 色相が赤の範囲内で、十分な彩度がある
        h_min, h_max = self.red_hue_range
        in_hue_range = (h >= h_min and h <= h_max) or (h >= 360 - h_max and h <= 360)

        return in_hue_range and s >= self.red_saturation_min and v >= 50

    def convert(self, input_path, output_path = None):
        """
        画像を変換
        
        Args:
            input_path: 入力画像パス
            output_path: 出力画像パス（Noneの場合は自動生成）
        
        Returns:
            変換後のPIL Image
        """
        # 出力パスの自動生成
        if output_path is None:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_eink.png"

        # 画像読み込み
        img = Image.open(input_path).convert('RGBA')
        width, height = img.size

        # アンチエイリアス用の拡大
        if self.use_anti_alias:
            scale = 2
            img = img.resize((width * scale, height * scale), Image.Resampling.LANCZOS)
            scaled_width, scaled_height = img.size
        else:
            scale = 1
            scaled_width, scaled_height = width, height

        img_array = np.array(img)

        # マスク作成
        red_mask = np.zeros((scaled_height, scaled_width), dtype = bool)
        black_mask = np.zeros((scaled_height, scaled_width), dtype = bool)
        white_content_mask = np.zeros((scaled_height, scaled_width), dtype = bool)

        for y in range(scaled_height):
            for x in range(scaled_width):
                r, g, b, a = img_array[y, x]

                # 透明部分はスキップ
                if a < 128:
                    continue

                # 赤系の判定
                if self.is_red(r, g, b):
                    red_mask[y, x] = True
                else:
                    # 明度計算
                    luminance = int(0.299 * r + 0.587 * g + 0.114 * b)

                    if luminance < self.dark_threshold:
                        black_mask[y, x] = True
                    else:
                        white_content_mask[y, x] = True

        # 縁取り生成
        outline_mask = self._create_outline(white_content_mask)

        # 最終画像生成
        output_array = np.ones((scaled_height, scaled_width, 3), dtype = np.uint8) * 255

        # レイヤー合成
        combined_black = black_mask | outline_mask
        output_array[combined_black] = [0, 0, 0]
        output_array[red_mask] = [255, 0, 0]

        result = Image.fromarray(output_array)

        # 元のサイズに戻す
        if self.use_anti_alias:
            result = result.resize((width, height), Image.Resampling.LANCZOS)

        result.save(output_path)
        logging.info("Conversion complete: {}".format(output_path))

        return result

    def _create_outline(self, content_mask):
        """縁取りマスク生成"""
        mask_img = Image.fromarray((content_mask * 255).astype(np.uint8))

        # 膨張処理
        kernel_size = self.outline_width * 2 + 1
        dilated = mask_img.filter(ImageFilter.MaxFilter(kernel_size))

        dilated_array = np.array(dilated) > 128
        outline = dilated_array & ~content_mask

        return outline


def create_preview_grid(image_paths, output_path):
    """
    複数の画像をグリッド表示
    
    Args:
        image_paths: 画像パスのリスト
        output_path: 出力パス
    """
    images = [Image.open(p).convert('RGB') for p in image_paths]

    # グリッドサイズ計算
    n = len(images)
    cols = min(4, n)
    rows = (n + cols - 1) // cols

    # 最大サイズを取得
    max_w = max(img.width for img in images)
    max_h = max(img.height for img in images)

    # グリッド画像作成
    padding = 10
    grid_width = cols * max_w + (cols + 1) * padding
    grid_height = rows * max_h + (rows + 1) * padding

    grid = Image.new('RGB', (grid_width, grid_height), (240, 240, 240))

    for i, img in enumerate(images):
        row = i // cols
        col = i % cols

        x = col * max_w + (col + 1) * padding
        y = row * max_h + (row + 1) * padding

        # 中央寄せ
        x += (max_w - img.width) // 2
        y += (max_h - img.height) // 2

        grid.paste(img, (x, y))

    grid.save(output_path)
    print(f"✓ プレビューグリッド作成: {output_path}")
    return grid


def main():
    parser = argparse.ArgumentParser(description = 'E-Ink Display用天気アイコン変換ツール')
    parser.add_argument('input', nargs = '+', help = '入力画像ファイル')
    parser.add_argument('-o', '--output-dir', default = '/mnt/user-data/outputs', help = '出力ディレクトリ')
    parser.add_argument(
        '--red-hue', type = int, nargs = 2, default = [0, 30], help = '赤の色相範囲 (0-360度)'
    )
    parser.add_argument('--red-sat', type = int, default = 50, help = '赤の最小彩度 (0-255)')
    parser.add_argument('--dark-threshold', type = int, default = 128, help = '黒判定の明度閾値 (0-255)')
    parser.add_argument('--outline-width', type = int, default = 2, help = '縁取りの太さ（ピクセル）')
    parser.add_argument('--no-anti-alias', action = 'store_true', help = 'アンチエイリアスを無効化')
    parser.add_argument('--preview', action = 'store_true', help = 'プレビューグリッドを生成')

    args = parser.parse_args()

    # 出力ディレクトリ作成
    os.makedirs(args.output_dir, exist_ok = True)

    # コンバーター作成
    converter = EInkConverter(
        red_hue_range = tuple(args.red_hue),
        red_saturation_min = args.red_sat,
        dark_threshold = args.dark_threshold,
        outline_width = args.outline_width,
        use_anti_alias = not args.no_anti_alias
    )

    print("\nE-Ink Display変換設定:")
    print(f"  赤色相範囲: {args.red_hue[0]}-{args.red_hue[1]}度")
    print(f"  赤最小彩度: {args.red_sat}")
    print(f"  暗部閾値: {args.dark_threshold}")
    print(f"  縁取り幅: {args.outline_width}px")
    print(f"  アンチエイリアス: {'ON' if not args.no_anti_alias else 'OFF'}")
    print()

    # 変換実行
    output_paths = []
    for input_path in args.input:
        basename = os.path.basename(input_path)
        name, _ = os.path.splitext(basename)
        output_path = os.path.join(args.output_dir, f"{name}_eink.png")

        converter.convert(input_path, output_path)
        output_paths.append(output_path)

    # プレビューグリッド作成
    if args.preview and len(output_paths) > 1:
        preview_path = os.path.join(args.output_dir, 'preview_grid.png')
        create_preview_grid(output_paths, preview_path)

    print(f"\n✅ 全{len(output_paths)}ファイルの変換完了")


if __name__ == "__main__":
    # コマンドライン引数がない場合はデフォルト実行
    import sys
    if len(sys.argv) == 1:
        sys.argv.extend([
            '/mnt/user-data/uploads/02d.png', '/mnt/user-data/uploads/13n.png', '--preview'
        ])

    main()

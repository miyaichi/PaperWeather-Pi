"""
i18n - 国際化（Internationalization）モジュール
==============================================
JSONベースの軽量翻訳システム

機能:
- ロケール別の翻訳ファイル読み込み
- テキストの自動翻訳
- フォールバック機能（翻訳がない場合は元のテキストを返す）

サポートするロケール:
- ja_JP: 日本語
- en_US: 英語（デフォルト）
"""

import json
import logging
import os


class I18n:
    """
    国際化（i18n）クラス

    指定されたロケールに基づいてテキストを翻訳する。
    翻訳ファイルはJSON形式で、locale/{locale}/messages.jsonに配置。

    Attributes:
        locale (str): 現在のロケール（例: 'ja_JP', 'en_US'）
        translations (dict): 翻訳辞書
        locale_dir (str): localeディレクトリのパス
    """

    def __init__(self, locale = 'en_US'):
        """
        I18nの初期化

        Args:
            locale (str): ロケール（デフォルト: 'en_US'）
                - 'ja_JP': 日本語
                - 'en_US': 英語
        """
        self.locale = locale
        self.translations = {}

        # localeディレクトリのパス（プロジェクトルート/locale）
        self.locale_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locale')

        self._load_translations()

    def _load_translations(self):
        """
        翻訳ファイルを読み込む（プライベートメソッド）

        locale/{locale}/messages.jsonを読み込み、
        translations辞書に格納する。

        ファイルが見つからない場合は警告を出力し、
        翻訳なし（元のテキストをそのまま返す）モードで動作。
        """
        # 翻訳ファイルのパス
        translation_file = os.path.join(self.locale_dir, self.locale, 'messages.json')

        if not os.path.exists(translation_file):
            logging.warning(
                f"Translation file not found: {translation_file}. "
                f"Using default (no translation)."
            )
            return

        try:
            with open(translation_file, 'r', encoding = 'utf-8') as f:
                self.translations = json.load(f)
            logging.info(f"Loaded translations for locale: {self.locale}")
        except Exception as e:
            logging.error(f"Failed to load translation file: {e}")

    def translate(self, text):
        """
        テキストを翻訳

        Args:
            text (str): 翻訳元のテキスト（英語）

        Returns:
            str: 翻訳されたテキスト（翻訳がない場合は元のテキスト）

        Examples:
            >>> i18n = I18n('ja_JP')
            >>> i18n.translate('Sunrise')
            '日の出'
            >>> i18n.translate('Unknown Text')
            'Unknown Text'  # 翻訳がない場合は元のテキスト
        """
        # 翻訳辞書から検索、なければ元のテキストを返す
        return self.translations.get(text, text)

    def __call__(self, text):
        """
        翻訳のショートカット

        i18n('Text')の形式で翻訳可能にする。

        Args:
            text (str): 翻訳元のテキスト

        Returns:
            str: 翻訳されたテキスト

        Examples:
            >>> i18n = I18n('ja_JP')
            >>> i18n('Humidity')
            '湿度'
        """
        return self.translate(text)

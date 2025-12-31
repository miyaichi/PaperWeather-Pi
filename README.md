# PaperWeather-Pi

A weather dashboard designed for Raspberry Pi Zero 2 W and Waveshare 7.5inch E-Ink Display (Black/White/Red).
Optimized for OpenWeather API and low-power E-Ink operation.

## Hardware

- Raspberry Pi Zero 2 W
- Waveshare 7.5inch e-Paper HAT (B) (800x480 resolution)

## Software Requirements

- Python 3
- Pillow
- requests
- Waveshare e-Paper Driver (`waveshare-epd`)

## Setup

1. **Install Dependencies**

   ```bash
   pip3 install -r requirements.txt
   ```

   _Note: For the actual E-Ink display, you must install the Waveshare drivers via their official instructions or repository._

2. **Configuration**

- Copy `.env.example` to `.env` and set `OPENWEATHER_APPID` (環境変数で秘匿管理)。`.env` は起動時に自動で読み込まれます。
  - Copy `config.json.example` to `config.json` and adjust location/units/fonts as needed.
    APIキーは `.env` から読み込まれ、JSON の値が `YOUR_OPENWEATHER_APPID` の場合でも環境変数が優先されます。

3. **Running**
   Run once (for cron jobs):

   ```bash
   python3 main.py
   ```

   Run loop (daemon mode):

   ```bash
   python3 main.py --loop
   ```

## Development

- If the `waveshare-epd` library is not found (e.g., on a desktop Mac), the script runs in **Simulation Mode**.
- It saves `screen_black.png` and `screen_red.png` to the current directory instead of updating a physical screen, plus a combined `screen_preview.png`.

## Project Hygiene

- Secrets are excluded from git via `.env` and `config.json` uses placeholders.
- `.gitignore` covers caches, virtualenvs, generated preview images.
- `.prettierrc` is provided for consistent JSON/Markdown formatting.

## Project Structure

- `src/`: Source code
  - `weather.py`: API handling
  - `renderer.py`: Image generation (Pillow)
  - `display.py`: Hardware abstraction
- `main.py`: Entry point

from flask import Flask, Response
import requests
import json
import pandas as pd
import torch
from chronos import BaseChronosPipeline
import traceback
import ta

app = Flask(__name__)

model_name = "amazon/chronos-bolt-base"

try:
    pipeline = BaseChronosPipeline.from_pretrained(
        model_name,
        device_map="cpu",
        torch_dtype=torch.float32
    )
except Exception as e:
    print(f"Error al cargar el modelo: {e}")
    pipeline = None

@app.route("/inference/value/<string:token>")
def get_value_inference(token):
    if pipeline is None:
        return Response("El modelo no está cargado", status=500, mimetype='text/plain')
    try:
        df = get_binance_data(token)
        df = add_technical_indicators(df)
        context = torch.tensor(df.drop(columns=['date']).values, dtype=torch.float32)
        context = context.contiguous()
        prediction_length = 1
        forecast = pipeline.predict(context, prediction_length)
        forecast_value = forecast[0].mean().item()
        return Response(str(forecast_value), status=200, mimetype='text/plain')
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return Response(str(e), status=500, mimetype='text/plain')

@app.route("/inference/volatility/<string:token>")
def get_volatility_inference(token):
    try:
        df = get_binance_data(token)
        current_price = df["price"].iloc[-1]
        old_price = df["price"].iloc[0]
        price_change = (current_price - old_price) / old_price
        volatility_percentage = abs(price_change) * 100
        return Response(str(volatility_percentage), status=200, mimetype='text/plain')
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return Response(str(e), status=500, mimetype='text/plain')

def get_binance_data(token):
    base_url = "https://api.binance.com/api/v3/klines"
    token_map = {
        'ETH': 'ETHUSDT',
        'SOL': 'SOLUSDT',
        'BTC': 'BTCUSDT',
        'BNB': 'BNBUSDT',
        'ARB': 'ARBUSDT'
    }
    token = token.upper()
    if token in token_map:
        symbol = token_map[token]
    else:
        raise ValueError("Token no soportado")
    params = {
        'symbol': symbol,
        'interval': '5m',
        'limit': 1000
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if not data:
            raise Exception("Datos vacíos recibidos de la API de Binance")
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume",
            "ignore"
        ])
        df["date"] = pd.to_datetime(df["close_time"], unit='ms')
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df["price"] = df["close"]
        df = df[["date", "open", "high", "low", "close", "volume", "price"]]
        df = df[:-1]
        if df.empty:
            raise Exception("El dataframe de precios está vacío")
        return df
    else:
        raise Exception(f"Fallo al recuperar datos de la API de Binance: {response.text}")

def add_technical_indicators(df):
    df.set_index('date', inplace=True)
    df['SMA'] = ta.trend.SMAIndicator(close=df['close'], window=14).sma_indicator()
    df['EMA'] = ta.trend.EMAIndicator(close=df['close'], window=14).ema_indicator()
    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    macd = ta.trend.MACD(close=df['close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Hist'] = macd.macd_diff()
    df = df.dropna()
    df.reset_index(inplace=True)
    return df

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True)

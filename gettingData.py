#Name: gettingData.py
#Start running on 0614 0400
import numpy as np
import pandas as pd
import time
import websocket
import json
import os
from datetime import datetime, timezone

def get_mircoprice(best_bid_price, best_bid_qty, best_ask_price, best_ask_qty):
    total_qty = best_bid_qty + best_ask_qty
    microprice = (best_bid_price * best_bid_qty + best_ask_price * best_ask_qty)/total_qty
    return microprice

def getdata2():
    while True:
        try:
            SYMBOL = 'btcusdt'
            LEVELS = 5
            SAVE_INTERVAL = 500
            STREAM_URL = f"wss://stream.binance.com:9443/ws/{SYMBOL}@depth{LEVELS}@100ms"

            current_date = None
            output_file = None
            records = []

            def get_filename(ts_ms):
                dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                return f"live_orderbook_depth_{dt.strftime('%Y-%m-%d')}.csv"

            def on_message(ws, message):
                nonlocal records, current_date, output_file
                data = json.loads(message)

                if 'bids' not in data or 'asks' not in data:
                    print(f"Ignoring message with keys: {list(data.keys())}")
                    return

                timestamp = data.get('E', int(time.time() * 1000))

                bids = data['bids']
                asks = data['asks']

                # Ensure at least LEVELS levels
                while len(bids) < LEVELS:
                    bids.append([0, 0])
                while len(asks) < LEVELS:
                    asks.append([0, 0])

                record = {'timestamp': timestamp}
                for i in range(LEVELS):
                    record[f'best{i+1}_bid'] = float(bids[i][0])
                    record[f'best{i+1}_bid_qty'] = float(bids[i][1])
                    record[f'best{i+1}_ask'] = float(asks[i][0])
                    record[f'best{i+1}_ask_qty'] = float(asks[i][1])

                record['mid'] = (record['best1_bid'] + record['best1_ask']) / 2.0
                record['spread'] = record['best1_ask'] - record['best1_bid']
                total_qty = record['best1_bid_qty'] + record['best1_ask_qty']
                record['microprice'] = (
                    (record['best1_bid'] * record['best1_bid_qty'] +
                    record['best1_ask'] * record['best1_ask_qty']) / total_qty
                    if total_qty > 0 else record['mid']
                )

                records.append(record)

                new_date = get_filename(timestamp)
                if new_date != current_date:
                    if records and output_file is not None:
                        df = pd.DataFrame(records)
                        df.to_csv(output_file, mode='a',
                                header=not os.path.exists(output_file), index=False)
                        records = []
                    current_date = new_date
                    output_file = new_date

                if len(records) >= SAVE_INTERVAL:
                    if output_file is None:
                        output_file = get_filename(timestamp)
                    df = pd.DataFrame(records)
                    df.to_csv(output_file, mode='a',
                            header=not os.path.exists(output_file), index=False)
                    print(f"Saved {len(records)} records to {output_file}")
                    records = []

            def on_error(ws, error):
                print(f"Error: {error}")

            def on_close(ws, close_status_code, close_msg):
                print("WebSocket closed. Saving remaining records...")
                if records and output_file:
                    df = pd.DataFrame(records)
                    df.to_csv(output_file, mode='a',
                            header=not os.path.exists(output_file), index=False)
                print("Done.")

            def on_open(ws):
                print("Connected to Binance WebSocket. Streaming data...")

            ws = websocket.WebSocketApp(STREAM_URL,
                                        on_open=on_open,
                                        on_message=on_message,
                                        on_error=on_error,
                                        on_close=on_close)
            ws.run_forever()
        except Exception as e:
            print(f"WebSocket crashed: {e}. Restarting in 5 seconds...")
            time.sleep(1)

def main():
    getdata2()

if __name__ == '__main__':
    main()

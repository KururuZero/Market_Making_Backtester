import numpy as np
import pandas as pd
import math
import csv
import os

# timestamp  best_bid  best_bid_qty  
# best_ask  best_ask_qty        
# mid  spread    microprice


class trading_param:
    def __init__(self, ref = 'mid', half_spread = 0.05, qty = 0.001, gamma = 0.0, lamb = 1.0, fee = 0.0002, pos_limit = math.inf, max_loss = math.inf):
        self.ref = ref
        self.half_spread = half_spread
        self.qty = qty
        self.gamma = gamma
        self.lamb = lamb
        self.fee = fee
        self.pos_limit = pos_limit
        self.max_loss = max_loss
    def print_para(self):
        print(f'reference price = {self.ref}')
        print(f'half_spread = {self.half_spread}')
        print(f'qty = {self.qty}')
        print(f'gamma = {self.gamma}')
        print(f'lambda = {self.lamb}')
        print(f'Transection fee = {self.fee * 100}%')
        print(f'position limit = {self.pos_limit}')
        
class order:
    def __init__(self, timestamp, bid_price, bid_qty, bid_queue, ask_price, ask_qty, ask_queue):
        self.timestamp = timestamp
        self.bid_price= bid_price
        self.bid_qty = bid_qty
        self.bid_queue = bid_queue
        self.ask_price= ask_price
        self.ask_qty = ask_qty
        self.ask_queue = ask_queue

def date_generator(y, m, d):
    string = [str(y), str(m), str(d)]
    if (m < 10):
        string[1] = f"0{m}"
    if (d < 10):
        string[2] = f"0{d}"
    return f"{string[0]}-{string[1]}-{string[2]}"

def get_trade_path(date: str):
    return(f"BTCUSDT-aggTrades-{date}.csv")

def get_OB_path(date: str):
    return (f"live_orderbook_depth_{date}.csv")
class record:
    def __init__(self, var, last_OB_timestamp = None,
                 position = 0.0, cash = 0.0, trading_freq = np.array([0, 0]),
                 max_pos_record = np.array([0.0, 0.0]), 
                 bot_order = order("0", 0, 0, 0, 0, 0, 0), last_ref = 0.0,
                 hit_pos_max = False, hit_max_loss = False):
        self.var = var
        self.last_OB_timestamp = last_OB_timestamp
        self.position = position
        self.cash = cash
        self.trading_freq = trading_freq
        self.max_pos_record = max_pos_record
        self.bot_order = bot_order
        self.last_ref = last_ref
        self.hit_pos_max = hit_pos_max
        self.hit_max_loss = hit_max_loss
class websocket_plus_aggTrades_backtest:
    def __init__(self, trading_param = trading_param(), td_list = None, record = None):
        self.trading_param = trading_param
        self.td_list = td_list
        self.record  = None

    
    def get_return_var(self):
        ref = self.trading_param.ref
        if(len(self.td_list) > 0):
            test_date = self.td_list[0]
            df = pd.read_csv(get_OB_path(test_date))
            df[f'shift_{ref}'] = df[ref].shift(1)
            df[f'{ref}_change'] = df[ref] - df[f'shift_{ref}']
            result = ((df[f'{ref}_change'].dropna()).std()) ** 2
            del df
            return result
        
    def multi_EMWA_backtest(self):
        var = self.get_return_var()
        self.record = record(var)
        df_OB_last = None
        df_trade_remaining = None
        last_timestamp = None
        for day in self.td_list[1:]:
            if (not self.record.hit_max_loss and not self.record.hit_pos_max):
                if(df_OB_last is not None): 
                    df_OB = pd.concat([df_OB_last, pd.read_csv(get_OB_path(day))])
                    df_OB = df_OB.drop_duplicates(subset='timestamp', keep='last')
                    del df_OB_last
                else: df_OB = pd.read_csv(get_OB_path(day))

                if(df_trade_remaining is not None): 
                    df_trade = pd.concat([df_trade_remaining, pd.read_csv(get_trade_path(day))])
                    df_trade = df_trade.drop_duplicates(subset='transact_time', keep='last')
                    del df_trade_remaining
                else: 
                    df_trade = pd.read_csv(get_trade_path(day))

                self.record = self.single_EMWA_backtest(self.record, df_OB, df_trade, day == self.td_list[-1])
                df_OB_last = df_OB.iloc[-1:]
                del df_OB
                last_timestamp = df_OB_last.iloc[0]["timestamp"]
                df_trade_remaining = df_trade[df_trade["transact_time"] > last_timestamp]
                del df_trade

        final_equity = self.record.cash + self.record.position * self.record.last_ref
        return {
            "start_day"       : self.td_list[0],
            "end_day"         : self.td_list[-1],
            "ref"             : self.trading_param.ref,
            "half_spread"     : self.trading_param.half_spread,
            "gamma"           : self.trading_param.gamma,
            "lamb"            : self.trading_param.lamb,
            "hit_pos_max"     : self.record.hit_pos_max,
            "hit_max_loss"    : self.record.hit_max_loss,
            "final_equity"    : final_equity,
            "final_position"  : self.record.position,
            "buy_freq"        : self.record.trading_freq[0],
            "sell_freq"       : self.record.trading_freq[1],
            "max_pos"         : self.record.max_pos_record[0],
            "min_pos"         : self.record.max_pos_record[1],
        }

    def single_EMWA_backtest(self, rec, df_OB, df_trade, last_day = False):
        var = rec.var
        qty = self.trading_param.qty
        half_spread = self.trading_param.half_spread
        trading_freq = rec.trading_freq #buy and sell
        max_pos_record = rec.max_pos_record
        position = rec.position
        cash = rec.cash
        pos_max = self.trading_param.pos_limit
        hit_pos_max = rec.hit_pos_max
        max_loss = self.trading_param.max_loss
        hit_max_loss = rec.hit_max_loss
        lamb = self.trading_param.lamb
        fee = self.trading_param.fee
        ref_col = self.trading_param.ref
        
        df_OB2 = df_OB
        curr_ref = df_OB2.iloc[0][ref_col]
        if(rec.last_ref == 0.0):
            last_ref = curr_ref
        else:
            last_ref = rec.last_ref
        start_time = df_OB2['timestamp'].iloc[0]
        df_trade = df_trade[df_trade['transact_time'] >= start_time].copy()
        trade_ts    = df_trade['transact_time'].values      
        trade_price = df_trade['price'].values
        trade_qty   = df_trade['quantity'].values
        trade_buyer = df_trade['is_buyer_maker'].values

        bot_order = rec.bot_order
        trade_idx = 0
        trade_length = len(df_trade)
        last_timestamp = df_OB2["timestamp"].iloc[-1]
        if (not hit_pos_max and not hit_max_loss):
            for row in df_OB2.itertuples(index = False):
                if((not last_day) and (row.timestamp == last_timestamp)):
                    break
                while (trade_idx <trade_length and 
                    (bot_order.bid_qty > 0 or bot_order.ask_qty > 0) and 
                    trade_ts[trade_idx] < row.timestamp):
                    t_price = trade_price[trade_idx]
                    t_qty = trade_qty[trade_idx]

                    if(trade_buyer[trade_idx] == True):
                        if(bot_order.bid_price > t_price):
                            actual_qty = min(bot_order.bid_qty, t_qty)
                            bot_order.bid_qty -= actual_qty
                            position += actual_qty
                            cash -= actual_qty * bot_order.bid_price * (1 + fee)
                            trading_freq[0] +=1
                            if position > max_pos_record[0]:
                                max_pos_record[0] = position

                        if(bot_order.bid_price == t_price):
                            if(t_qty >= bot_order.bid_queue):
                                actual_qty = min(bot_order.bid_qty, t_qty - bot_order.bid_queue)
                                bot_order.bid_queue = 0.0
                                bot_order.bid_qty -= actual_qty
                                position += actual_qty
                                cash -= actual_qty * bot_order.bid_price * (1 + fee)
                                trading_freq[0] +=1
                                if position > max_pos_record[0]:
                                    max_pos_record[0] = position
                            else:
                                bot_order.bid_queue -= t_qty
                    else:
                        if(bot_order.ask_price < t_price):
                            actual_qty = min(bot_order.ask_qty, t_qty)
                            bot_order.ask_qty -= actual_qty
                            position -= actual_qty
                            cash += actual_qty * bot_order.ask_price * (1 - fee)
                            trading_freq[1]+=1
                            if position < max_pos_record[1]:
                                max_pos_record[1] = position
                        if(bot_order.ask_price == t_price):
                            if(t_qty >= bot_order.ask_queue):
                                actual_qty = min(bot_order.ask_qty, t_qty - bot_order.ask_queue)
                                bot_order.ask_queue = 0.0
                                bot_order.ask_qty -= actual_qty
                                position -= actual_qty
                                cash += actual_qty * bot_order.ask_price * (1 + fee)
                                trading_freq[1] +=1
                                if position < max_pos_record[1]:
                                    max_pos_record[1] = position
                            else:
                                bot_order.ask_queue -= t_qty
                    trade_idx += 1
                while(trade_idx <trade_length and trade_ts[trade_idx] < row.timestamp):
                    trade_idx += 1
                reference_price = getattr(row, ref_col)
        
                for j in range(5):
                    best_ask = getattr(row, f'best{j+1}_ask')
                    best_ask_qty = getattr(row, f'best{j+1}_ask_qty')
                    best_bid = getattr(row, f'best{j+1}_bid')
                    best_bid_qty = getattr(row, f'best{j+1}_bid_qty')

                    if(bot_order.bid_price > best_ask):
                        actual_qty = min(bot_order.bid_qty, best_ask_qty)
                        bot_order.bid_qty -= actual_qty
                        position += actual_qty
                        cash -= actual_qty * bot_order.bid_price * (1 + fee)
                        trading_freq[0] += 1
                        if position > max_pos_record[0]:
                            max_pos_record[0] = position
                    if(bot_order.bid_price == best_ask):
                        if(best_ask_qty >= bot_order.bid_queue):
                            actual_qty = min(bot_order.bid_qty, best_ask_qty - bot_order.bid_queue)
                            bot_order.bid_queue = 0.0
                            bot_order.bid_qty -= actual_qty
                            position += actual_qty
                            cash -= actual_qty * bot_order.bid_price * (1 + fee)
                            trading_freq[0] +=1
                            if position > max_pos_record[0]:
                                max_pos_record[0] = position
                        else:
                            bot_order.bid_queue -= best_ask_qty
                    if(bot_order.ask_price < best_bid):
                        actual_qty = min(bot_order.ask_qty, best_bid_qty)
                        bot_order.ask_qty -= actual_qty
                        position -= actual_qty
                        cash += actual_qty * bot_order.ask_price * (1 - fee)
                        trading_freq[1] += 1
                        if position < max_pos_record[1]:
                            max_pos_record[1] = position
                    if(bot_order.ask_price == best_bid):
                        if(best_bid_qty >= bot_order.ask_queue):
                            actual_qty = min(bot_order.ask_qty, best_bid_qty - bot_order.ask_queue)
                            bot_order.ask_queue = 0.0
                            bot_order.ask_qty -= actual_qty
                            position -= actual_qty
                            cash += actual_qty * bot_order.ask_price * (1 + fee)
                            trading_freq[1] +=1
                            if position < max_pos_record[1]:
                                max_pos_record[1] = position
                        else:
                            bot_order.ask_queue -= best_bid_qty
                    

                last_ref = curr_ref
                curr_ref = reference_price
                var = lamb * var + (1.0 - lamb) * ((math.log(curr_ref / last_ref)) ** 2)
                var_squared_ref = var * (curr_ref ** 2)
                dyn_half = half_spread + self.trading_param.gamma * var_squared_ref/ 2.0
                reservation = reference_price - self.trading_param.gamma * var_squared_ref * position
                bid = round(reservation - dyn_half, 2)
                ask = round(reservation + dyn_half, 2)
                bot_order.timestamp = row.timestamp
                if (bid != bot_order.bid_price or bot_order.bid_qty == 0.0):
                    bot_order.bid_price = bid
                    bot_order.bid_qty = qty
                    bot_order.bid_queue = 0.0
                    for j in range(5):
                        best_bid = getattr(row, f'best{j+1}_bid')
                        best_bid_qty = getattr(row, f'best{j+1}_bid_qty')
                        if(bid == best_bid):
                            bot_order.bid_queue = best_bid_qty

                    
                if (ask != bot_order.ask_price or bot_order.ask_qty == 0.0):
                    bot_order.ask_price = ask
                    bot_order.ask_qty = qty
                    bot_order.ask_queue = 0.0
                    for j in range(5):
                        best_ask = getattr(row, f'best{j+1}_ask')
                        best_ask_qty = getattr(row, f'best{j+1}_ask_qty')
                        if(ask == best_ask):
                            bot_order.ask_queue = best_ask_qty

                

                equity = cash + position * (row.best1_bid + row.best1_ask) / 2.0
                if (abs(position) > pos_max):
                    hit_pos_max = True 
                    break
                if (equity < -max_loss):
                    hit_max_loss = True
                    break

        return record(var = var, last_OB_timestamp = last_timestamp, position = position, 
                      cash = cash, trading_freq = trading_freq, max_pos_record = max_pos_record,
                      last_ref = curr_ref,
                      bot_order = bot_order, hit_pos_max = hit_pos_max, hit_max_loss = hit_max_loss)

def main():
    ref_list = ["mid"]
    # Each inner list is one continuous run: first day is for variance, rest are test days
    td_lists = [
        [date_generator(2026, 6, day) for day in range(2, 5)],        # 2,3,4
        [date_generator(2026, 6, day) for day in range(13, 19)]       # 13..18
    ]
    g_list = [0.1, 0.5, 1.0, 1.25, 1.5, 1.75, 2.0]
    s_list = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5]
    l_list = [0.99995, 0.9995, 0.995]

    results_file = "my_BT2.csv"
    header = [
        "start_day", "end_day", "ref", "half_spread", "gamma", "lamb",
        "hit_pos_max", "hit_max_loss", "final_equity", "final_position",
        "buy_freq", "sell_freq", "max_pos", "min_pos"
    ]

    if not os.path.exists(results_file):
        with open(results_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)

    for td_list in td_lists:
        for r in ref_list:
            for g in g_list:
                for s in s_list:
                    for l in l_list:
                        para = trading_param(
                            ref=r, half_spread=s, qty=0.001,
                            gamma=g, lamb=l, fee=0.0002,
                            pos_limit=2, max_loss=200000.0
                        )
                        bt = websocket_plus_aggTrades_backtest(
                            trading_param=para, td_list=td_list
                        )
                        metrics = bt.multi_EMWA_backtest()

                        with open(results_file, 'a', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([
                                metrics["start_day"], metrics["end_day"],
                                metrics["ref"], metrics["half_spread"],
                                metrics["gamma"], metrics["lamb"],
                                metrics["hit_pos_max"], metrics["hit_max_loss"],
                                metrics["final_equity"], metrics["final_position"],
                                metrics["buy_freq"], metrics["sell_freq"],
                                metrics["max_pos"], metrics["min_pos"],
                            ])

    print("All backtests completed. Results saved to", results_file)

if __name__ == '__main__':
    main()

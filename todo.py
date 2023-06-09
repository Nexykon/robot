import ccxt
import re
import time
import imaplib
import email
import csv
import os
import json
import threading
import matplotlib.pyplot as plt
from tkinter import *
from tkinter import ttk
import logging
import sys
import re
import time
from email import message_from_bytes

__all__ = ['exchange_instances', 'check_account_balance']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename='C:\\Python\\trading_bot\\logs\\trading_bot.log', mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)


def sync_exchange_time(exchange_instance):
    """Synchronize time with the Binance server"""
    try:
        exchange_time = exchange_instance.fetch_time()
        after = int(time.time() * 1000)
        diff = after - exchange_time
        if diff < -1000 or diff > 1000:
            print('Exchange time is out of sync, synchronizing...')
            ccxt.binance.options['adjustForTimeDifference'] = True
        else:
            print('Exchange time is in sync.')
    except Exception as e:
        print(f'Failed to synchronize time with exchange: {e}')



print("Loading API keys...")
with open('C:\\Python\\trading_bot\\api_keys.json') as f:
    api_key_data_list = json.load(f)
print("Loaded API keys: ", api_key_data_list)

with open('C:\\Python\\trading_bot\\email_credentials.json') as f:
    email_credentials = json.load(f)

with open('C:\\Python\\trading_bot\\config.json') as f:
    config = json.load(f)

timeframe = config['timeframe']
limit = config['limit']
percentage = config['percentage']
leverage = config['leverage']
 

print("Creating exchange instances...")
exchange_instances = [getattr(ccxt, api_key_data['exchange_id'])({
    'apiKey': api_key_data['api_key'],
    'secret': api_key_data['api_secret'],
    'timeout': 30000,
    'enableRateLimit': True,
    'options': {
        'recvWindow': 60000,
        'defaultType': 'future',  # To je ključno, da se povežete z Binance Futures API.
    },
}) for api_key_data in api_key_data_list if 'exchange_id' in api_key_data]
print("Created exchange instances: ", exchange_instances)


def get_trading_pairs(exchange_instance):
    try:
        markets = exchange_instance.load_markets()
        print("Loaded markets: ", markets)
        usdt_pairs = [pair for pair in markets.keys() if 'USDT' in pair and markets[pair]['active']]
        print("USDT pairs: ", usdt_pairs)
        return usdt_pairs
    except Exception as e:
        print(f"Error fetching trading pairs: {e}")
        return []

# Uporaba funkcije za pridobitev trgovalnih parov
if exchange_instances:
    trading_pairs = get_trading_pairs(exchange_instances[0])
    print("Trading pairs: ", trading_pairs)
else:
    # Izvedite ustrezno obdelavo ali izpišite sporočilo o napaki
    print("Seznam exchange_instances je prazen.")

def execute_trade(exchange_instance, signal, trading_pair, order_size, stop_loss_percent, take_profit_percent):
    try:
        # Preverite veljavnost vhodnih podatkov
        if not isinstance(exchange_instance, ccxt.Exchange):
            print("Napaka: Neveljavna instanca borze.")
            return None
        if signal.lower() not in ['buy', 'sell']:
            print("Napaka: Signal mora biti 'buy' ali 'sell'.")
            return None
        if not isinstance(trading_pair, str) or '/' not in trading_pair:
            print("Napaka: Neveljaven trgovalni par.")
            return None
        if not (0 < stop_loss_percent < 1 and 0 < take_profit_percent < 1):
            print("Napaka: Stop loss in take profit morata biti med 0 in 1.")
            return None
        
        if signal.lower() == 'buy':
            print(f'Kupujem na {exchange_instance.name} za valutni par {trading_pair}')
            order = exchange_instance.create_market_buy_order(trading_pair, order_size)

            entry_price = float(order['price'])
            stop_loss_price = entry_price * (1 - stop_loss_percent)
            take_profit_price = entry_price * (1 + take_profit_percent)

            exchange_instance.create_order(trading_pair, 'stop_loss_limit', 'sell', order_size, stop_loss_price, {'stopPrice': stop_loss_price})
            exchange_instance.create_order(trading_pair, 'limit', 'sell', order_size, take_profit_price)

        elif signal.lower() == 'sell':
            print(f'Prodajam na {exchange_instance.name} za valutni par {trading_pair}')
            order = exchange_instance.create_market_sell_order(trading_pair, order_size)

            entry_price = float(order['price'])
            stop_loss_price = entry_price * (1 + stop_loss_percent)
            take_profit_price = entry_price * (1 - take_profit_percent)

            exchange_instance.create_order(trading_pair, 'stop_loss_limit', 'buy', order_size, stop_loss_price, {'stopPrice': stop_loss_price})
            exchange_instance.create_order(trading_pair, 'limit', 'buy', order_size, take_profit_price)
        
        print(f"Executing trade: {signal} {trading_pair} {stop_loss_percent} {take_profit_percent}")
        print(f'Naročilo za {signal} izvedeno uspešno!')

    except Exception as e:
        print(f'Napaka pri izvedbi naročila: {e}')
        return None


total_order_size = 0.01
stop_loss_percent = 0.009  # 0.9%
take_profit_percent = 0.004  # 0.4%

def create_bybit_order(exchange, symbol, side, order_type, amount, price=None):
    if order_type == 'market':
        order = exchange.place_active_order(
            side=side.upper(),
            symbol=symbol.replace('/', ''),
            order_type=order_type.upper(),
            qty=amount,
            time_in_force='GTC'
        )
    else:
        order = exchange.place_active_order(
            side=side.upper(),
            symbol=symbol.replace('/', ''),
            order_type=order_type.upper(),
            qty=amount,
            price=price,
            time_in_force='GTC'
        )

    return order

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    else:
        return msg.get_payload(decode=True).decode()


from email import message_from_bytes

def parse_email_message(raw_email):
    parsed_email = message_from_bytes(raw_email)
    return parsed_email

def read_unread_emails(email_address, email_password):
    try:
        client = imaplib.IMAP4_SSL("imap.gmail.com")
        client.login(email_address, email_password)
        client.select("inbox")
        typ, messages = client.search(None, 'UNSEEN')
        messages = messages[0].split(b' ')
        alerts = []

        for msg_id in messages:
            if msg_id == b'':
                continue
            typ, msg_data = client.fetch(msg_id, '(RFC822)')
            raw_email = msg_data[0][1]
            msg = parse_email_message(raw_email)

            # Get the email body as plain text
            email_body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    email_body = part.get_payload(decode=True).decode('utf-8')
                    break

            if not email_body:
                print("Napaka: E-poštno sporočilo nima vsebine v obliki besedila.")
                continue

            # Print email body for debugging
            print(f"Prebrana vsebina e-pošte: {email_body}")
            
            try:
                email_data = json.loads(email_body)
            except json.JSONDecodeError:
                print("Napaka: E-poštno sporočilo ne vsebuje pravilnih JSON podatkov.")
                continue

            if "symbol" in email_data and "side" in email_data and "stop_loss_percent" in email_data and "take_profit_percent" in email_data:
                alerts.append((email_data["side"], email_data["symbol"], email_data["side"], float(email_data["stop_loss_percent"]), float(email_data["take_profit_percent"])))
            else:
                print("Napaka: E-poštno sporočilo ne vsebuje vseh potrebnih podatkov.")

        return alerts

    except Exception as e:
        logging.error(f"Error: {e}")
        return []
    finally:
        client.logout()


def parse_trading_signal(email):
    signal_data = {}
    
    signal_type_match = re.search(r'(BUY|SELL)', email, re.IGNORECASE)
    if signal_type_match:
        signal_data['signal_type'] = signal_type_match.group(1).lower()
    
    pairs_match = re.search(r'(\w+?)(USDT\.P)', email)
    if pairs_match:
        signal_data['trading_pair'] = pairs_match.group(1) + pairs_match.group(2)

    exchange_match = re.search(r'EXCHANGE\s*:\s*(\w+)', email, re.IGNORECASE)
    if exchange_match:
        signal_data['exchange'] = exchange_match.group(1)
        
    for field in ['Entry', 'SL']:
        match = re.search(f'{field}\s*:\s*([\d.]+)', email, re.IGNORECASE)
        if match:
            signal_data[field.lower()] = float(match.group(1))
    
    signal_data['tp'] = 0.4

    return signal_data



def check_tradingview_alerts():
    email_address = email_credentials['email_address']
    email_password = email_credentials['email_password']

    return read_unread_emails(email_address, email_password)

def log_trade(timestamp, trading_pair, signal, price):
    filename = 'trade_history.csv'
    file_exists = os.path.isfile(filename)

    with open(filename, 'a', newline='') as csvfile:
        headers = ['timestamp', 'trading_pair', 'signal', 'price']
        writer = csv.DictWriter(csvfile, delimiter=',', lineterminator='\n', fieldnames=headers)

        if not file_exists:
            writer.writeheader()

        writer.writerow({'timestamp': timestamp, 'trading_pair': trading_pair, 'signal': signal, 'price': price})

def plot_price_data(trading_pair):
    binance_instance = exchange_instances[0]  # Use the first Binance account for data retrieval
    timeframe = '1m'  # Timeframe for data collection
    limit = 100  # Number of candles in the data

    price_data = binance_instance.fetch_ohlcv(trading_pair, timeframe, limit=limit)
    timestamps, open_prices, high_prices, low_prices, close_prices, volumes = zip(*price_data)

    # Convert timestamps to appropriate format
    timestamps = [time.strftime('%Y-%m-%d %H:%M', time.localtime(ts // 1000)) for ts in timestamps]

    plt.plot(timestamps, close_prices)
    plt.xticks(rotation=45)
    plt.title(f'{trading_pair} Price')
    plt.xlabel('Timestamp')
    plt.ylabel('Price')
    plt.show()

def get_binance_futures_usdt_balance(exchange_instance):
    try:
        balance = exchange_instance.fetch_balance(params={'type': 'future'})
        usdt_balance = balance['USDT']['total']
        return usdt_balance
    except Exception as e:
        logging.error(f"Error fetching Binance Futures balance: {e}")
        return 0
        
def get_usdt_balance(binance_instance):
    try:
        balance = binance_instance.fetch_balance()
        usdt_balance = balance['free']['USDT']
        return usdt_balance
    except Exception as e:
        logging.error(f"Error fetching balance: {e}")
        return 0
        
def calculate_order_size(balance, percentage):
    return balance * (percentage / 100)

def sync_exchange_time(exchange_instance):
    try:
        exchange_time = exchange_instance.fetch_time()
        local_time = int(time.time() * 1000)
        time_diff = exchange_time - local_time
        exchange_instance.options['recvWindow'] = 60000 + time_diff
    except Exception as e:
        logging.error(f"Error syncing exchange time: {e}")


def main_loop():
    global stop_trading
    email_address = email_credentials['email_address']
    email_password = email_credentials['email_password']
    while not stop_trading:
        try:
            print("Preverjanje e-pošte...")
            logging.info("Preverjanje e-pošte...")
            alerts = read_unread_emails(email_address, email_password)

            logging.info(f"Prejeli ste {len(alerts)} opozoril: {alerts}")
            for signal, trading_pair, side, stop_loss_percent, take_profit_percent in alerts:
                for exchange_instance in exchange_instances:
                    sync_exchange_time(exchange_instance)
                    print(f"Izvajanje naročila na {exchange_instance.name} z naslednjimi parametri:")
                    print("Poselovanje valutni par:", trading_pair)
                    print("Stranski položaj:", side)
                    print("Odstotek za zaustavitev izgube:", stop_loss_percent)
                    print("Odstotek za dobiček:", take_profit_percent)
                    
                    execute_trade(exchange_instance, signal, trading_pair, 0.01, stop_loss_percent, take_profit_percent)

            time.sleep(60)
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)


def stop_main_loop():
    global stop_trading
    stop_trading = True

def start_main_loop():
    global stop_trading
    stop_trading = False
    main_thread = threading.Thread(target=main_loop)
    main_thread.start()

def check_account_balance(binance_instance):
    try:
        balance = binance_instance.fetch_balance()
        non_zero_balances = {coin: amount for coin, amount in balance['free'].items() if amount > 0}
        print("Balance:", non_zero_balances)
    except Exception as e:
        print(f"Error fetching balance: {e}")

def create_gui():
    def on_trading_pair_selected(event):
        selected_trading_pair.set(combo_trading_pairs.get())
    
    root = Tk()
    root.title("Trading Bot")

    mainframe = ttk.Frame(root, padding="3 3 12 12")
    mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    ttk.Label(mainframe, text="Trading Bot is running").grid(column=1, row=1, sticky=W)

    ttk.Button(mainframe, text="Start", command=start_main_loop).grid(column=3, row=3, sticky=W)
    ttk.Button(mainframe, text="Stop", command=stop_main_loop).grid(column=4, row=3, sticky=W)

    # Create a dropdown menu to select a trading pair
    selected_trading_pair = StringVar()
    combo_trading_pairs = ttk.Combobox(mainframe, textvariable=selected_trading_pair)
    
    # Get trading pairs
    if exchange_instances:
        trading_pairs = get_trading_pairs(exchange_instances[0])
    else:
        print("Seznam exchange_instances je prazen.")
        trading_pairs = []
    
    combo_trading_pairs['values'] = trading_pairs
    combo_trading_pairs.grid(column=1, row=3, sticky=W)
    
    if trading_pairs:  # Set default selected trading pair if trading_pairs is not empty
        combo_trading_pairs.current(0)  
        
    combo_trading_pairs.bind("<<ComboboxSelected>>", on_trading_pair_selected)

    ttk.Button(mainframe, text="Show Graph", command=lambda: plot_price_data(selected_trading_pair.get())).grid(column=5, row=3, sticky=W)

    for child in mainframe.winfo_children():
        child.grid_configure(padx=5, pady=5)

    root.mainloop()
if __name__ == "__main__":
    for i, instance in enumerate(exchange_instances):
        try:
            print(f"Account {i + 1}:")
            futures_usdt_balance = get_binance_futures_usdt_balance(instance)
            print("Futures USDT Balance:", futures_usdt_balance)
            trading_pairs = get_trading_pairs(instance)
        except Exception as e:
            logging.error(f"Error checking account balance: {e}")
    create_gui()

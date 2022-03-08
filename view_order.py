import yaml
import binance

credentials = None
with open("/home/ubuntu/ScraperPRO/auth/auth.yml", "r") as stream:
	credentials = yaml.safe_load(stream)

client = binance.Client(credentials["BINANCE"]["key"], credentials["BINANCE"]["secret"])

all_orders = client.get_all_orders(symbol='ANKRUSDT')
print(all_orders)

usdt_balance = client.get_asset_balance(asset='USDT')
print(usdt_balance)
ens_balance = client.get_asset_balance(asset='ANKR')
print(ens_balance)
ticker = client.get_symbol_ticker(symbol='ANKRUSDT')
print(ticker)
info = client.get_symbol_info(symbol='ANKRUSDT')
print(info)

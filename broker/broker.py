from abc import ABC, abstractmethod
from typing import Dict, Any, NoReturn, List

import binance.exceptions
from ftx.api import FtxClient
from binance.client import Client as BinanceClient
from datetime import datetime
from typing import Union
from util.types import BrokerType, Ticker, Order
from util.exceptions import *
from util import Config, Util
from dateutil.parser import parse
from util.decorators import retry
import yaml
import requests
import logging
import math
import traceback
import time


logger = logging.getLogger(__name__)


class Broker(ABC):
    def __init__(self) -> NoReturn:
        self.brokerType = None

    @staticmethod
    def factory(broker: BrokerType, subaccount: Union[str, None] = None) -> any:
        with open(Config.AUTH_DIR.joinpath("auth.yml")) as file:
            auth = yaml.load(file, Loader=yaml.FullLoader)

            if broker == "FTX":
                return FTX(
                    subaccount=subaccount,
                    key=auth["FTX"]["key"],
                    secret=auth["FTX"]["secret"],
                )
            if broker == "BINANCE":
                # TODO - SUBACCOUNTS FOR BINANCE IS NOT IMPLEMENTED YET
                return Binance(
                    subaccount="",
                    key=auth["BINANCE"]["key"],
                    secret=auth["BINANCE"]["secret"],
                )

    @abstractmethod
    def get_tickers(self, quote_ticker: str, **kwargs) -> List[Ticker]:
        """
        Returns all coins from Broker
        """
        raise NotImplementedError

    @abstractmethod
    def get_current_price(self, ticker: Ticker) -> float:
        """
        Get the current price for a coin
        """
        raise NotImplementedError

    @abstractmethod
    def place_order(self, config: Config, *args, **kwargs) -> Order:
        raise NotImplementedError

    @abstractmethod
    def convert_size(self, config: Config, ticker: Ticker, price: float) -> float:
        raise NotImplementedError


class FTX(FtxClient, Broker):
    def __init__(self, subaccount: str, key: str, secret: str) -> NoReturn:
        self.brokerType = "FTX"

        super().__init__(
            api_key=key,
            api_secret=secret,
            subaccount_name=subaccount,
        )

    @retry(
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            NoBrokerResponseException,
            Exception,
        ),
        2,
        0,
        None,
        1,
        0,
        logger,
    )
    def get_tickers(self, quote_ticker: str, **kwargs) -> List[Ticker]:
        try:
            api_resp = super(FTX, self).get_markets()

            test_retry = kwargs.get('test_retry', False)
            if test_retry:
                raise requests.exceptions.ConnectionError

            resp = []
            for ticker in api_resp:
                if (
                    ticker["type"] == "spot"
                    and ticker["enabled"]
                    and ticker["quoteCurrency"] == quote_ticker
                ):
                    if ticker["type"] == "spot" and ticker["enabled"]:
                        resp.append(
                            Ticker(
                                ticker=ticker["name"],
                                base_ticker=ticker["baseCurrency"],
                                quote_ticker=ticker["quoteCurrency"],
                            )
                        )
            return resp
        except Exception as e:
            if len(e.args) > 0 and "FTX is currently down" in e.args[0]:
                raise BrokerDownException(e.args[0])
            else:
                raise

    @retry(
        (
                Exception,
        ),
        2,
        3,
        None,
        1,
        0,
        logger,
    )
    @FtxClient.authentication_required
    def get_current_price(self, ticker: Ticker):
        Config.NOTIFICATION_SERVICE.debug(
            "Getting latest price for [{}]".format(ticker.ticker)
        )
        try:
            resp = float(self.get_market(market=ticker.ticker)["last"])

            if resp is None:
                raise GetPriceNoneResponse("None Response from Get Price")
            Config.NOTIFICATION_SERVICE.info(
                "FTX Price - {} {}".format(ticker.ticker, round(resp, 4))
            )
            return resp
        except LookupError as e:
            pass

    # @retry(
    #     (
    #             Exception,
    #     ),
    #     2,
    #     3,
    #     None,
    #     1,
    #     0,
    #     logger,
    # )
    @FtxClient.authentication_required
    def place_order(self, config: Config, *args, **kwargs) -> Order:
        if Config.TEST:
            price = kwargs.get(
                "current_price", self.get_current_price(kwargs["ticker"])
            )
            return Order(
                broker="FTX",
                ticker=kwargs["ticker"],
                purchase_datetime=datetime.now(),
                price=price,
                side=kwargs["side"],
                size=kwargs["size"],
                type="market",
                status="TEST_MODE",
                take_profit=Util.percent_change(price, config.TAKE_PROFIT_PERCENT),
                stop_loss=Util.percent_change(price, -config.STOP_LOSS_PERCENT),
                trailing_stop_loss_max=float("-inf"),
                trailing_stop_loss=Util.percent_change(
                    price, -config.TRAILING_STOP_LOSS_PERCENT
                ),
            )

        else:
            kwargs["market"] = kwargs["ticker"]
            del kwargs["ticker"]
            api_resp = super(FTX, self).place_order(*args, *kwargs)
            return Order(
                broker="FTX",
                ticker=kwargs["ticker"],
                purchase_datetime=parse(api_resp["createdAt"]),
                price=api_resp["price"],
                side=api_resp["side"],
                size=api_resp["size"],
                type="market",
                status="LIVE",
                take_profit=Util.percent_change(
                    api_resp["price"], config.TAKE_PROFIT_PERCENT
                ),
                stop_loss=Util.percent_change(
                    api_resp["price"], -config.STOP_LOSS_PERCENT
                ),
                trailing_stop_loss_max=float("-inf"),
                trailing_stop_loss=Util.percent_change(
                    api_resp["price"], -config.TRAILING_STOP_LOSS_PERCENT
                ),
            )

    def convert_size(self, config: Config, ticker: Ticker, price: float) -> float:
        size = config.QUANTITY / price
        return size


class Binance(BinanceClient, Broker):
    def __init__(self, subaccount: str, key: str, secret: str) -> NoReturn:
        self.brokerType = "BINANCE"

        super().__init__(api_key=key, api_secret=secret)

    @retry(
        (
                binance.exceptions.BinanceAPIException,
                Exception,
        ),
        2,
        3,
        None,
        1,
        0,
        logger,
    )
    def get_current_price(self, ticker: Ticker) -> float:
        Config.NOTIFICATION_SERVICE.debug(
            "Getting latest price for [{}]".format(ticker)
        )
        time.sleep(0.2)
        while True:
            try:
                retval = float(self.get_symbol_ticker(symbol=ticker.ticker)["price"])
            except binance.exceptions.BinanceAPIException:
                print("API get_current_price ERROR RETRY TOP KEK MY BROTHER")
                print(traceback.format_exc())
                time.sleep(0.3)
                continue
            break
        return retval


    def check_order(self, sell):
        # check order filled
        while True:
            try:
                return super(Binance, self).get_order(symbol=sell.ticker.ticker, orderId=sell.orderId)
            except:
                print(traceback.format_exc())
                time.sleep(Config.SELL_RETRY_SECONDS)
                continue


    def cancel(self, sell):
        while True:
            try:
                return super(Binance, self).cancel_order(symbol=sell.ticker.ticker, orderId=sell.orderId)
            except:
                print(traceback.format_exc())
                continue


    # @retry(
    #     (
    #             binance.exceptions.BinanceAPIException,
    #             Exception,
    #     ),
    #     2,
    #     3,
    #     None,
    #     1,
    #     0,
    #     logger,
    # )
    def place_order(self, config: Config, *args, **kwargs) -> Order:
        kwargs["symbol"] = kwargs["ticker"].ticker
        kwargs["type"] = "market"
        kwargs["quantity"] = kwargs["size"]
        kwargs['side'] = kwargs['side'].upper()
        all_filters = None
        if kwargs['side'] == 'SELL':
            kwargs["type"] = "market" if kwargs["current_price"]==-1 else "limit"
            all_filters = self.get_symbol_info(kwargs['symbol'])['filters']
            Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
                "\n\nSTEP SIZE IS\n" + str(all_filters) + "\n\n"
            )
            LOT_SIZE_filter = {}
            for f in all_filters:
                if f["filterType"] == "LOT_SIZE":
                    LOT_SIZE_filter = f
                    break
            step_size = float(LOT_SIZE_filter["stepSize"])
            Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("QUANTITY BEFORE STEPSIZE " + str(kwargs['quantity']))
            old_quantity = kwargs['quantity']
            precision = int(round(-math.log(step_size, 10), 0))
            new_quantity = round(old_quantity, precision)
            while new_quantity > old_quantity:
                new_quantity -= step_size
            kwargs['quantity'] = float(round(new_quantity, precision))
            Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("QUANTITY AFTER STEPSIZE " + str(kwargs['quantity']))

        kwargs['quoteOrderQty'] = kwargs['quantity']
        params = {}
        if kwargs['side'] == 'SELL':
            for p in ["quantity", "side", "symbol", "type"]:
                params[p] = kwargs[p]
            if kwargs["type"] == "limit":
                params["price"] = kwargs["buy_price"] + kwargs["current_price"]*kwargs["buy_price"]*config.LIMIT_SELL_PERCENT/100
                params["timeInForce"] = "GTC"
                for f in all_filters:
                    if f["filterType"] == "PRICE_FILTER":
                        PRICE_FILTER = f
                        break
                step_size = float(PRICE_FILTER["tickSize"])
                Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("QUANTITY BEFORE STEPSIZE " + str(params["price"]))
                old_price = params["price"]
                precision = int(round(-math.log(step_size, 10), 0))
                new_price = round(old_price, precision)
                while new_price > old_price:
                    new_price -= step_size
                params["price"] = float(round(new_price, precision))
                Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("QUANTITY AFTER STEPSIZE " + str(params["price"]))
        if kwargs['side'] == 'BUY':
            for p in ["quoteOrderQty", "side", "symbol", "type"]:
                params[p] = kwargs[p]

        if Config.TEST:
            # does not return anything.  No error mean request was good.
            api_resp = super(Binance, self).create_test_order(**params)
            price = self.get_current_price(kwargs["ticker"])

            return Order(
                broker="BINANCE",
                ticker=kwargs["ticker"],
                purchase_datetime=datetime.now(),
                price=price,
                side=kwargs["side"],
                size=kwargs["size"],
                type="market",
                status="TEST_MODE",
                take_profit=Util.percent_change(price, config.TAKE_PROFIT_PERCENT),
                stop_loss=Util.percent_change(price, -config.STOP_LOSS_PERCENT),
                trailing_stop_loss_max=float("-inf"),
                trailing_stop_loss=Util.percent_change(
                    price, -config.TRAILING_STOP_LOSS_PERCENT
                ),
            )
        else:
            api_resp = {}
            while True:
                try:
                    api_resp = super(Binance, self).create_order(**params)
                except binance.exceptions.BinanceAPIException:
                    print("API place_order ERROR RETRY TOP KEK MY BROTHER")
                    print(traceback.format_exc())
                    if kwargs['side'] == 'SELL':
                        time.sleep(config.SELL_RETRY_SECONDS)
                    continue
                break

            fill_sum = 0
            fill_count = 0

            for fill in api_resp['fills']:
                #fill_sum += (float(fill['price'])*float(fill['qty']) - float(fill['commission']))
                fill_sum += float(fill['price'])*float(fill['qty'])
                fill_count += float(fill['qty'])

            avg_fill_price = 0
            if kwargs["type"] == "market":
                avg_fill_price = fill_sum / fill_count
            print(api_resp["executedQty"])

            return Order(
                broker="BINANCE",
                ticker=kwargs["ticker"],
                purchase_datetime=datetime.now(),
                price=avg_fill_price if avg_fill_price!=0 else kwargs["buy_price"],
                side=api_resp["side"],
                size=float(api_resp["executedQty"])*0.995 if fill_count!=0 else params["quantity"],
                type="market",
                status="TEST_MODE" if Config.TEST else "LIVE",
                take_profit=Util.percent_change(
                    float(avg_fill_price), config.TAKE_PROFIT_PERCENT
                ),
                stop_loss=Util.percent_change(
                    float(avg_fill_price), -config.STOP_LOSS_PERCENT
                ),
                trailing_stop_loss_max=float("-inf"),
                trailing_stop_loss=Util.percent_change(
                    float(avg_fill_price), -config.TRAILING_STOP_LOSS_PERCENT
                ),
                orderId=api_resp["orderId"],
            )

    @retry(
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            NoBrokerResponseException,
            Exception,
        ),
        2,
        0,
        None,
        1,
        0,
        logger,
    )
    def get_tickers(self, quote_ticker: str, **kwargs) -> List[Ticker]:
        api_resp = super(Binance, self).get_exchange_info()

        test_retry = kwargs.get('test_retry', False)
        if test_retry:
            raise requests.exceptions.ConnectionError

        resp = []
        for ticker in api_resp["symbols"]:
            if ticker["isSpotTradingAllowed"] and ticker["quoteAsset"] == quote_ticker:
                resp.append(
                    Ticker(
                        ticker=ticker["symbol"],
                        base_ticker=ticker["baseAsset"],
                        quote_ticker=ticker["quoteAsset"],
                    )
                )

        return resp

    def convert_size(self, config: Config, ticker: Ticker, price: float) -> float:

        info = super(Binance, self).get_symbol_info(symbol=ticker.ticker)
        step_size = info["filters"][2]["stepSize"]
        lot_size = step_size.index("1") - 1
        lot_size = max(lot_size, 0)

        # calculate the volume in coin from QUANTITY in USDT (default)
        size = config.QUANTITY / price

        # if lot size has 0 decimal points, make the volume an integer
        if lot_size == 0:
            size = int(size)
        else:
            size = float("{:.{}f}".format(size, lot_size))

        return size

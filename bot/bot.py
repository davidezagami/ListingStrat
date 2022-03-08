import traceback
import time
import datetime
from typing import List, Dict, NoReturn, Tuple

from broker import Broker
from notification.notification import pretty_entry, pretty_close
from util import Config
from util import Util
from util.types import BrokerType, Ticker, Order, Sold

import scraper


class Bot:
    def __init__(self, broker: BrokerType) -> NoReturn:
        self.__sent_first_warning = False
        self.__sent_second_warning = False
        self.__sent_third_warning = False

        self.__target_coin = None
        self.__scraped_listing_time = None
        self.__listing_time_ts = 0
        self.__stage = 0

        self.__new_tickers_detected_time = 0
        self.__time_to_buy_seconds = 0
        self.__should_send_detection_notification = False
        self.once = True

        self.broker = Broker.factory(broker)
        self.config = Config(self.broker.brokerType)

        self._pending_remove = []

        self.ticker_seen_dict = []
        self.all_tickers, self.ticker_seen_dict = self.get_starting_tickers()

        # create / load files
        self.orders: Dict[str, Order] = {}
        self.orders_file = None

        self.sold: Dict[str, Sold] = {}
        self.sold_file = None

        for f in ["orders", "sold"]:
            file = Config.ROOT_DIR.joinpath(f"{self.broker.brokerType}_{f}.json")
            self.__setattr__(f"{f}_file", file)
            if file.exists():
                self.__setattr__(
                    f, Util.load_json(file, Order if f == "orders" else Sold)
                )

        # Meta info
        self.interval = 0


    def check_warnings(self):
        if not self.__sent_first_warning:
            if (self.__target_coin is not None) and (self.__listing_time_ts - time.time() < Config.FIRST_WARNING_TIME_MINUTES*60):
                Config.NOTIFICATION_SERVICE.info(
                    f"[{self.broker.brokerType}] will list {self.__target_coin} in {Config.FIRST_WARNING_TIME_MINUTES} minutes!"
                )
                self.__sent_first_warning = True
        if not self.__sent_second_warning:
            if (self.__target_coin is not None) and (self.__listing_time_ts - time.time() < Config.SECOND_WARNING_TIME_MINUTES*60):
                Config.NOTIFICATION_SERVICE.info(
                    f"[{self.broker.brokerType}] will list {self.__target_coin} in {Config.SECOND_WARNING_TIME_MINUTES} minutes!"
                )
                self.__sent_second_warning = True
        if not self.__sent_third_warning:
            if (self.__target_coin is not None) and (self.__listing_time_ts - time.time() < Config.THIRD_WARNING_TIME_SECONDS):
                Config.NOTIFICATION_SERVICE.info(
                    f"[{self.broker.brokerType}] will list {self.__target_coin} in {Config.THIRD_WARNING_TIME_SECONDS} seconds!"
                )
                self.__sent_third_warning = True

    def scrape_the_fucking_shit_m8(self) -> NoReturn:
        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
            f"[{self.broker.brokerType}]\tScraping..."
        )
        coin, listing_time = scraper.search_and_update()
        if coin is not None:
            self.__target_coin = coin
            self.__scraped_listing_time = listing_time
            self.__listing_time_ts = time.mktime(time.strptime(listing_time, "%Y-%m-%d %H:%M"))
            self.__sent_first_warning = False
            self.__sent_second_warning = False
            self.__sent_third_warning = False
            print("self.__target_coin", self.__target_coin)
            print("self.__scraped_listing_time", self.__scraped_listing_time)
            print("self.__listing_time_ts", self.__listing_time_ts)

    async def run_async(self) -> NoReturn:
        """
        Sells, adjusts TP and SL according to trailing values
        and buys new tickers
        """
        try:
            self.periodic_update()

            if (self.__target_coin is not None) and (-100*Config.CHECK_LISTING_START_TIME < self.__listing_time_ts - time.time() < Config.CHECK_LISTING_START_TIME):
                # basically the sell block and update TP and SL logic
                if len(self.orders) > 0:
                    Config.NOTIFICATION_SERVICE.debug(
                        f"[{self.broker.brokerType}]\tActive Order Tickers: [{self.orders}]"
                    )

                    for key, stored_order in self.orders.items():
                        if key not in self.sold:
                            #self.update(key, stored_order)
                            self.do_the_selling(key, stored_order)

                # remove pending removals
                [self.orders.pop(o) for o in self._pending_remove]
                if len(self._pending_remove) > 0:
                    self.__target_coin = None
                    self.__stage = 0
                    self.__scraped_listing_time = None
                    self.__listing_time_ts = 0
                self._pending_remove = []

                # check if new tickers are listed
                new_tickers = self.get_new_tickers()

                if len(new_tickers) > 0:
                    self.__new_tickers_detected_time = time.time()
                    self.__should_send_detection_notification = True
                    #Config.NOTIFICATION_SERVICE.debug(
                    #    f"[{self.broker.brokerType}]\tNew tickers detected: {new_tickers}"
                    #)

                    for new_ticker in new_tickers:
                        self.process_new_ticker(new_ticker)
                else:
                    Config.NOTIFICATION_SERVICE.debug(
                        f"[{self.broker.brokerType}]\tNo new tickers found.."
                    )

            self.interval += 1

        except Exception as e:
            self.save()
            Config.NOTIFICATION_SERVICE.error(traceback.format_exc())

        finally:
            self.save()


    def do_the_selling(self, key, order, **kwargs) -> NoReturn:
        time_now = time.time() - self.__listing_time_ts
        if (self.__stage == 0) and (time_now < self.config.LIMIT_SELL_SECONDS):
            res = self.close_trade(order, 1, order.price)
            if res:
                self.__stage = 3
                return
            self.__stage = 1
        elif (self.__stage == 1) and (self.config.LIMIT_SELL_SECONDS < time_now < self.config.MARKET_SELL_SECONDS):
            res = self.close_trade(order, 0, order.price)
            if res:
                self.__stage = 3
                return
            self.__stage = 2
        elif (self.__stage == 2) and (self.config.MARKET_SELL_SECONDS < time_now):
            self.close_trade(order, -1, order.price)
            self.__stage = 3


    def update(self, key, order, **kwargs) -> NoReturn:
        # This is for testing
        current_price = kwargs.get(
            "current_price", self.broker.get_current_price(order.ticker)
        )

        if self.__listing_time_ts + 10 < time.time():
            self.close_trade(order, current_price, order.price)
            return

        # if the price is decreasing and is below the stop loss
        if current_price < order.stop_loss:
            self.close_trade(order, current_price, order.price)

        # if the price is increasing and is higher than the old stop-loss maximum, update trailing stop loss
        elif (
                current_price > order.trailing_stop_loss_max
                and self.config.ENABLE_TRAILING_STOP_LOSS
        ):
            self.orders[key] = self.update_trailing_stop_loss(order, current_price)

        # if price is increasing and is higher than the take profit maximum
        elif current_price > order.take_profit:
            self.close_trade(order, current_price, order.price)

        # if the price is decreasing and has fallen below the trailing stop loss minimum
        elif current_price < order.trailing_stop_loss:
            self.close_trade(order, current_price, order.price)

    def upgrade_update(self) -> NoReturn:
        return
        if self.config.OUTDATED:
            Config.NOTIFICATION_SERVICE.warning(
                """\n*******************************************\nNEW UPDATE AVAILABLE. PLEASE UPDATE!\n*******************************************"""
            )

    def periodic_update(self) -> NoReturn:
        """
        log an update about every LOG_INFO_UPDATE_INTERVAL minutes
        also re-saves files
        """
        if (
                self.interval >= 0
                and self.interval
                % int(
                (Config.PROGRAM_OPTIONS["LOG_INFO_UPDATE_INTERVAL"] * 60)
                / Config.FREQUENCY_SECONDS
        )
                == 0
        ):
            Config.NOTIFICATION_SERVICE.debug(
                f"[{self.broker.brokerType}] ORDERS UPDATE:\n\t{self.orders}"
            )
            self.scrape_the_fucking_shit_m8()
            self.config = Config(self.broker.brokerType)
            Config.NOTIFICATION_SERVICE.debug(
                f"[{self.broker.brokerType}]\tSaving..."
            )
            self.save()
            self.upgrade_update()
        self.check_warnings()

    def get_starting_tickers(self) -> Tuple[List[Ticker], Dict[str, bool]]:
        """
        This method should be used once before starting the loop.
        The value for every ticker detected before the loop is set to True in the ticker_seen_dict.
        All the new tickers detected during the loop will have a value of False.
        """

        tickers = self.broker.get_tickers(self.config.QUOTE_TICKER)
        ticker_seen_dict: Dict[str, bool] = {}

        for ticker in tickers:
            ticker_seen_dict[ticker.ticker] = True

        return tickers, ticker_seen_dict

    def get_new_tickers(self, **kwargs) -> List[Ticker]:
        """
        This method checks if there are new tickers listed and returns them in a list.
        The value of the new tickers in ticker_seen_dict will be set to True to make them not get detected again.
        """
        new_tickers = []
        Config.NOTIFICATION_SERVICE.debug(
            f"[{self.broker.brokerType}]\tGetting all tickers.."
        )
        all_tickers_recheck = self.broker.get_tickers(self.config.QUOTE_TICKER)

        if (
                all_tickers_recheck is not None
                and len(all_tickers_recheck) != self.ticker_seen_dict
        ):
            new_tickers = [
                i for i in all_tickers_recheck if i.ticker not in self.ticker_seen_dict
            ]

            for new_ticker in new_tickers:
                self.ticker_seen_dict[new_ticker.ticker] = True

        def get_specific_ticker(tickers, ticker_name):
            if datetime.datetime.now().second>2:
                return []
            for x in tickers:
                if x.ticker == ticker_name:
                    if self.once:
                        self.once = False
                        return [x]
                    else:
                        return []
        return new_tickers# + get_specific_ticker(all_tickers_recheck, "ANKRUSDT")

    def update_trailing_stop_loss(self, order: Order, current_price: float) -> Order:

        # increase as absolute value for TP
        order.trailing_stop_loss_max = max(current_price, order.price)
        order.trailing_stop_loss = Util.percent_change(
            order.trailing_stop_loss_max, -self.config.TRAILING_STOP_LOSS_PERCENT
        )

        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
            f"[{self.broker.brokerType}]\t[{order.ticker.ticker}] Updated:\n\tTrailing Stop-Loss: {round(order.trailing_stop_loss, 8)} "
        )
        #Config.NOTIFICATION_SERVICE.info(
        #    f"[{self.broker.brokerType}]\t[{order.ticker.ticker}] Updated:\n\tTrailing Stop-Loss: {round(order.trailing_stop_loss, 8)} "
        #)

        return order

    def close_trade(
            self, order: Order, current_price: float, stored_price: float
    ) -> NoReturn:
        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
            "CLOSING Order:\n{}".format(order.json())
        )
        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
            "Current Price:\t{}".format(current_price)
        )
        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
            "Stored Price:\t{}".format(stored_price)
        )

        sell: Order = self.broker.place_order(
            self.config,
            ticker=order.ticker,
            side="sell",
            size=float(order.size),
            current_price=current_price,
            buy_price=stored_price,
        )

        success = False
        if current_price == -1:
            success = True
        else:
            time_limit = self.config.LIMIT_SELL_SECONDS if self.__stage==0 else self.config.MARKET_SELL_SECONDS
            time_now = time.time() - self.__listing_time_ts
            while time_now < time_limit:
                time_now = time.time() - self.__listing_time_ts
                # check order filled
                order_status = self.broker.check_order(sell)
                if order_status["executedQty"] == order_status["origQty"]:
                    success = True
                    break
                else:
                    time.sleep(Config.SELL_RETRY_SECONDS)
            if not success:
                self.broker.cancel(sell)
                return False

        Config.NOTIFICATION_SERVICE.message('CLOSE', pretty_close, (sell,order))
        # pending remove order from json file
        self._pending_remove.append(order.ticker.ticker)

        # store sold trades data
        sold = Sold(
            broker=sell.broker,
            ticker=order.ticker,
            purchase_datetime=order.purchase_datetime,
            price=sell.price,
            side=sell.side,
            size=sell.size,
            type=sell.type,
            status=sell.status,
            take_profit=sell.take_profit,
            stop_loss=sell.stop_loss,
            trailing_stop_loss_max=sell.trailing_stop_loss_max,
            trailing_stop_loss=sell.trailing_stop_loss,
            profit=(current_price * sell.size) - (stored_price * order.price),
            profit_percent=((current_price * sell.size) - (stored_price * order.price)) / (stored_price * order.price) * 100,
            sold_datetime=sell.purchase_datetime,
            orderId=sell.orderId
        )

        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("SOLD:\n{}".format(sold.json()))

        self.sold[order.ticker.ticker] = sold
        if not Config.TEST and Config.SHARE_DATA:
            Util.post_pipedream(sold)

        self.save()
        return success


    def process_new_ticker(self, new_ticker: Ticker, **kwargs) -> NoReturn:
        # buy if the ticker hasn't already been bought
        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
            "PROCESSING NEW TICKER:\n{}".format(new_ticker.json())
        )

        if (
                new_ticker.ticker not in self.orders
                and self.config.QUOTE_TICKER in new_ticker.quote_ticker
        ):
            #Config.NOTIFICATION_SERVICE.info(
            #    f"[{self.broker.brokerType}]\tPreparing to buy {new_ticker.ticker}"
            #)
            Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
                f"[{self.broker.brokerType}]\tPreparing to buy {new_ticker.ticker}"
            )

            #price = self.broker.get_current_price(new_ticker)
            #size = self.broker.convert_size(
            #    config=self.config, ticker=new_ticker, price=price
            #)
            size = float(self.config.QUANTITY)

            try:

                #Config.NOTIFICATION_SERVICE.info(
                #    f"[{self.broker.brokerType}]\tPlacing [{'TEST' if self.config.TEST else 'LIVE'}] Order.."
                #)
                Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
                    f"[{self.broker.brokerType}]\tPlacing [{'TEST' if self.config.TEST else 'LIVE'}] Order with " + str((new_ticker, size, "BUY", kwargs))
                )

                order = self.broker.place_order(
                    self.config, ticker=new_ticker, size=size, side="BUY", **kwargs
                )

                self.__time_to_buy_seconds = time.time() - self.__new_tickers_detected_time
                notif_msg = "TIME TO BUY %.4f seconds"%self.__time_to_buy_seconds
                notif_msg = "TIME TO BUY %.4f seconds"%float(str(order.purchase_datetime).split(':')[-1])
                if self.__should_send_detection_notification:
                    self.__should_send_detection_notification = False
                    notif_msg = f"[{self.broker.brokerType}]\tNew ticker detected: {new_ticker}\n\n" + notif_msg
                print(notif_msg)
                Config.NOTIFICATION_SERVICE.info(notif_msg)

                Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
                    "ORDER RESPONSE:\n{}".format(order.json())
                )
                self.orders[new_ticker.ticker] = order
                if not Config.TEST and Config.SHARE_DATA:
                    Util.post_pipedream(order)

                Config.NOTIFICATION_SERVICE.message('ENTRY', pretty_entry, (order,))
            except Exception as e:
                Config.NOTIFICATION_SERVICE.error(traceback.format_exc())
            finally:
                self.save()

        else:
            Config.NOTIFICATION_SERVICE.error(
                f"[{self.broker.brokerType}]\tNew new_ticker detected, but {new_ticker.ticker} is currently in "
                f"portfolio, or {self.config.QUOTE_TICKER} does not match"
            )
            Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error(
                f"[{self.broker.brokerType}]\tNew new_ticker detected, but {new_ticker.ticker} is currently in "
                f"portfolio, or {self.config.QUOTE_TICKER} does not match.\n{new_ticker.json()}"
            )

    def save(self) -> NoReturn:
        Util.dump_json(self.orders_file, self.orders)
        Util.dump_json(self.sold_file, self.sold)

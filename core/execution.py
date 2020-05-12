import datetime
import queue

from abc import ABCMeta, abstractmethod

from .event import FillEvent, OrderEvent

class ExecutionHandler(object):
    """
    The ExecutionHandler abstract class handles the interaction
    between a set of order objects generated by a Portfolio and
    the ultimate set of Fill objects that actually occur in the
    market.

    The handlers can be used to subclass simulated brokerages
    or live brokerages, with identical interfaces. This allows
    strategies to be backtested in a very similar manner to the
    live trading engine.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def execute_order(self, event):
        """
        Takes an Order event and executes it, producing
        a Fill event that gets placed onto the Events queue.

        Parameters:
        event - Contains an Event object with order information.
        """
        raise NotImplementedError("Should implement execute_order()")


class SimulatedExecutionHandler(ExecutionHandler):
    """
    The simulated execution handler simply converts all order
    objects into their equivalent fill objects automatically
    without latency, slippage or fill-ratio issues.

    This allows a straightforward "first go" test of any strategy,
    before implementation with a more sophisticated execution
    handler.
    """

    def __init__(self, events, bars):
        """
        Initialises the handler, setting the event queues
        up internally.

        Parameters:
        events - The Queue of Event objects.
        bars - The Data Handler that give the data feed.
        """
        self.events = events
        self.bars = bars

        self.all_orders = []

    def _find_open_order(self, symbol):
        # 找到当前所有订单中还开放的订单，即 entry_price 不是 None，
        # 但是 exit_price 是 None，返回。找不到返回 None。
        for order in self.all_orders:
            if order.symbol == symbol and order.entry_price is not None and \
                order.exit_price is None:
                return order
        return None

    def scan_open_orders(self, event):
        for symbol in self.bars.symbol_list:
            fill_events = []
            timeindex = self.bars.get_latest_bar_datetime(symbol)
            latest_bar = self.bars.get_latest_bar(symbol)[1]

            for order in self.all_orders:
                if order.symbol != symbol:
                    continue
                if order.entry_price is None:
                    if order.order_type == 'LMT' and order.limit_price is not None:
                        # Limit order 限价单的处理，确保还没进场，并且设置好了 limit price
                        if order.direction == 'BUY' and latest_bar['low'] < order.limit_price:
                            # 达到了进场条件，进场。实际应该是 ask low <= 才执行，买单要看 ask
                            # TODO: 时间应该是当前bar和之前一个bar之间的某一个时间。
                            order.entry_time = timeindex
                            # 简单的使用了 limit price，实际情况可能会更好的价格
                            order.entry_price = order.limit_price
                            fill_event = FillEvent(order, timeindex, order.limit_price,order.symbol,'LOCAL', order.quantity, order.direction, 0.01)
                            fill_events.append(fill_event)

                        if order.direction == 'SELL' and latest_bar['high'] > order.limit_price:
                            # 达到了进场条件，进场。实际应该是 bid high >= 才执行，卖单要看 bid
                            # TODO: 时间应该是当前bar和之前一个bar之间的某一个时间。
                            order.entry_time = timeindex
                            # 简单的使用了 limit price，实际情况可能会更好的价格
                            order.entry_price = order.limit_price
                            fill_event = FillEvent(order, timeindex, order.limit_price,order.symbol,'LOCAL', order.quantity, order.direction, 0.01)
                            fill_events.append(fill_event)
                    elif order.order_type == 'STP' and order.stop_price is not None:
                        # Stop order 限价单的处理，确保还没进场，并且设置好了 stop_price
                        # Stop order 不是 Stop loss!!!
                        # 具体区别查看 https://www.babypips.com/learn/forex/types-of-orders

                        # stop order 限价单的处理，确保还没进场，并且设置好了 stop_price
                        if order.direction == 'BUY' and latest_bar['high'] > order.stop_price:
                            # 达到了进场条件，进场。实际应该是 ask high = stop price的时候
                            # 触发一个 MKT 的买单，这里就略过了这个过程，直接把订单成交，
                            # 确保这个订单发生在当前bar的时间结束之前

                            # TODO: 时间应该是当前bar和之前一个bar之间的某一个时间。
                            order.entry_time = timeindex
                            # 简单的使用了 limit price，实际情况可能会更好的价格
                            order.entry_price = order.stop_price
                            fill_event = FillEvent(order, timeindex, order.stop_price,order.symbol,'LOCAL', order.quantity, order.direction, 0.01)
                            fill_events.append(fill_event)

                        if order.direction == 'SELL' and latest_bar['low'] < order.stop_price:
                            # 达到了进场条件，进场。实际应该是 bid low = stop price 的时候
                            # 触发一个 MKT 的卖单，这里就略过了这个过程，直接把订单成交，
                            # 确保这个订单发生在当前bar的时间结束之前

                            # TODO: 时间应该是当前bar和之前一个bar之间的某一个时间。
                            order.entry_time = timeindex
                            # 简单的使用了 limit price，实际情况可能会更好的价格
                            order.entry_price = order.stop_price
                            fill_event = FillEvent(order, timeindex, order.stop_price,order.symbol,'LOCAL', order.quantity, order.direction, 0.01)
                            fill_events.append(fill_event)
                elif order.entry_price is not None and order.exit_price is None:
                    # 处理已经进场的单子，触发止损 stop 或者止盈 limit
                    # stop_loss 和 profit target 的处理
                    if order.stop_loss is not None:
                        if order.direction == 'BUY' and latest_bar['low'] <= order.stop_loss:
                            # 触发止损
                            # 更新它的出场信息（价格，时间，盈亏）
                            order.exit_time = timeindex
                            order.exit_price = order.stop_loss
                            order.profit = (order.exit_price - order.entry_price) * order.quantity
                            # TODO: 这里的方向是 hardcoded，因为和order是反着的
                            fill_event = FillEvent(order, timeindex, order.exit_price,order.symbol,'LOCAL', order.quantity,'SELL', 0.01)
                            fill_events.append(fill_event)

                        if order.direction == 'SELL' and latest_bar['high'] >= order.stop_loss:
                           # 触发止损
                           # 更新它的出场信息（价格，时间，盈亏）
                           order.exit_time = timeindex
                           order.exit_price = order.stop_loss
                           order.profit = (order.exit_price - order.entry_price) * order.quantity
                           # TODO: 这里的方向是 hardcoded，因为和order是反着的
                           fill_event = FillEvent(order, timeindex, order.exit_price, order.symbol,'LOCAL', order.quantity,'BUY', 0.01)
                           fill_events.append(fill_event)

                    if order.profit_target is not None:
                        if order.direction == 'BUY' and latest_bar['high'] >= order.profit_target:
                            # 触发止盈
                            # 更新它的出场信息（价格，时间，盈亏）
                            order.exit_time = timeindex
                            order.exit_price = order.profit_target
                            order.profit = (order.profit_target - order.entry_price) * order.quantity
                            # TODO: 这里的方向是 hardcoded，因为和order是反着的
                            fill_event = FillEvent(order, timeindex, order.exit_price, order.symbol,'LOCAL', order.quantity,'SELL', 0.01)
                            fill_events.append(fill_event)

                        if order.direction == 'SELL' and latest_bar['low'] <= order.profit_target:
                            # 触发止盈
                            # 更新它的出场信息（价格，时间，盈亏）
                            order.exit_time = timeindex
                            order.exit_price = order.profit_target
                            order.profit = (order.profit_target - order.entry_price) * order.quantity
                            # TODO: 这里的方向是 hardcoded，因为和 order 是反着的
                            fill_event = FillEvent(order, timeindex, order.exit_price, order.symbol,'LOCAL', order.quantity,'BUY', 0.01)
                            fill_events.append(fill_event)

        return fill_events

    def execute_order(self, event):
        """
        Simply converts Order objects into Fill objects naively,
        i.e. without any latency, slippage or fill ratio problems.

        Parameters:
        event - Contains an Event object with order information.
        """
        if event.type == 'ORDER' and event.order_type == 'MKT':
            # Now we are opening a new order 按照市场价开新单
            timeindex = self.bars.get_latest_bar_datetime(event.symbol)
            price = self.bars.get_latest_bar_value(event.symbol, "close")
            order = self._find_open_order(event.symbol)
            if order is None:
                # 找不到，新建一个 order，更新它的进场时间和价格
                order = event
                order.entry_time = timeindex
                order.entry_price = price
                self.all_orders.append(event)
            else:
                # 找到了现有 order，更新它的信息
                order.exit_time = timeindex
                order.exit_price = price
                order.profit = (price - order.entry_price) * order.quantity
            # 无论如何，这个订单要按照市场价执行。
            fill_event = FillEvent(order, timeindex, price,
                                   event.symbol,'LOCAL', event.quantity,
                                   event.direction, 0.01)
            self.events.put(fill_event)

        elif event.type == 'ORDER' and \
            (event.order_type == 'LMT' or event.order_type == 'STP'):
            # 如果是限价单 limit/stop order，直接把订单放入订单池 self.all_orders
            # TODO: 理论上这个订单不会立即成交的吧？
            self.all_orders.append(event)

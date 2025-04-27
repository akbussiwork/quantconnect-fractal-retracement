from AlgorithmImports import *
from collections import deque

class WilliamsFractals:
    def __init__(self, fractal_length=5):
        self.fractal_length = fractal_length
        self._fractal = deque(maxlen=fractal_length)
        self._mid_index = fractal_length // 2 - (1 if fractal_length % 2 == 0 else 0)
        self._barry_up = None
        self._barry_down = None

    def add(self, bar):
        self._fractal.append(bar)
        if len(self._fractal) < self.fractal_length:
            return None
        mid = self._fractal[self._mid_index]
        if max(self._fractal, key=lambda b: b.High) == mid:
            self._barry_up = mid.High
        if min(self._fractal, key=lambda b: b.Low) == mid:
            self._barry_down = mid.Low
        if self._barry_up is not None and self._barry_down is not None:
            return (self._barry_up, self._barry_down)
        return None

class FractalFibOcoStrategy(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2023, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.SetCash(100000)

        future = self.AddFuture(Futures.Indices.SP500EMini, Resolution.Minute)
        future.SetFilter(lambda x: x.FrontMonth().Expiration(timedelta(0), timedelta(90)))
        self.chainSymbol = future.Symbol

        self.fractal = WilliamsFractals(fractal_length=5)
        self.bias = None
        self.inSetup = False
        self.previousWeeklyBar = None
        self.contractSymbol = None

        consolidator = TradeBarConsolidator(timedelta(weeks=1))
        consolidator.DataConsolidated += self.OnWeeklyBar
        self.SubscriptionManager.AddConsolidator(self.chainSymbol, consolidator)

    def OnWeeklyBar(self, sender, bar):
        if self.previousWeeklyBar is None:
            self.previousWeeklyBar = bar
            return

        if bar.High > self.previousWeeklyBar.High:
            self.bias = "bullish"
        elif bar.Low < self.previousWeeklyBar.Low:
            self.bias = "bearish"
        else:
            self.bias = "neutral"

        self.Log(f"[WeeklyBias] Bias: {self.bias}")

        self.inSetup = True
        self.previousWeeklyBar = bar

    def OnData(self, data):
        if self.contractSymbol is None:
            if self.chainSymbol not in data.FutureChains:
                return
            chain = data.FutureChains[self.chainSymbol]
            if not chain:
                return

            front = sorted(chain, key=lambda c: c.Expiry)[0]
            self.contractSymbol = front.Symbol
            self.AddFutureContract(self.contractSymbol, Resolution.Minute)
            self.Log(f"Subscribed to {self.contractSymbol}")
            return

        if not self.inSetup or self.bias is None or self.bias == "neutral":
            return

        if self.contractSymbol not in data.Bars:
            return

        price = data.Bars[self.contractSymbol].Close

        self.inSetup = False

        if self.bias == "bullish":
            self.EnterLongTrade(price)
        elif self.bias == "bearish":
            self.EnterShortTrade(price)

    def EnterLongTrade(self, price):
        self.Log(f"[Trade Bullish] Buying 1 contract at {price:.2f}")
        qty = 1
        self.MarketOrder(self.contractSymbol, qty)

        tick = self.Securities[self.contractSymbol].SymbolProperties.MinimumPriceVariation
        sl = price - (10 * tick)
        tp = price + (30 * tick)
        self.StopMarketOrder(self.contractSymbol, -qty, sl)
        self.LimitOrder(self.contractSymbol, -qty, tp)

    def EnterShortTrade(self, price):
        self.Log(f"[Trade Bearish] Selling 1 contract at {price:.2f}")
        qty = -1
        self.MarketOrder(self.contractSymbol, qty)

        tick = self.Securities[self.contractSymbol].SymbolProperties.MinimumPriceVariation
        sl = price + (10 * tick)
        tp = price - (30 * tick)
        self.StopMarketOrder(self.contractSymbol, -qty, sl)
        self.LimitOrder(self.contractSymbol, -qty, tp)

    def OnOrderEvent(self, orderEvent):
        self.Log(f"[OrderEvent] {orderEvent}")

    
   

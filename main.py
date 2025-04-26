from AlgorithmImports import *

class FractalFibOcoStrategy(QCAlgorithm):
    def Initialize(self):
        # Strategy parameters
        self.SetStartDate(2023, 1, 1)
        self.SetCash(100000)
        self.riskPercent = 0.01  # 1% risk per trade
        self.lookbackBars = 3    # fractal requires one bar on each side

        # Add and filter the futures contract
        future = self.AddFuture(Futures.Indices.SP500EMini, Resolution.Hour)
        future.SetFilter(TimeSpan.Zero, TimeSpan.FromDays(180))
        self.contractSymbol = None
        
        # Schedule monthly rollover
        self.Schedule.On(
            self.DateRules.MonthStart(future.Symbol),
            self.TimeRules.AfterMarketOpen(future.Symbol, 0),
            self.RollContracts
        )

    def RollContracts(self):
        # Automatically handled by filter, but log for clarity
        self.Log("Rolling to new nearest-future contract")
        self.contractSymbol = None  # reset, will pick up in OnData

    def OnData(self, data: Slice):
        # Ensure we have a live futures chain
        if not data.FutureChains.ContainsKey(self.AddedSecurities[0].Symbol):
            return

        chain = data.FutureChains[self.AddedSecurities[0].Symbol]
        # Select the front-month contract
        contract = sorted(chain.Contracts.Values, key=lambda c: c.Expiry)[0]
        if self.contractSymbol is None or contract.Symbol != self.contractSymbol:
            self.contractSymbol = contract.Symbol
            self.Log(f"Activated contract: {self.contractSymbol}")

        # Request history for the lookback window
        history = self.History([self.contractSymbol], self.lookbackBars*2 + 1, Resolution.Hour)
        if history.empty:
            return

        df = history.loc[self.contractSymbol].copy()
        df.columns = ['open','high','low','close','volume']

        # 1️⃣ Detect Fractals
        df['Fractal_High'] = (df['high'].shift(1) < df['high']) & (df['high'].shift(-1) < df['high'])
        df['Fractal_Low']  = (df['low'].shift(1)  > df['low']) & (df['low'].shift(-1)  > df['low'])

        # Get most recent fractals
        lows  = df[df['Fractal_Low']]
        highs = df[df['Fractal_High']]
        if lows.empty or highs.empty:
            return

        last_low  = lows.iloc[-1]
        last_high = highs.iloc[-1]
        # Ensure we have an uptrend fractal (low before high)
        if last_low.name >= last_high.name:
            return

        # 2️⃣ Compute Fibonacci levels
        low_price  = last_low['low']
        high_price = last_high['high']
        range_      = high_price - low_price
        fib21      = high_price + range_ * 0.21   # -21% extension
        fib0       = high_price                   # stop-loss
        fib100     = low_price                    # take-profit

        # 3️⃣ Check for cross below -21% trigger
        last_close  = df['close'].iloc[-1]
        prev_close  = df['close'].iloc[-2]
        invested    = self.Portfolio[self.contractSymbol].Invested
        if prev_close > fib21 and last_close <= fib21 and not invested:
            # Found entry signal
            entry_price  = fib21
            stop_price   = fib0
            profit_price = fib100

            # 4️⃣ Calculate position size
            qty = self.CalculatePositionSize(entry_price, stop_price)
            if qty == 0:
                self.Log("Calculated quantity is 0, skipping entry.")
                return

            # 5️⃣ Place OCO orders
            self.MarketOrder(self.contractSymbol, qty)
            self.StopMarketOrder(self.contractSymbol, -qty, stop_price)
            self.LimitOrder(self.contractSymbol, -qty, profit_price)
            self.Log(f"OCO placed: Entry={entry_price:.2f}, SL={stop_price:.2f}, TP={profit_price:.2f}, Qty={qty}")

    def CalculatePositionSize(self, entry_price: float, stop_price: float) -> int:
        # Risk amount in dollars
        risk_amount = self.Portfolio.Cash * self.riskPercent
        # Price distance to stop
        distance = abs(entry_price - stop_price)
        if distance <= 0:
            return 0
        # Contracts (rounded down)
        return int(risk_amount / distance)

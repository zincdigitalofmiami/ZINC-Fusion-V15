"""
A collection of Algos used to create Strategy logic.
"""
from __future__ import division

import abc
import random
import re

import numpy as np
import pandas as pd
import sklearn.covariance

import bt
from bt.core import Algo, AlgoStack, SecurityBase, is_zero


def run_always(f):
    """
    Run always decorator to be used with Algo
    to ensure stack runs the decorated Algo
    on each pass, regardless of failures in the stack.
    """
    f.run_always = True
    return f


class PrintDate(Algo):

    """
    This Algo simply print's the current date.

    Can be useful for debugging purposes.
    """

    def __call__(self, target):
        print(target.now)
        return True


class PrintTempData(Algo):

    """
    This Algo prints the temp data.

    Useful for debugging.

    Args:
        * fmt_string (str): A string that will later be formatted with the
          target's temp dict. Therefore, you should provide
          what you want to examine within curly braces ( { } )
    """

    def __init__(self, fmt_string=None):
        super(PrintTempData, self).__init__()
        self.fmt_string = fmt_string

    def __call__(self, target):
        if self.fmt_string:
            print(self.fmt_string.format(**target.temp))
        else:
            print(target.temp)
        return True


class PrintInfo(Algo):

    """
    Prints out info associated with the target strategy. Useful for debugging
    purposes.

    Args:
        * fmt_string (str): A string that will later be formatted with the
          target object's __dict__ attribute. Therefore, you should provide
          what you want to examine within curly braces ( { } )

    Ex:
        PrintInfo('Strategy {name} : {now}')


    This will print out the name and the date (now) on each call.
    Basically, you provide a string that will be formatted with target.__dict__

    """

    def __init__(self, fmt_string="{name} {now}"):
        super(PrintInfo, self).__init__()
        self.fmt_string = fmt_string

    def __call__(self, target):
        print(self.fmt_string.format(**target.__dict__))
        return True


class Debug(Algo):

    """
    Utility Algo that calls pdb.set_trace when triggered.

    In the debug session, 'target' is available and can be examined through the
    StrategyBase interface.
    """

    def __call__(self, target):
        import pdb

        pdb.set_trace()
        return True


class RunOnce(Algo):

    """
    Returns True on first run then returns False.

    Args:
        * run_on_first_call: bool which determines if it runs the first time the algo is called

    As the name says, the algo only runs once. Useful in situations
    where we want to run the logic once (buy and hold for example).

    """

    def __init__(self):
        super(RunOnce, self).__init__()
        self.has_run = False

    def __call__(self, target):
        # if it hasn't run then we will
        # run it and set flag
        if not self.has_run:
            self.has_run = True
            return True

        # return false to stop future execution
        return False


class RunPeriod(Algo):
    def __init__(
        self, run_on_first_date=True, run_on_end_of_period=False, run_on_last_date=False
    ):
        super(RunPeriod, self).__init__()
        self._run_on_first_date = run_on_first_date
        self._run_on_end_of_period = run_on_end_of_period
        self._run_on_last_date = run_on_last_date

    def __call__(self, target):
        # get last date
        now = target.now

        # if none nothing to do - return false
        if now is None:
            return False

        # not a known date in our universe
        if now not in target.data.index:
            return False

        # get index of the current date
        index = target.data.index.get_loc(target.now)

        result = False

        # index 0 is a date added by the Backtest Constructor
        if index == 0:
            return False
        # first date
        if index == 1:
            if self._run_on_first_date:
                result = True
        # last date
        elif index == (len(target.data.index) - 1):
            if self._run_on_last_date:
                result = True
        else:

            # create pandas.Timestamp for useful .week,.quarter properties
            now = pd.Timestamp(now)

            index_offset = -1
            if self._run_on_end_of_period:
                index_offset = 1

            date_to_compare = target.data.index[index + index_offset]
            date_to_compare = pd.Timestamp(date_to_compare)

            result = self.compare_dates(now, date_to_compare)

        return result

    @abc.abstractmethod
    def compare_dates(self, now, date_to_compare):
        raise (NotImplementedError("RunPeriod Algo is an abstract class!"))


class RunDaily(RunPeriod):

    """
    Returns True on day change.

    Args:
        * run_on_first_date (bool): determines if it runs the first time the algo is called
        * run_on_end_of_period (bool): determines if it should run at the end of the period
          or the beginning
        * run_on_last_date (bool): determines if it runs on the last time the algo is called

    Returns True if the target.now's day has changed
    compared to the last(or next if run_on_end_of_period) date, if not returns False.
    Useful for daily rebalancing strategies.

    """

    def compare_dates(self, now, date_to_compare):
        if now.date() != date_to_compare.date():
            return True
        return False


class RunWeekly(RunPeriod):

    """
    Returns True on week change.

    Args:
        * run_on_first_date (bool): determines if it runs the first time the algo is called
        * run_on_end_of_period (bool): determines if it should run at the end of the period
          or the beginning
        * run_on_last_date (bool): determines if it runs on the last time the algo is called

    Returns True if the target.now's week has changed
    since relative to the last(or next) date, if not returns False. Useful for
    weekly rebalancing strategies.

    """

    def compare_dates(self, now, date_to_compare):
        if now.year != date_to_compare.year or now.week != date_to_compare.week:
            return True
        return False


class RunMonthly(RunPeriod):

    """
    Returns True on month change.

    Args:
        * run_on_first_date (bool): determines if it runs the first time the algo is called
        * run_on_end_of_period (bool): determines if it should run at the end of the period
          or the beginning
        * run_on_last_date (bool): determines if it runs on the last time the algo is called

    Returns True if the target.now's month has changed
    since relative to the last(or next) date, if not returns False. Useful for
    monthly rebalancing strategies.

    """

    def compare_dates(self, now, date_to_compare):
        if now.year != date_to_compare.year or now.month != date_to_compare.month:
            return True
        return False


class RunQuarterly(RunPeriod):

    """
    Returns True on quarter change.

    Args:
        * run_on_first_date (bool): determines if it runs the first time the algo is called
        * run_on_end_of_period (bool): determines if it should run at the end of the period
          or the beginning
        * run_on_last_date (bool): determines if it runs on the last time the algo is called

    Returns True if the target.now's quarter has changed
    since relative to the last(or next) date, if not returns False. Useful for
    quarterly rebalancing strategies.

    """

    def compare_dates(self, now, date_to_compare):
        if now.year != date_to_compare.year or now.quarter != date_to_compare.quarter:
            return True
        return False


class RunYearly(RunPeriod):

    """
    Returns True on year change.

    Args:
        * run_on_first_date (bool): determines if it runs the first time the algo is called
        * run_on_end_of_period (bool): determines if it should run at the end of the period
          or the beginning
        * run_on_last_date (bool): determines if it runs on the last time the algo is called

    Returns True if the target.now's year has changed
    since relative to the last(or next) date, if not returns False. Useful for
    yearly rebalancing strategies.

    """

    def compare_dates(self, now, date_to_compare):
        if now.year != date_to_compare.year:
            return True
        return False


class RunOnDate(Algo):

    """
    Returns True on a specific set of dates.

    Args:
        * dates (list): List of dates to run Algo on.

    """

    def __init__(self, *dates):
        """
        Args:
            * dates (*args): A list of dates. Dates will be parsed
              by pandas.to_datetime so pass anything that it can
              parse. Typically, you will pass a string 'yyyy-mm-dd'.
        """
        super(RunOnDate, self).__init__()
        # parse dates and save
        self.dates = [pd.to_datetime(d) for d in dates]

    def __call__(self, target):
        return target.now in self.dates


class RunAfterDate(Algo):

    """
    Returns True after a date has passed

    Args:
        * date: Date after which to start trading

    Note:
        This is useful for algos that rely on trailing averages where you
        don't want to start trading until some amount of data has been built up

    """

    def __init__(self, date):
        """
        Args:
            * date: Date after which to start trading
        """
        super(RunAfterDate, self).__init__()
        # parse dates and save
        self.date = pd.to_datetime(date)

    def __call__(self, target):
        return target.now > self.date


class RunAfterDays(Algo):

    """
    Returns True after a specific number of 'warmup' trading days have passed

    Args:
        * days (int): Number of trading days to wait before starting

    Note:
        This is useful for algos that rely on trailing averages where you
        don't want to start trading until some amount of data has been built up

    """

    def __init__(self, days):
        """
        Args:
            * days (int): Number of trading days to wait before starting
        """
        super(RunAfterDays, self).__init__()
        self.days = days

    def __call__(self, target):
        if self.days > 0:
            self.days -= 1
            return False
        return True


class RunIfOutOfBounds(Algo):

    """
    This algo returns true if any of the target weights deviate by an amount greater
    than tolerance. For example, it will be run if the tolerance is set to 0.5 and
    a security grows from a target weight of 0.2 to greater than 0.3.

    A strategy where rebalancing is performed quarterly or whenever any
    security's weight deviates by more than 20% could be implemented by:

        Or([runQuarterlyAlgo,runIfOutOfBoundsAlgo(0.2)])

    Args:
        * tolerance (float): Allowed deviation of each security weight.

    Requires:
        * Weights

    """

    def __init__(self, tolerance):
        self.tolerance = float(tolerance)
        super(RunIfOutOfBounds, self).__init__()

    def __call__(self, target):
        if "weights" not in target.temp:
            return True

        targets = target.temp["weights"]

        for cname in target.children:
            if cname in targets:
                c = target.children[cname]
                deviation = abs((c.weight - targets[cname]) / targets[cname])
                if deviation > self.tolerance:
                    return True

        if "cash" in target.temp:
            cash_deviation = abs(
                (target.capital - targets.value) / targets.value - target.temp["cash"]
            )
            if cash_deviation > self.tolerance:
                return True

        return False


class RunEveryNPeriods(Algo):

    """
    This algo runs every n periods.

    Args:
        * n (int): Run each n periods
        * offset (int): Applies to the first run. If 0, this algo will run the
          first time it is called.

    This Algo can be useful for the following type of strategy:
        Each month, select the top 5 performers. Hold them for 3 months.

    You could then create 3 strategies with different offsets and create a
    master strategy that would allocate equal amounts of capital to each.

    """

    def __init__(self, n, offset=0):
        super(RunEveryNPeriods, self).__init__()
        self.n = n
        self.offset = offset
        self.idx = n - offset - 1
        self.lcall = 0

    def __call__(self, target):
        # ignore multiple calls on same period
        if self.lcall == target.now:
            return False
        else:
            self.lcall = target.now
            # run when idx == (n-1)
            if self.idx == (self.n - 1):
                self.idx = 0
                return True
            else:
                self.idx += 1
                return False


class SelectAll(Algo):

    """
    Sets temp['selected'] with all securities (based on universe).

    Selects all the securities and saves them in temp['selected'].
    By default, SelectAll does not include securities that have no
    data (nan) on current date or those whose price is zero or negative.

    Args:
        * include_no_data (bool): Include securities that do not have data?
        * include_negative (bool): Include securities that have negative
          or zero prices?
    Sets:
        * selected

    """

    def __init__(self, include_no_data=False, include_negative=False):
        super(SelectAll, self).__init__()
        self.include_no_data = include_no_data

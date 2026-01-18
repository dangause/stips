"""A timed cache decorator to cache values from a function or method for a period of time."""

from collections.abc import Callable, Hashable
from datetime import datetime, timedelta, timezone
from functools import wraps


class TimedCache:
    """A cache that times out values after a passed in timeout expires.

    When an item is set in the cache, the time is also recorded. Subsequent
    calls to get the item will succeed until the timeout expires.

    TimedCache.NO_VALUE is returned if the item has timed out or has never been added to the cache.

    Args:
        timeout : The length of time to cache items.
    """

    class _NoValueType:
        """Sentinel type used to represent an unset value. This allows ``None`` to be a valid value
        in the cache."""

        pass

    NO_VALUE = _NoValueType()
    """Value indicating an item is not in the cache."""

    def __init__(self, timeout: timedelta):
        self.cache = {}
        self.timeout = timeout

    def __getitem__(self, key):
        if key in self.cache:
            time_set, value = self.cache[key]
            if time_set + self.timeout < datetime.now(timezone.utc):
                del self.cache[key]
            else:
                return value
        return TimedCache.NO_VALUE

    def __setitem__(self, key, value):
        self.cache[key] = (datetime.now(timezone.utc), value)

    def clear(self):
        """Force clear the cache. Useful for unit testing. The timed_cache decorator
        is written such that the wrapped method/function will have a cache attribute
        that can be cleared with this method"""
        self.cache = {}


def timed_cache(cache_timeout: timedelta) -> Callable:
    """Decorator to indicate the values returned from a function or method should be cached for a given
    period of time. After that period of time the function will be called again to repopulate the cache.

    In order to be used on function, all arguments to the function must be hashable. Since "self" is an
    argument to methods, any class that uses timed_cache on one of its methods must also be hashable.

    Args:
        cache_timeout: The period of time keep values in the cache
    """

    # Define the actual decorator which takes a function and returns a wrapped version of it
    def timed_cache_decorator(func):

        # The wrapper function for caching results
        @wraps(func)
        def timed_cache_wrapper(*args, **kwargs):

            # Combine the argument values into a tuple to form a hash key
            all_args = args + tuple([kwargs[x] for x in sorted(kwargs.keys())])

            # If any aren't hashable, convert to strings
            hash_key = tuple(
                [arg if isinstance(arg, Hashable) else str(arg) for arg in all_args]
            )

            result = timed_cache_wrapper.cache[hash_key]
            if result is TimedCache.NO_VALUE:
                # No cached value, call the function to generate results and cache those
                result = func(*args, **kwargs)
                timed_cache_wrapper.cache[hash_key] = result
            return result

        # Make sure the cache is initialized
        if not hasattr(timed_cache_wrapper, "cache"):
            timed_cache_wrapper.cache = TimedCache(cache_timeout)

        return timed_cache_wrapper

    return timed_cache_decorator

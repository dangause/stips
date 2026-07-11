def test_cached_values():

    from datetime import timedelta

    from lick_archive.utils import timed_cache

    test_cached_values.times_called = 0

    @timed_cache.timed_cache(timedelta(hours=1))
    def test_function(a, b, c):
        test_cached_values.times_called += 1
        return a

    # Verify the function is called the initial time
    assert test_function(1, "string", ["list", "of", "strings"]) == 1
    assert test_cached_values.times_called == 1

    assert test_function(1, b="string", c=["list", "of", "other", "strings"]) == 1
    assert test_cached_values.times_called == 2

    assert test_function(2, "string", ["list", "of", "other", "strings"]) == 2
    assert test_cached_values.times_called == 3

    # Verify the second time arguments are passed a cached value is used (i.e. times_called) does not go up
    assert test_function(1, "string", ["list", "of", "strings"]) == 1
    assert test_cached_values.times_called == 3

    assert test_function(1, "string", ["list", "of", "other", "strings"]) == 1
    assert test_cached_values.times_called == 3

    assert test_function(2, "string", ["list", "of", "other", "strings"]) == 2
    assert test_cached_values.times_called == 3


def test_cache_timeout():
    import time
    from datetime import timedelta

    from lick_archive.utils import timed_cache

    test_cache_timeout.times_called = 0

    @timed_cache.timed_cache(timedelta(seconds=2))
    def test_function(a, b, c):
        test_cache_timeout.times_called += 1
        return a

    assert test_function(1, "string", ["list", "of", "strings"]) == 1
    assert test_cache_timeout.times_called == 1

    time.sleep(5)

    assert test_function(1, "string", ["list", "of", "strings"]) == 1
    assert test_cache_timeout.times_called == 2

#include "VideoPlaybackClock.h"
#include <cassert>
#include <initializer_list>

int main() {
  for (int requests : {30, 60, 120}) {
    VideoPlaybackClock clock;
    assert(clock.Frame(0, false, 1) == 0);
    for (int i = 1; i <= requests * 10; ++i) {
      const int64_t now = int64_t(i) * 1000000000LL / requests;
      const auto expected = uint64_t(now / 1000000000LL * 30 +
                                   now % 1000000000LL * 30 / 1000000000LL);
      assert(clock.Frame(now, false, 1) == expected);
      assert(clock.Frame(now, false, 1) == expected); // Second camera output.
    }
    assert(clock.Frame(10000000000LL, true, 1) == 300);
    assert(clock.Frame(20000000000LL, true, 1) == 300);
    assert(clock.Frame(20000000000LL, false, 1) == 300);
    assert(clock.Frame(21000000000LL, false, 1) == 330);
    assert(clock.Frame(22000000000LL, true, 2) == 0);
    assert(clock.Frame(32000000000LL, false, 2) == 0);
    assert(clock.Frame(33000000000LL, false, 2) == 30);
  }
}

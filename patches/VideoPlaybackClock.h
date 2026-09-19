#pragma once

#include <cstdint>

// Caller supplies monotonic nanoseconds and serializes access across outputs.
class VideoPlaybackClock {
 public:
  uint64_t Frame(int64_t now, bool paused, uint64_t generation) {
    if (!initialized_ || generation != generation_) {
      elapsed_ = 0;
      initialized_ = true;
      generation_ = generation;
    } else if (!paused_ && now > previous_) {
      elapsed_ += now - previous_;
    }
    previous_ = now;
    paused_ = paused;
    return (elapsed_ / 1000000000LL) * 30 +
           (elapsed_ % 1000000000LL) * 30 / 1000000000LL;
  }

 private:
  bool initialized_ = false;
  bool paused_ = true;
  uint64_t generation_ = 0;
  int64_t previous_ = 0;
  int64_t elapsed_ = 0;
};

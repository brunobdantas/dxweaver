#include "HuntWatchdog.h"

#include <algorithm>

namespace dxw {

const std::int64_t HuntWatchdog::kStaleAfterMs;
const std::int64_t HuntWatchdog::kHardTimeoutMs;

void HuntWatchdog::start(const std::string& call, std::int64_t nowMs) noexcept {
    call_ = call;
    startedMs_ = nowMs;
    lastSeenMs_ = nowMs;
    engaged_ = false;
}

void HuntWatchdog::observe(const std::string& call, std::int64_t nowMs) noexcept {
    if (call_.empty() || call != call_) return;
    lastSeenMs_ = std::max(lastSeenMs_, nowMs);
}

void HuntWatchdog::engage(const std::string& call) noexcept {
    if (call_.empty() || call != call_) return;
    engaged_ = true;
}

void HuntWatchdog::clear() noexcept {
    call_.clear();
    startedMs_ = 0;
    lastSeenMs_ = 0;
    engaged_ = false;
}

std::int64_t HuntWatchdog::ageMs(std::int64_t nowMs) const noexcept {
    if (call_.empty()) return 0;
    return std::max<std::int64_t>(0, nowMs - startedMs_);
}

std::int64_t HuntWatchdog::silentMs(std::int64_t nowMs) const noexcept {
    if (call_.empty()) return 0;
    return std::max<std::int64_t>(0, nowMs - lastSeenMs_);
}

bool HuntWatchdog::shouldExpire(std::int64_t nowMs) const noexcept {
    if (call_.empty() || engaged_) return false;
    const std::int64_t age = ageMs(nowMs);
    const std::int64_t silence = silentMs(nowMs);
    return age >= kHardTimeoutMs ||
           (age >= kStaleAfterMs && silence >= kStaleAfterMs);
}

} // namespace dxw

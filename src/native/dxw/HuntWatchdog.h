#pragma once

#include <cstdint>
#include <string>

namespace dxw {

class HuntWatchdog final {
public:
    static const std::int64_t kStaleAfterMs = 30000;
    static const std::int64_t kHardTimeoutMs = 45000;

    void start(const std::string& call, std::int64_t nowMs) noexcept;
    void observe(const std::string& call, std::int64_t nowMs) noexcept;
    void engage(const std::string& call) noexcept;
    void clear() noexcept;

    bool active() const noexcept { return !call_.empty(); }
    bool engaged() const noexcept { return engaged_; }
    const std::string& call() const noexcept { return call_; }
    std::int64_t ageMs(std::int64_t nowMs) const noexcept;
    std::int64_t silentMs(std::int64_t nowMs) const noexcept;
    bool shouldExpire(std::int64_t nowMs) const noexcept;

private:
    std::string call_;
    std::int64_t startedMs_{0};
    std::int64_t lastSeenMs_{0};
    bool engaged_{false};
};

} // namespace dxw

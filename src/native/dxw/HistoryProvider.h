#pragma once

#include <memory>
#include <string>

namespace dxw {

struct HistoryFacts {
    bool worked{false};
    bool confirmed{false};
    bool workedBand{false};
    bool workedMode{false};
};

class IHistoryProvider {
public:
    virtual ~IHistoryProvider() = default;
    virtual HistoryFacts lookup(const std::string& call, const std::string& band,
                                const std::string& mode) const = 0;
};

class ResilientHistoryProvider final : public IHistoryProvider {
public:
    explicit ResilientHistoryProvider(std::shared_ptr<const IHistoryProvider> primary)
        : primary_(std::move(primary)) {}

    HistoryFacts lookup(const std::string& call, const std::string& band,
                        const std::string& mode) const override {
        if (!primary_) return {};
        try { return primary_->lookup(call, band, mode); }
        catch (...) { return {}; }
    }

private:
    std::shared_ptr<const IHistoryProvider> primary_;
};

} // namespace dxw
